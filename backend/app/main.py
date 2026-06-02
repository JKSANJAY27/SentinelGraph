import time
import json
import asyncio
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List

from .database import Base, engine, get_db
from .models import Incident
from .schemas import AlertmanagerWebhook, IncidentResponse
from .graph.workflow import create_incident_workflow
from .graph.nodes import register_queue, unregister_queue

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
        # Run graph
        final_state = incident_graph.invoke(initial_state)
        
        # Update SQLite DB entry
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if incident:
            incident.status = final_state.get("status", "investigating")
            incident.state_json = final_state
            db.commit()
    except Exception as exc:
        print(f"[ERROR] LangGraph async run failed: {str(exc)}")
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if incident:
            incident.status = "error"
            incident.state_json = {"error": str(exc), "execution_history": ["Error: workflow crashed"]}
            db.commit()
    finally:
        db.close()

@app.get("/health")
def health():
    return {"status": "ok", "app": "sentinelgraph-backend"}

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
        "execution_history": ["Supervisor: Readying incident workspace."]
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
