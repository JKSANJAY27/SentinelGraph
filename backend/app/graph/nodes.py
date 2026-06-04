import subprocess
import time
import os
import asyncio
import json
import httpx
from typing import Dict, Any, List
from .state import IncidentState
from ..llm import get_llm
from ..memory.memory_store import save_memory, retrieve_relevant_memories

llm = get_llm()

# Global registry of real-time SSE queues for streaming agent updates to the UI
# incident_id -> list of (asyncio.Queue, asyncio.AbstractEventLoop)
incident_queues: Dict[str, List[tuple]] = {}

def register_queue(incident_id: str, queue: asyncio.Queue):
    if incident_id not in incident_queues:
        incident_queues[incident_id] = []
    try:
        import asyncio
        loop = asyncio.get_running_loop()
    except RuntimeError:
        import asyncio
        loop = asyncio.get_event_loop()
    incident_queues[incident_id].append((queue, loop))

def unregister_queue(incident_id: str, queue: asyncio.Queue):
    if incident_id in incident_queues:
        incident_queues[incident_id] = [item for item in incident_queues[incident_id] if item[0] is not queue]

def call_mcp_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Route tool calls through the standardized MCP layer in-process."""
    from app.mcp.mcp_server import mcp_server
    payload = {
        "jsonrpc": "2.0",
        "id": "agent-call",
        "method": "tools/call",
        "params": {
            "name": name,
            "arguments": arguments
        }
    }
    response = mcp_server.dispatch(payload)
    if "error" in response:
        raise RuntimeError(response["error"]["message"])
    return response["result"]

def log_step(state: IncidentState, msg: str) -> None:
    """Helper to log agent execution trails and notify live streaming frontend web sockets/SSE."""
    print(f"[AGENT FLOW] {msg}")
    state["execution_history"].append(msg)
    
    # Save a snapshot of the current state variables for the playback scrubber
    if "snapshots" not in state or state["snapshots"] is None:
        state["snapshots"] = []
        
    import copy
    snapshot = {
        "step_index": len(state["snapshots"]) + 1,
        "timestamp": time.time(),
        "message": msg,
        "status": state.get("status"),
        "service": state.get("service"),
        "severity": state.get("severity"),
        "logs": copy.deepcopy(state.get("logs", {})),
        "metrics": copy.deepcopy(state.get("metrics", {})),
        "deploys": copy.deepcopy(state.get("deploys", [])),
        "runbooks": copy.deepcopy(state.get("runbooks", [])),
        "dependencies": copy.deepcopy(state.get("dependencies", {})),
        "hypotheses": copy.deepcopy(state.get("hypotheses", [])),
        "recovery_plan": copy.deepcopy(state.get("recovery_plan", {})),
        "postmortem": state.get("postmortem"),
        "execution_history": list(state.get("execution_history", []))
    }
    state["snapshots"].append(snapshot)
    
    incident_id = state.get("incident_id")
    if incident_id and incident_id in incident_queues:
        for q, loop in incident_queues[incident_id]:
            try:
                loop.call_soon_threadsafe(q.put_nowait, {
                    "event": "step",
                    "message": msg,
                    "state": {
                        "status": state.get("status"),
                        "service": state.get("service"),
                        "severity": state.get("severity"),
                        "logs": state.get("logs"),
                        "metrics": state.get("metrics"),
                        "deploys": state.get("deploys"),
                        "runbooks": state.get("runbooks"),
                        "dependencies": state.get("dependencies"),
                        "hypotheses": state.get("hypotheses"),
                        "recovery_plan": state.get("recovery_plan"),
                        "postmortem": state.get("postmortem"),
                        "execution_history": state.get("execution_history"),
                        "snapshots": state.get("snapshots", [])
                    }
                })
            except Exception:
                pass

def fetch_container_logs(container_name: str) -> List[str]:
    """Tries to query live logs from Docker. Falls back to empty list on failure."""
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", "40", container_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3.0
        )
        if result.returncode == 0:
            lines = [line.strip() for line in result.stdout.split("\n") if line.strip()]
            return lines
    except Exception as exc:
        print(f"[LOG INVESTIGATOR] Failed to query Docker logs for '{container_name}': {str(exc)}")
    return []

def get_realistic_mock_logs(service: str, alertname: str) -> List[str]:
    """Generates high-fidelity mock SRE logs matching failure scenarios."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    if "payment" in service:
        if "Latency" in alertname or "HighLatency" in alertname:
            return [
                f"{timestamp} [uvicorn.access] 172.18.0.4:50231 - POST /payments HTTP/1.1 200 OK",
                f"{timestamp} [WARNING] payment_processor: database query latency detected: 2.84s on read transaction",
                f"{timestamp} [uvicorn.access] 172.18.0.4:50234 - POST /payments HTTP/1.1 504 Gateway Timeout",
                f"{timestamp} [ERROR] database_pool: connection acquisition timed out after 3.0s",
                f"{timestamp} [ERROR] DatabaseSaturation: Max connection limit reached on db host."
            ]
        else:
            return [
                f"{timestamp} [uvicorn.access] 172.18.0.4:50231 - POST /payments HTTP/1.1 200 OK",
                f"{timestamp} [ERROR] payment_processor: failed to process credit transaction tx_9238472",
                f"{timestamp} [ERROR] sqlite3.OperationalError: database is locked",
                f"{timestamp} [uvicorn.access] 172.18.0.4:50239 - POST /payments HTTP/1.1 500 Internal Server Error"
            ]
    elif "order" in service:
        if "memory" in alertname or "leak" in alertname or "Leak" in alertname:
            return [
                f"{timestamp} [INFO] order_service: processing checkout request for user 24",
                f"{timestamp} [INFO] order_cache: allocated cached elements. Heap size: 142MB",
                f"{timestamp} [INFO] order_cache: allocated cached elements. Heap size: 284MB",
                f"{timestamp} [INFO] order_cache: allocated cached elements. Heap size: 568MB",
                f"{timestamp} [WARNING] GC: garbage collection cycle completed but freed 0 bytes. Heap high."
            ]
        else:
            return [
                f"{timestamp} [uvicorn.access] 172.18.0.1:41203 - POST /orders HTTP/1.1 200 OK",
                f"{timestamp} [ERROR] httpx.ConnectTimeout: httpx.ConnectTimeout connecting to payment-service:8013",
                f"{timestamp} [uvicorn.access] 172.18.0.1:41208 - POST /orders HTTP/1.1 502 Bad Gateway"
            ]
    elif "user" in service:
        return [
            f"{timestamp} [INFO] user_service: loaded schema migrations v1.0.0",
            f"{timestamp} [ERROR] config_loader: parameter 'JWT_SECRET_KEY' is missing or corrupted",
            f"{timestamp} [ERROR] ConfigRegressionError: failed to load context variables on user initialization",
            f"{timestamp} [uvicorn.access] 172.18.0.2:48102 - GET /users/14 HTTP/1.1 500 Internal Server Error"
        ]
    return [
        f"{timestamp} [INFO] Server started successfully.",
        f"{timestamp} [INFO] Listening on port 80",
        f"{timestamp} [INFO] Health status: OK"
    ]

