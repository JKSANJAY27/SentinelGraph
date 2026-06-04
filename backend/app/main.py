import time
import json
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables from backend/ or project root
load_dotenv()
parent_env = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
if os.path.exists(parent_env):
    load_dotenv(parent_env)

from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List

from .database import Base, engine, get_db
from .models import Incident
from .schemas import AlertmanagerWebhook, IncidentResponse, ApprovalRequest
from .graph.workflow import create_incident_workflow
from .graph.nodes import register_queue, unregister_queue
from .mcp.mcp_server import mcp_server

# Initialize DB Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="SentinelGraph AI Incident Commander Backend", version="1.0.0")

# Setup CORS for Vite UI Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Compile LangGraph Workflow
incident_graph = create_incident_workflow()

def run_incident_graph_async(incident_id: str, initial_state: dict):
    """Executes the LangGraph Multi-Agent reasoning chain in a separate worker thread."""
    db = SessionLocal = sessionmaker = None
    from .database import SessionLocal
    
    db = SessionLocal()
    try:
        # Setup Langfuse callbacks if enabled in environment
        callbacks = []
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            try:
                from langfuse.langchain import CallbackHandler
                langfuse_handler = CallbackHandler(
                    public_key=os.getenv("LANGFUSE_PUBLIC_KEY")
                )
                callbacks.append(langfuse_handler)
                print("[INFO] Langfuse SRE Agent execution tracing activated.")
            except Exception as langfuse_exc:
                print(f"[WARN] Failed to load Langfuse CallbackHandler: {str(langfuse_exc)}")
                
        # Run graph
        config = {"configurable": {"thread_id": incident_id}, "callbacks": callbacks}
        final_state = incident_graph.invoke(initial_state, config=config)
        
        # Update SQLite DB entry
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if incident:
            incident.status = final_state.get("status", "investigating")
            incident.state_json = final_state
            db.commit()
    except Exception as exc:
        print(f"[ERROR] LangGraph async run failed: {str(exc)}")
        err_history = ["Error: workflow crashed", f"Details: {str(exc)}"]
        err_state = {
            "incident_id": incident_id,
            "status": "error",
            "execution_history": err_history,
            "logs": {},
            "metrics": {},
            "deploys": [],
            "dependencies": {},
            "runbooks": [],
            "hypotheses": [],
            "recovery_plan": {},
            "postmortem": None
        }
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if incident:
            incident.status = "error"
            incident.state_json = err_state
            db.commit()
            
        # Broadcast graph crash to any connected SSE listeners
        from .graph.nodes import incident_queues
        if incident_id in incident_queues:
            for q, loop in incident_queues[incident_id]:
                try:
                    loop.call_soon_threadsafe(q.put_nowait, {
                        "event": "step",
                        "message": f"Critical error: {str(exc)}",
                        "state": err_state
                    })
                except Exception as q_exc:
                    print(f"[WARN] Failed to enqueue error event: {str(q_exc)}")
    finally:
        db.close()

@app.get("/health")
def health():
    return {"status": "ok", "app": "sentinelgraph-backend"}

@app.post("/api/v1/mcp")
def mcp_endpoint(payload: dict):
    """Router endpoint for MCP JSON-RPC 2.0 requests."""
    return mcp_server.dispatch(payload)

@app.post("/api/v1/alerts", response_model=IncidentResponse)
def receive_alert(webhook_data: AlertmanagerWebhook, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    if not webhook_data.alerts:
        raise HTTPException(status_code=400, detail="No alerts found in webhook payload")
        
    alert = webhook_data.alerts[0]
    alertname = alert.labels.get("alertname", "UnknownAlert")
    service = alert.labels.get("service", alert.labels.get("job", "unknown-service"))
    severity = alert.labels.get("severity", "info")
    
    incident_id = f"inc_{int(time.time())}"
    
    # 1. Initialize DB incident
    db_incident = Incident(
        id=incident_id,
        alertname=alertname,
        service=service,
        severity=severity,
        status="active",
        alert_payload=webhook_data.model_dump(),
        state_json={
            "incident_id": incident_id,
            "status": "active",
            "execution_history": ["Supervisor: Readying incident workspace."]
        }
    )
    db.add(db_incident)
    db.commit()
    db.refresh(db_incident)
    
    # 2. Setup initial state
    initial_state = {
        "incident_id": incident_id,
        "alert_payload": webhook_data.model_dump(),
        "service": service,
        "severity": severity,
        "status": "active",
        "logs": {},
        "metrics": {},
        "deploys": [],
        "dependencies": {},
        "runbooks": [],
        "hypotheses": [],
        "recovery_plan": {},
        "postmortem": None,
        "approval_status": None,
        "approval_comments": None,
        "execution_history": ["Supervisor: Readying incident workspace."],
        "snapshots": []
    }
    
    # 3. Trigger LangGraph Multi-Agent workflow in Background
    background_tasks.add_task(run_incident_graph_async, incident_id, initial_state)
    
    return db_incident

@app.get("/api/v1/incidents", response_model=List[IncidentResponse])
def get_incidents(db: Session = Depends(get_db)):
    return db.query(Incident).order_by(Incident.created_at.desc()).all()

@app.get("/api/v1/incidents/{incident_id}", response_model=IncidentResponse)
def get_incident(incident_id: str, db: Session = Depends(get_db)):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident

@app.get("/api/v1/incidents/{incident_id}/stream")
async def stream_incident(incident_id: str):
    """Establishes a Server-Sent Events (SSE) stream for live agent execution updates."""
    queue = asyncio.Queue()
    register_queue(incident_id, queue)
    
    async def event_generator():
        try:
            # Yield initial connect signal
            yield f"event: ping\ndata: {json.dumps({'status': 'connected'})}\n\n"
            
            while True:
                data = await queue.get()
                yield f"event: {data['event']}\ndata: {json.dumps(data)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            unregister_queue(incident_id, queue)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")

