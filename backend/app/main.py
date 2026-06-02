import time
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List

from .database import Base, engine, get_db
from .models import Incident
from .schemas import AlertmanagerWebhook, IncidentResponse
from .graph.workflow import create_incident_workflow

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

@app.get("/health")
def health():
    return {"status": "ok", "app": "sentinelgraph-backend"}

@app.post("/api/v1/alerts", response_model=IncidentResponse)
def receive_alert(webhook_data: AlertmanagerWebhook, db: Session = Depends(get_db)):
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
        alert_payload=webhook_data.model_dump()
    )
    db.add(db_incident)
    db.commit()
    db.refresh(db_incident)
    
    # 2. Trigger LangGraph Multi-Agent investigation
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
        "execution_history": []
    }
    
    try:
        final_state = incident_graph.invoke(initial_state)
        
        # 3. Update DB incident with outcomes
        db_incident.status = final_state.get("status", "investigating")
        db_incident.state_json = final_state
        db.commit()
        db.refresh(db_incident)
    except Exception as exc:
        print(f"[ERROR] LangGraph execution failed: {str(exc)}")
        db_incident.status = "error"
        db_incident.state_json = {"error": str(exc), "execution_history": ["Error: workflow failed"]}
        db.commit()
        
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