# ----------------- AGENT NODES -----------------

def supervisor_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Supervisor: Inciting multi-agent SRE investigation workspace.")
    state["status"] = "investigating"
    return {"status": "investigating", "execution_history": state["execution_history"]}

def alert_triage_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Alert Triage Agent: Actively parsing Prometheus alert payload details...")
    
    alert_info = state["alert_payload"].get("alerts", [{}])[0]
    labels = alert_info.get("labels", {})
    annotations = alert_info.get("annotations", {})
    
    alertname = labels.get("alertname", "UnknownAlert")
    service = labels.get("service", labels.get("job", "unknown-service"))
    severity = labels.get("severity", "info")
    summary = annotations.get("summary", "No summary provided.")
    description = annotations.get("description", "No description provided.")
    
    prompt = f"""
You are an expert Alert Triage SRE Agent. Analyze this raw Prometheus alert payload:
- Alert Name: {alertname}
- Impacted Service Label: {service}
- Severity: {severity}
- Summary: {summary}
- Description: {description}

Determine:
1. The exact service name impacted.
2. The severity rating (INFO, WARNING, CRITICAL).
3. A concise summary of the issue.
Format your response clearly.
"""
    response = llm.invoke(prompt)
    log_step(state, f"Alert Triage Agent - LLM Analysis:\n{response.content}")
    
    state["service"] = service
    state["severity"] = severity
    state["status"] = "triaged"
    
    log_step(state, f"Alert Triage Agent: Triage outcome finalized for service '{service}'.")
    return {
        "service": service,
        "severity": severity,
        "status": "triaged",
        "execution_history": state["execution_history"]
    }

