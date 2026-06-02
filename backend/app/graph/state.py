from typing import TypedDict, List, Dict, Any, Optional

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
    execution_history: List[str]         # Auditing/run state history log
