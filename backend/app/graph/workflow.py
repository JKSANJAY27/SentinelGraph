from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from .state import IncidentState
from .nodes import (
    supervisor_node,
    alert_triage_node,
    logs_investigator_node,
    metrics_analyst_node,
    deploy_detective_node,
    runbook_docs_node,
    dependency_graph_node,
    root_cause_node,
    recovery_planner_node,
    postmortem_writer_node,
    memory_curator_node
)

def create_incident_workflow():
    workflow = StateGraph(IncidentState)
    
    # Add nodes
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("alert_triage", alert_triage_node)
    workflow.add_node("logs_investigator", logs_investigator_node)
    workflow.add_node("metrics_analyst", metrics_analyst_node)
    workflow.add_node("deploy_detective", deploy_detective_node)
    workflow.add_node("runbook_docs", runbook_docs_node)
    workflow.add_node("dependency_graph", dependency_graph_node)
    workflow.add_node("root_cause", root_cause_node)
    workflow.add_node("recovery_planner", recovery_planner_node)
    workflow.add_node("postmortem_writer", postmortem_writer_node)
    workflow.add_node("memory_curator", memory_curator_node)
    
    # Set entry point
    workflow.set_entry_point("supervisor")
    
    # Supervisor -> Alert Triage
    workflow.add_edge("supervisor", "alert_triage")
    
    # Parallel Specialist Fan-Out
    workflow.add_edge("alert_triage", "logs_investigator")
    workflow.add_edge("alert_triage", "metrics_analyst")
    workflow.add_edge("alert_triage", "deploy_detective")
    workflow.add_edge("alert_triage", "runbook_docs")
    workflow.add_edge("alert_triage", "dependency_graph")
    
    # Fan-In to Root Cause reasoning
    workflow.add_edge("logs_investigator", "root_cause")
    workflow.add_edge("metrics_analyst", "root_cause")
    workflow.add_edge("deploy_detective", "root_cause")
    workflow.add_edge("runbook_docs", "root_cause")
    workflow.add_edge("dependency_graph", "root_cause")
    
    # Mitigation execution flow
    workflow.add_edge("root_cause", "recovery_planner")
    workflow.add_edge("recovery_planner", "postmortem_writer")
    workflow.add_edge("postmortem_writer", "memory_curator")
    workflow.add_edge("memory_curator", END)
    
    # Compile graph with MemorySaver checkpointer
    checkpointer = MemorySaver()
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["postmortem_writer"]
    )