def logs_investigator_node(state: IncidentState) -> Dict[str, Any]:
    service = state["service"]
    alert_info = state["alert_payload"].get("alerts", [{}])[0]
    alertname = alert_info.get("labels", {}).get("alertname", "UnknownAlert")
    
    log_step(state, f"Logs Investigator: Fetching server log logs for service '{service}'...")
    
    # Standard MCP Tool invocation
    mcp_result = call_mcp_tool("query_logs", {"service": service, "alertname": alertname})
    logs = mcp_result.get("raw_list", [])
    
    log_step(state, f"Logs Investigator: Successfully extracted {len(logs)} live lines from Docker container.")
        
    log_dump = "\n".join(logs)
    prompt = f"""
You are an expert SRE Log Investigator Agent. Analyze the stdout/stderr server logs for '{service}':

```text
{log_dump}
```

Identify:
1. Repeating warning/error stack traces or anomalies.
2. The key evidence log lines with citations.
3. Your diagnosis of the immediate service failure.
Format your output concisely.
"""
    response = llm.invoke(prompt)
    log_step(state, f"Logs Investigator - LLM Analysis:\n{response.content}")
    
    state["logs"][service] = logs
    return {"logs": state["logs"], "execution_history": state["execution_history"]}

def fetch_simulated_deploys(service: str) -> List[Dict[str, Any]]:
    """Simulate querying a git deploy registry / release tag log."""
    simulated_deploys = [
        {"version": "v1.0.8", "timestamp": "2026-06-02T10:00:00Z", "author": "dev-sanjay", "commit": "a82f31", "status": "stable"},
        {"version": "v1.0.9", "timestamp": "2026-06-02T14:10:00Z", "author": "DeployBot", "commit": "f938d2", "status": "stable"}
    ]
    if "user" in service.lower():
        simulated_deploys.append(
            {"version": "v1.1.0", "timestamp": "2026-06-02T15:35:00Z", "author": "dev-sanjay", "commit": "b02d84", "status": "failed", "details": "Injected bad parameter key regression"}
        )
    else:
        simulated_deploys.append(
            {"version": "v1.0.9", "timestamp": "2026-06-02T14:10:00Z", "author": "DeployBot", "commit": "f938d2", "status": "active"}
        )
    return simulated_deploys

def deploy_detective_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Deploy Detective: Querying system change logs and git deploy registries...")
    
    simulated_deploys = fetch_simulated_deploys(state["service"])
        
    prompt = f"""
You are an expert SRE Deploy Detective Agent. Review these recent deployments:
{simulated_deploys}

Assess if any recent deployment could explain an alert on service '{state['service']}'.
Summarize your assessment and identify if a rollback is recommended.
"""
    response = llm.invoke(prompt)
    log_step(state, f"Deploy Detective - LLM Analysis:\n{response.content}")
    
    state["deploys"] = simulated_deploys
    return {"deploys": state["deploys"], "execution_history": state["execution_history"]}

def runbook_docs_node(state: IncidentState) -> Dict[str, Any]:
    service = state["service"]
    log_step(state, f"Runbook Assistant: Searching matching runbooks under backend/runbooks/ directory for service '{service}'...")
    
    # Standard MCP Tool invocation
    mcp_result = call_mcp_tool("search_runbooks", {"service": service})
    runbooks = mcp_result.get("runbooks", [])
    
    log_step(state, f"Runbook Assistant: Located and loaded matching runbook via MCP.")
        
    prompt = f"""
You are an expert SRE Runbook Assistant. Review the extracted runbooks for service '{service}':
{runbooks}

Summarize the appropriate action items and verification procedures matching this failure profile.
"""
    response = llm.invoke(prompt)
    log_step(state, f"Runbook Assistant - LLM Analysis:\n{response.content}")
    
    state["runbooks"] = runbooks
    return {"runbooks": state["runbooks"], "execution_history": state["execution_history"]}

# ----------------- STUBS (Fleshed out in future steps) -----------------

