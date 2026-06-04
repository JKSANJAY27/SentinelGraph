from typing import TypedDict, List, Dict, Any, Optional, Annotated

def merge_execution_history(left: List[str], right: List[str]) -> List[str]:
    """Reducer to merge execution history lists concurrently without duplicates."""
    merged = list(left or [])
    for item in (right or []):
        if item not in merged:
            merged.append(item)
    return merged

def merge_snapshots(left: List[Dict[str, Any]], right: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Reducer to merge snapshots list concurrently without duplicates."""
    merged = list(left or [])
    for item in (right or []):
        if not any(x.get("step_index") == item.get("step_index") for x in merged):
            merged.append(item)
    return merged

class IncidentState(TypedDict):
    # Incident core identification
    incident_id: str
    alert_payload: Dict[str, Any]
    service: str
    severity: str
    status: str  # active, triaged, investigating, recovery_pending, recovered, postmortem_written
    
    # Evidence gathered
    logs: Dict[str, List[str]]           # Service name -> log lists
    metrics: Dict[str, Dict[str, Any]]  # Service name -> prometheus metrics
    deploys: List[Dict[str, Any]]       # Recent git/deploy releases
    dependencies: Dict[str, Any]         # Network mapping topology
    runbooks: List[Dict[str, Any]]       # Recommended operations guidelines
    
    # Reasoning outcomes
    hypotheses: List[Dict[str, Any]]     # Root cause hypotheses with score & citation
    recovery_plan: Dict[str, Any]       # Suggested recovery action list
    postmortem: Optional[str]            # Final markdown postmortem
    
    # Human approval state
    approval_status: Optional[str]       # pending, approved, rejected
    approval_comments: Optional[str]
    
    # Audit trail
    execution_history: Annotated[List[str], merge_execution_history]         # Auditing/run state history log
    snapshots: Annotated[List[Dict[str, Any]], merge_snapshots]

