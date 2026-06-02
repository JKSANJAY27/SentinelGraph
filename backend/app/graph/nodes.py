import random
from typing import Dict, Any
from .state import IncidentState

# Helper to log actions
def log_step(state: IncidentState, msg: str) -> None:
    print(f"[AGENT FLOW] {msg}")
    state["execution_history"].append(msg)

def supervisor_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Supervisor: Inciting multi-agent investigation workspace.")
    # In supervisor, we decide next nodes. For this initial setup, we transition status.
    state["status"] = "investigating"
    return {"status": "investigating", "execution_history": state["execution_history"]}

def alert_triage_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, "Alert Triage: Isolating target system from alert labels.")
    alert_info = state["alert_payload"].get("alerts", [{}])[0]
    labels = alert_info.get("labels", {})
    annotations = alert_info.get("annotations", {})
    
    state["service"] = labels.get("service", labels.get("job", "unknown-service"))
    state["severity"] = labels.get("severity", "info")
    state["status"] = "triaged"
    
    log_step(state, f"Alert Triage: Mapped alert to service '{state['service']}' (Severity: {state['severity']}).")
    return {
        "service": state["service"],
        "severity": state["severity"],
        "status": "triaged",
        "execution_history": state["execution_history"]
    }

def logs_investigator_node(state: IncidentState) -> Dict[str, Any]:
    log_step(state, f"Logs Investigator: Fetching server log logs for service '{state['service']}'...")
    # Gather logs (will be fully integrated in Step 1.5)
    mock_logs = [
        "[INFO] Server listening on port 8013",
        "[INFO] Database connection pool established.",
        "[WARNING] Transaction query took longer than expected: 2.1s",
        "[ERROR] DatabaseSaturation: Max connection limit reached on db host."
    ]
    state["logs"][state["service"]] = mock_logs
    log_step(state, f"Logs Investigator: Retrieved {len(mock_logs)} log events.")
    return {"logs": state["logs"], "execution_history": state["execution_history"]}

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
    # Reasoning logic stub
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