def query_prometheus_metric(query_str: str) -> float:
    """Safely queries Prometheus container API, returning float result or 0.0."""
    try:
        url = "http://localhost:9090/api/v1/query"
        response = httpx.get(url, params={"query": query_str}, timeout=2.0)
        if response.status_code == 200:
            data = response.json()
            results = data.get("data", {}).get("result", [])
            if results:
                val = results[0].get("value", [None, "0.0"])[1]
                return round(float(val), 3)
    except Exception as exc:
        print(f"[METRICS ANALYST] Prometheus unreachable: {str(exc)}")
    return 0.0

def get_realistic_mock_metrics(service: str, alertname: str) -> Dict[str, Any]:
    """Generates high-fidelity mock metrics if Prometheus is unreachable."""
    if "payment" in service:
        if "Latency" in alertname or "HighLatency" in alertname:
            return {"cpu_usage_pct": 92.4, "memory_usage_mb": 256, "http_5xx_rate": 0.05, "average_latency_ms": 2840}
        else:
            return {"cpu_usage_pct": 45.1, "memory_usage_mb": 190, "http_5xx_rate": 0.24, "average_latency_ms": 110}
    elif "order" in service:
        if "Memory" in alertname or "leak" in alertname or "Leak" in alertname:
            return {"cpu_usage_pct": 58.2, "memory_usage_mb": 512, "http_5xx_rate": 0.02, "average_latency_ms": 85}
        else:
            return {"cpu_usage_pct": 34.0, "memory_usage_mb": 128, "http_5xx_rate": 0.12, "average_latency_ms": 140}
    elif "user" in service:
        return {"cpu_usage_pct": 28.5, "memory_usage_mb": 96, "http_5xx_rate": 0.38, "average_latency_ms": 45}
    return {"cpu_usage_pct": 10.0, "memory_usage_mb": 64, "http_5xx_rate": 0.0, "average_latency_ms": 5}

def metrics_analyst_node(state: IncidentState) -> Dict[str, Any]:
    service = state["service"]
    alert_info = state["alert_payload"].get("alerts", [{}])[0]
    alertname = alert_info.get("labels", {}).get("alertname", "UnknownAlert")
    
    log_step(state, f"Metrics Analyst: Fetching Prometheus CPU/Memory metrics trends for '{service}'...")
    
    # Standard MCP Tool invocation
    mcp_result = call_mcp_tool("query_metrics", {"service": service, "alertname": alertname})
    metrics = mcp_result.get("metrics", {})
    
    log_step(state, f"Metrics Analyst: Successfully scraped live metric indicators via MCP.")
        
    prompt = f"""
You are an expert SRE Metrics Analyst Agent. Analyze the retrieved service metrics for '{service}':
- CPU Saturation: {metrics['cpu_usage_pct']}%
- Memory footprint: {metrics['memory_usage_mb']} MB
- HTTP 5xx Error Rate: {metrics['http_5xx_rate'] * 100}%
- Average Response Latency: {metrics['average_latency_ms']} ms

Identify any performance thresholds violated, anomalies, or system constraints.
"""
    response = llm.invoke(prompt)
    log_step(state, f"Metrics Analyst - LLM Analysis:\n{response.content}")
    
    state["metrics"][service] = metrics
    return {"metrics": state["metrics"], "execution_history": state["execution_history"]}

def dependency_graph_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Dependency Detective: Computing service dependency topology...")
    
    nodes = [
        {"id": "user-service", "label": "User Profile API", "status": "healthy" if "user" not in state["service"].lower() else "error"},
        {"id": "order-service", "label": "Order Orchestrator", "status": "healthy" if "order" not in state["service"].lower() else "error"},
        {"id": "payment-service", "label": "Payment Processor", "status": "healthy" if "payment" not in state["service"].lower() else "error"}
    ]
    
    edges = [
        {"from": "order-service", "to": "user-service", "label": "HTTP/1.1"},
        {"from": "order-service", "to": "payment-service", "label": "HTTP/1.1"}
    ]
    
    state["dependencies"] = {
        "nodes": nodes,
        "edges": edges,
        "root_service": state["service"]
    }
    
    log_step(state, f"Dependency Detective: Identified failed root node '{state['service']}' and mapped network edges.")
    return {"dependencies": state["dependencies"], "execution_history": state["execution_history"]}

