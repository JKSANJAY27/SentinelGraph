import subprocess
import time
import asyncio
from typing import Dict, Any, List
from .state import IncidentState
from ..llm import get_llm

llm = get_llm()

# Global registry of real-time SSE queues for streaming agent updates to the UI
# incident_id -> list of asyncio.Queue
incident_queues: Dict[str, List[asyncio.Queue]] = {}

def register_queue(incident_id: str, queue: asyncio.Queue):
    if incident_id not in incident_queues:
        incident_queues[incident_id] = []
    incident_queues[incident_id].append(queue)

def unregister_queue(incident_id: str, queue: asyncio.Queue):
    if incident_id in incident_queues:
        try:
            incident_queues[incident_id].remove(queue)
        except ValueError:
            pass

def log_step(state: IncidentState, msg: str) -> None:
    """Helper to log agent execution trails and notify live streaming frontend web sockets/SSE."""
    print(f"[AGENT FLOW] {msg}")
    state["execution_history"].append(msg)
    
    incident_id = state.get("incident_id")
    if incident_id and incident_id in incident_queues:
        for q in incident_queues[incident_id]:
            try:
                # Push details to the active event loop queue safely
                loop = asyncio.get_running_loop()
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
                        "execution_history": state.get("execution_history")
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
    
    logs = fetch_container_logs(service)
    if not logs:
        log_step(state, f"Logs Investigator: Container '{service}' not active or offline. Generating high-fidelity mock logs.")
        logs = get_realistic_mock_logs(service, alertname)
    else:
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

# ----------------- STUBS -----------------

def metrics_analyst_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, f"Metrics Analyst: Fetching prometheus CPU/Memory trends for '{state['service']}'...")
    state["metrics"][state["service"]] = {
        "cpu_usage_pct": 87.5,
        "memory_usage_mb": 412,
        "http_5xx_rate": 0.24,
        "average_latency_ms": 1240
    }
    log_step(state, "Metrics Analyst: Gained performance data spikes.")
    return {"metrics": state["metrics"], "execution_history": state["execution_history"]}

def deploy_detective_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Deploy Detective: Inspecting change registry logs...")
    state["deploys"] = [
        {"version": "1.0.0", "timestamp": "2026-06-02T15:00:00Z", "author": "DeployBot", "status": "active"},
        {"version": "1.1.0-bad", "timestamp": "2026-06-02T15:35:00Z", "author": "dev-sanjay", "status": "failed"}
    ]
    log_step(state, f"Deploy Detective: Found {len(state['deploys'])} recent deployments.")
    return {"deploys": state["deploys"], "execution_history": state["execution_history"]}

def runbook_docs_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, f"Runbook Assistant: Scanning static knowledge base documents for service '{state['service']}'...")
    state["runbooks"] = [
        {
            "title": "Payment Service Outage Recovery",
            "steps": "1. Check DB connections. 2. Scale connections list. 3. Restart payment service container if latency is high."
        }
    ]
    log_step(state, "Runbook Assistant: Extracted 1 matching runbook document.")
    return {"runbooks": state["runbooks"], "execution_history": state["execution_history"]}

def dependency_graph_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Dependency Detective: Computing service dependency topology...")
    state["dependencies"] = {
        "nodes": ["user-service", "order-service", "payment-service"],
        "edges": [
            {"from": "order-service", "to": "user-service"},
            {"from": "order-service", "to": "payment-service"}
        ]
    }
    log_step(state, "Dependency Detective: Formulated architecture map.")
    return {"dependencies": state["dependencies"], "execution_history": state["execution_history"]}

def root_cause_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Root Cause Agent: Aggregating logs, metrics, deploys, and runbooks...")
    state["hypotheses"] = [
        {
            "rank": 1,
            "hypothesis": f"Database Connection Exhaustion in {state['service']}",
            "confidence": 0.85,
            "rationale": "High connection times coupled with log error 'Max connection limit reached' matches standard pool saturation.",
            "evidence": "Logs & Metrics spikes"
        },
        {
            "rank": 2,
            "hypothesis": f"Deploy config regression on {state['service']}",
            "confidence": 0.50,
            "rationale": "Incident started shortly after release of v1.1.0.",
            "evidence": "Deploy Detective logs"
        }
    ]
    log_step(state, f"Root Cause Agent: Discovered {len(state['hypotheses'])} likely causes.")
    return {"hypotheses": state["hypotheses"], "execution_history": state["execution_history"]}

def recovery_planner_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Recovery Planner: Formulating mitigation actions list...")
    state["recovery_plan"] = {
        "action": "Restart container & scale DB pool connection limit to 100",
        "type": "restart_and_scale",
        "safety_level": "safe",
        "impact": "None expected, read-only cache handles client orders during transition"
    }
    state["status"] = "recovery_pending"
    log_step(state, f"Recovery Planner: Recommended action plan: '{state['recovery_plan']['action']}'.")
    return {
        "recovery_plan": state["recovery_plan"], 
        "status": "recovery_pending", 
        "execution_history": state["execution_history"]
    }

def postmortem_writer_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Postmortem Agent: Compiling final summary narrative...")
    state["postmortem"] = f"""# SRE Incident Postmortem
## Incident ID: {state['incident_id']}
- **Service Affected**: {state['service']}
- **Severity**: {state['severity'].upper()}
- **Root Cause**: {state['hypotheses'][0]['hypothesis']}
- **Mitigation Taken**: {state['recovery_plan']['action']}

### Timeline
- **Incident Fired**: Alert received.
- **Root Cause Isolated**: 95% certainty connection issue.
- **Mitigation Approved**: Container scale-up action applied successfully.
"""
    state["status"] = "recovered"
    log_step(state, "Postmortem Agent: Postmortem report rendered successfully.")
    return {"postmortem": state["postmortem"], "status": "recovered", "execution_history": state["execution_history"]}

def memory_curator_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Memory Curator: Storing lessons-learned in long-term memory...")
    log_step(state, "Memory Curator: Incident memory saved.")
    return {"execution_history": state["execution_history"]}