def resume_incident_graph_async(incident_id: str, action: str):
    """Resumes the LangGraph workflow from the paused interrupt checkpoint or cancels it."""
    db = None
    from .database import SessionLocal
    db = SessionLocal()
    try:
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            return
        
        state = incident.state_json or {}
        
        callbacks = []
        if os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"):
            try:
                from langfuse.langchain import CallbackHandler
                langfuse_handler = CallbackHandler(
                    public_key=os.getenv("LANGFUSE_PUBLIC_KEY")
                )
                callbacks.append(langfuse_handler)
            except Exception as exc:
                print(f"[WARN] Failed to load Langfuse CallbackHandler: {str(exc)}")
        
        config = {"configurable": {"thread_id": incident_id}, "callbacks": callbacks}
        
        if action == "approve":
            # Add resume entry in execution history
            msg = "Human Operator: Approved mitigation plan. Resuming execution."
            
            service = state.get("service")
            msg_mcp = ""
            if service:
                try:
                    from app.graph.nodes import call_mcp_tool
                    mcp_res = call_mcp_tool("restart_container", {"service": service})
                    msg_mcp = f"Execution Agent: Standard MCP tool triggered: {mcp_res.get('content', [{}])[0].get('text', '')}"
                except Exception as mcp_exc:
                    msg_mcp = f"Execution Agent: Failed to trigger MCP restart container: {str(mcp_exc)}"
                    
            history_update = state.get("execution_history", []) + [msg]
            if msg_mcp:
                history_update.append(msg_mcp)
                
            incident_graph.update_state(config, {
                "approval_status": "approved",
                "execution_history": history_update
            })
            
            # Resume LangGraph by calling invoke with None input
            final_state = incident_graph.invoke(None, config=config)
            
            incident.status = final_state.get("status", "recovered")
            incident.state_json = final_state
            db.commit()
            
            # Broadcast final status
            from .graph.nodes import incident_queues
            if incident_id in incident_queues:
                for q, loop in incident_queues[incident_id]:
                    try:
                        loop.call_soon_threadsafe(q.put_nowait, {
                            "event": "step",
                            "message": msg,
                            "state": final_state
                        })
                    except Exception as q_exc:
                        print(f"[WARN] Failed to broadcast resume: {str(q_exc)}")
        else:
            # Reject
            msg = "Human Operator: Rejected mitigation plan. Aborting execution."
            state["status"] = "rejected"
            state["approval_status"] = "rejected"
            state["execution_history"] = state.get("execution_history", []) + [msg]
            
            incident.status = "rejected"
            incident.state_json = state
            db.commit()
            
            # Broadcast reject
            from .graph.nodes import incident_queues
            if incident_id in incident_queues:
                for q, loop in incident_queues[incident_id]:
                    try:
                        loop.call_soon_threadsafe(q.put_nowait, {
                            "event": "step",
                            "message": msg,
                            "state": state
                        })
                    except Exception as q_exc:
                        print(f"[WARN] Failed to broadcast reject: {str(q_exc)}")
    except Exception as exc:
        print(f"[ERROR] resume_incident_graph_async failed: {str(exc)}")
    finally:
        db.close()

@app.post("/api/v1/incidents/{incident_id}/action", response_model=IncidentResponse)
def handle_incident_action(
    incident_id: str,
    payload: ApprovalRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
        
    if incident.status != "recovery_pending":
        raise HTTPException(status_code=400, detail="Action can only be performed when status is recovery_pending")
        
    if payload.action not in ["approve", "reject"]:
        raise HTTPException(status_code=400, detail="Action must be either 'approve' or 'reject'")
        
    # Queue up background resume / reject thread runner
    background_tasks.add_task(resume_incident_graph_async, incident_id, payload.action)
    
    # Return immediately to front-end to avoid blocking API
    return incident