def root_cause_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Root Cause Agent: Aggregating logs, metrics, deploys, runbooks, and dependency topology...")
    
    service = state["service"]
    alert_info = state["alert_payload"].get("alerts", [{}])[0]
    alertname = alert_info.get("labels", {}).get("alertname", "UnknownAlert")
    
    logs = state["logs"].get(service, [])
    metrics = state["metrics"].get(service, {})
    deploys = state["deploys"]
    runbooks = state["runbooks"]
    dependencies = state["dependencies"]
    
    # Query semantic memory store for historical incident context
    past_memories = retrieve_relevant_memories(service, alertname)
    if past_memories:
        log_step(state, f"Root Cause Agent: Retrieved {len(past_memories)} relevant past incident records from long-term semantic memory.")
    else:
        log_step(state, "Root Cause Agent: No matching historical memories found in semantic store.")
        
    prompt = f"""
You are the lead SRE Root Cause Analyst Agent (Deep Agent). Your goal is to analyze the gathered system metrics, logs, git release history, operational runbooks, and topology to formulate the top 3 root-cause hypotheses for this incident.

ALERT DETAILS:
- Alert Name: {alertname}
- Impacted Service: {service}

GATHERED EVIDENCE:
1. Logs:
{logs}

2. Performance Metrics:
{metrics}

3. Recent Deployment/Change Logs:
{deploys}

4. Matching Runbook:
{runbooks}

5. Infrastructure Topology:
{dependencies}

6. Historical SRE Learnings (Long-Term Memory):
{past_memories}

Formulate the top 3 root cause hypotheses. Consider past incident matches to correlate telemetry spikes with verified history.
For EACH hypothesis, you MUST specify:
- Rank (1, 2, or 3)
- Hypothesis title
- Confidence score (a float between 0.0 and 1.0)
- Detailed reasoning / rationale citing exact log lines, metrics values, deploy versions, or historical parallels
- Evidence source (e.g. Logs, Deploy Detective, Semantic Memory)

Be extremely precise. Do not guess or hallucinate without referencing the gathered evidence.
Format your output exactly as a JSON list, matching this structure:
[
  {{
    "rank": 1,
    "hypothesis": "Hypothesis title here",
    "confidence": 0.90,
    "rationale": "Reasoning explaining why citing logs/metrics/deploy lines...",
    "evidence": "Logs & Metrics spikes"
  }}
]
Ensure your response is ONLY the raw JSON list block so it can be parsed cleanly.
"""
    response = llm.invoke(prompt)
    content = response.content.strip()
    
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
        content = content.strip()
        
    try:
        hypotheses = json.loads(content)
        state["hypotheses"] = hypotheses
        log_step(state, f"Root Cause Agent: Formulated {len(hypotheses)} root-cause hypotheses with LLM reasoning.")
    except Exception as exc:
        print(f"[ROOT CAUSE] Failed to parse LLM JSON response: {content}. Error: {str(exc)}")
        log_step(state, "[ROOT CAUSE] Failed to parse LLM JSON response. Falling back to structured default hypotheses.")
        
        if "payment" in service:
            state["hypotheses"] = [
                {
                    "rank": 1,
                    "hypothesis": "Database pool saturation on payment-service",
                    "confidence": 0.88,
                    "rationale": "Logs cite 'Max connection limit reached on db host'. Latency exceeds 2500ms.",
                    "evidence": "Logs & Prometheus latency metrics"
                },
                {
                    "rank": 2,
                    "hypothesis": "Cascading timeout blockages in checkout transactions",
                    "confidence": 0.45,
                    "rationale": "High downstream delays propagate bottleneck calls upstream to order-service.",
                    "evidence": "Metrics analysis"
                }
            ]
        elif "order" in service:
            state["hypotheses"] = [
                {
                    "rank": 1,
                    "hypothesis": "Retained cache memory leak in order-service caching loops",
                    "confidence": 0.95,
                    "rationale": "Heap footprints expanded rapidly from 142MB to 568MB within 10 seconds, matching GC failure warnings.",
                    "evidence": "Logs and heap metrics trends"
                }
            ]
        else:
            state["hypotheses"] = [
                {
                    "rank": 1,
                    "hypothesis": "JWT validation token configuration regression in v1.1.0 release",
                    "confidence": 0.90,
                    "rationale": "Alert started shortly after deployment of v1.1.0, throwing parameter loading errors in user profile route.",
                    "evidence": "Deploy Detective logs and 500 error stack trace"
                }
            ]
            
    return {"hypotheses": state["hypotheses"], "execution_history": state["execution_history"]}

def recovery_planner_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Recovery Planner Agent: Formulating customized mitigation actions plan...")
    
    service = state["service"]
    runbooks = state["runbooks"]
    hypotheses = state["hypotheses"]
    
    top_hypothesis = hypotheses[0] if hypotheses else {"hypothesis": "Unknown service failure", "rationale": "No hypothesis isolated."}
    
    prompt = f"""
You are an expert SRE Recovery Planner Agent. Your goal is to review the top isolated root-cause hypothesis and the matched operational runbook steps to formulate a safe, actionable mitigation recovery plan for the failed service '{service}'.

TOP DIAGNOSED HYPOTHESIS:
- Hypothesis: {top_hypothesis.get('hypothesis')}
- Rationale: {top_hypothesis.get('rationale')}

EXTRACTED RUNBOOK GUIDELINES:
{runbooks}

Determine:
1. The exact step-by-step action list to safely resolve the issue (e.g. restart container, scale connections limit, rollback config release, clear cache pool).
2. The mitigation action type (e.g. 'restart_service', 'rollback_deploy', 'scale_db_limits', 'clear_cache').
3. A safety level rating ('safe' - zero traffic risk, 'moderate' - minor impact possibility, 'risky' - potential read disruption).
4. The expected impact on active client requests.

Be extremely precise. Recommend safe actions. Avoid destructive commands.
Format your output exactly as a JSON dictionary matching this structure:
{{
  "action": "Description of exact mitigation steps here",
  "type": "restart_service" | "rollback_deploy" | "scale_db_limits" | "clear_cache",
  "safety_level": "safe" | "moderate" | "risky",
  "impact": "Description of expected impact on users during mitigation..."
}}
Ensure your response is ONLY the raw JSON dictionary block.
"""
    response = llm.invoke(prompt)
    content = response.content.strip()
    
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
        content = content.strip()
        
    try:
        plan = json.loads(content)
        state["recovery_plan"] = plan
        log_step(state, f"Recovery Planner Agent: Successfully formulated dynamic plan: '{plan['action']}'.")
    except Exception as exc:
        print(f"[RECOVERY PLANNER] Failed to parse LLM JSON response: {content}. Error: {str(exc)}")
        log_step(state, "[RECOVERY PLANNER] Failed to parse LLM response. Falling back to default runbook guidelines.")
        
        if "payment" in service:
            state["recovery_plan"] = {
                "action": "Scale database connections limit to 100 and restart payment-service container.",
                "type": "scale_db_limits",
                "safety_level": "safe",
                "impact": "None expected, read-only cache handles client checkout queries during connection resize."
            }
        elif "order" in service:
            state["recovery_plan"] = {
                "action": "Clear accumulating cached dictionary memory blocks and restart order-service.",
                "type": "clear_cache",
                "safety_level": "safe",
                "impact": "None expected, clients can re-verify orders from database queries."
            }
        else:
            state["recovery_plan"] = {
                "action": "Roll back recent user-service build version v1.1.0 to stable release v1.0.9.",
                "type": "rollback_deploy",
                "safety_level": "moderate",
                "impact": "Minor 2-second token validation delay during container checkout rotation."
            }
            
    state["status"] = "recovery_pending"
    return {
        "recovery_plan": state["recovery_plan"], 
        "status": "recovery_pending", 
        "execution_history": state["execution_history"]
    }

def postmortem_writer_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Postmortem Agent: Compiling final summary narrative...")
    
    service = state["service"]
    incident_id = state["incident_id"]
    severity = state["severity"]
    hypotheses = state["hypotheses"]
    recovery_plan = state["recovery_plan"]
    logs = state["logs"].get(service, [])
    metrics = state["metrics"].get(service, {})
    deploys = state["deploys"]
    history = state["execution_history"]
    approval_status = state.get("approval_status", "approved")
    
    top_hypothesis = hypotheses[0] if hypotheses else {"hypothesis": "Unknown service failure", "rationale": "No hypothesis isolated."}
    
    prompt = f"""
You are the Lead SRE Postmortem Writer Agent. Your goal is to compile a detailed, professional SRE Postmortem report in Markdown format for the resolved incident '{incident_id}'.

INCIDENT META:
- Incident ID: {incident_id}
- Affected Service: {service}
- Severity: {severity}
- Mitigation Status: {approval_status}

GATHERED TELEMETRY & CONTEXT:
- Top Hypothesis: {top_hypothesis.get('hypothesis')}
- Hypothesis Rationale: {top_hypothesis.get('rationale')}
- Mitigation Action Executed: {recovery_plan.get('action', 'N/A')}
- Recent Logs: {logs}
- Performance Metrics: {metrics}
- Recent Deployments: {deploys}
- Multi-Agent Orchestration Trail: {history}

Your postmortem report MUST be structured in clean Markdown with the following section headers:
1. `# SRE Incident Postmortem: {incident_id}`
2. `## Executive Summary`: High-level summary of the outage, impact, and mitigation.
3. `## Root Cause Analysis (RCA)`: In-depth explanation of the root cause, citing exact evidence from the logs, metrics, or deployments.
4. `## Detailed Incident Timeline`: Formatted bulleted chronological list showing the progression of events, from alert firing, triage, agents analysis, human gate approval, to recovery.
5. `## Resolution & Verification`: Detailed explanation of the recovery action, operator decision, and proof of recovery.
6. `## Corrective & Preventative Action Items`: Action items to prevent recurrence.

Do not guess or hallucinate details that are not supported by the telemetry. Keep the tone professional, objective, and blameless. Return ONLY the markdown document content.
"""
    response = llm.invoke(prompt)
    postmortem = response.content.strip()
    
    state["postmortem"] = postmortem
    state["status"] = "recovered"
    log_step(state, "Postmortem Agent: Postmortem report rendered successfully.")
    return {"postmortem": postmortem, "status": "recovered", "execution_history": state["execution_history"]}

def memory_curator_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Memory Curator: Storing lessons-learned in long-term memory...")
    
    service = state["service"]
    incident_id = state["incident_id"]
    severity = state["severity"]
    hypotheses = state["hypotheses"]
    recovery_plan = state["recovery_plan"]
    history = state["execution_history"]
    alert_info = state["alert_payload"].get("alerts", [{}])[0]
    alertname = alert_info.get("labels", {}).get("alertname", "UnknownAlert")
    
    top_hypothesis = hypotheses[0] if hypotheses else {"hypothesis": "Unknown service failure", "rationale": "No hypothesis isolated."}
    
    prompt = f"""
You are the Lead SRE Memory Curator Agent. Your goal is to review the resolved incident context and distill the primary lessons-learned into a structured JSON memory object.

RESOLVED INCIDENT CONTEXT:
- Incident ID: {incident_id}
- Affected Service: {service}
- Alert Name: {alertname}
- Severity: {severity}
- Top Hypothesis: {top_hypothesis.get('hypothesis')}
- Mitigation Taken: {recovery_plan.get('action')}
- Execution history: {history}

Format your output exactly as a JSON dictionary matching this structure:
{{
  "incident_id": "{incident_id}",
  "service": "{service}",
  "alertname": "{alertname}",
  "root_cause": "{top_hypothesis.get('hypothesis')}",
  "evidence": "{top_hypothesis.get('rationale')}",
  "mitigation": "{recovery_plan.get('action')}",
  "key_learnings": "Long-term architectural key learning points or preventative actions..."
}}
Ensure your response is ONLY the raw JSON dictionary block.
"""
    try:
        response = llm.invoke(prompt)
        content = response.content.strip()
        
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if lines[-1].startswith("```") else "\n".join(lines[1:])
            content = content.strip()
            
        memory_data = json.loads(content)
        save_memory(memory_data)
        log_step(state, f"Memory Curator: Distilled experience and saved lesson-learned under ID: {memory_data.get('incident_id')}.")
    except Exception as exc:
        print(f"[MEMORY CURATOR] Failed to parse or save LLM JSON response: {str(exc)}")
        # Fallback manual extraction to prevent graph crash
        fallback_data = {
            "incident_id": incident_id,
            "service": service,
            "alertname": alertname,
            "root_cause": top_hypothesis.get("hypothesis"),
            "evidence": top_hypothesis.get("rationale"),
            "mitigation": recovery_plan.get("action"),
            "key_learnings": "Verify telemetry metrics saturation patterns and scale pool/caches proactively."
        }
        save_memory(fallback_data)
        log_step(state, "Memory Curator: Successfully saved incident fallback memory record.")
        
    return {"execution_history": state["execution_history"]}
