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

def seed_default_settings():
    from .database import SessionLocal
    from .models import SystemSetting
    db = SessionLocal()
    try:
        defaults = {
            "prometheus_url": "http://localhost:9090",
            "logs_mode": "docker",
            "kubernetes_namespace": "default",
            "restart_mode": "docker",
            "github_repo": "",
            "github_branch": "master",
            "github_token": "",
            "slack_webhook_url": "",
            "langfuse_public_key": os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-0f43a27c-5b4d-4f10-9446-6eee8060216c"),
            "langfuse_secret_key": os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-f656a0df-ba2b-4c14-b722-f582b67516f3"),
            "langfuse_base_url": os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
            "logs_file_path": "logs/{service}.log",
            "remediation_webhook_url": "",
            "remediation_command": "echo 'Restarting service {service}'"
        }
        for k, v in defaults.items():
            existing = db.query(SystemSetting).filter(SystemSetting.key == k).first()
            if not existing:
                setting = SystemSetting(key=k, value=v)
                db.add(setting)
        db.commit()
    except Exception as exc:
        print(f"[SETTINGS SEEDER] Error: {str(exc)}")
    finally:
        db.close()

seed_default_settings()

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
def receive_alert(webhook_data: dict, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    alertname = "UnknownAlert"
    service = "unknown-service"
    severity = "critical"
    
    # 1. Detect Sentry Payload
    if "project_name" in webhook_data or "project" in webhook_data or "event" in webhook_data:
        service = webhook_data.get("project_name", webhook_data.get("project", "unknown-service"))
        severity = webhook_data.get("level", "error")
        alertname = webhook_data.get("message", webhook_data.get("title", "SentryExceptionAlert"))
        if "event" in webhook_data and isinstance(webhook_data["event"], dict):
            event = webhook_data["event"]
            service = event.get("project", service)
            alertname = event.get("title", alertname)
            severity = event.get("level", severity)
            
    # 2. Detect Grafana Payload
    elif "ruleName" in webhook_data or "evalMatches" in webhook_data:
        alertname = webhook_data.get("ruleName", "GrafanaAlert")
        severity = "warning" if webhook_data.get("state") == "pending" else "critical"
        tags = webhook_data.get("tags", {})
        service = tags.get("service", tags.get("job", "unknown-service"))
        if service == "unknown-service" and webhook_data.get("evalMatches"):
            matches = webhook_data["evalMatches"]
            if matches and isinstance(matches, list):
                service = matches[0].get("metric", "unknown-service")
                
    # 3. Alertmanager Format (standard or fallback)
    else:
        alerts = webhook_data.get("alerts", [])
        if alerts and isinstance(alerts, list):
            alert = alerts[0]
            labels = alert.get("labels", {})
            alertname = labels.get("alertname", "UnknownAlert")
            service = labels.get("service", labels.get("job", "unknown-service"))
            severity = labels.get("severity", "critical")
        else:
            alertname = webhook_data.get("alertname", "GenericWebhookAlert")
            service = webhook_data.get("service", "unknown-service")
            severity = webhook_data.get("severity", "info")

    # Clean and normalize service name to match user-service, order-service, payment-service catalog
    service_lower = service.lower()
    if "payment" in service_lower:
        service = "payment-service"
    elif "order" in service_lower:
        service = "order-service"
    elif "user" in service_lower:
        service = "user-service"
    else:
        service = service.replace("_", "-")
        if not service.endswith("-service"):
            service = f"{service}-service"

    # Normalize severity to lowercase
    severity = severity.lower()
    if severity not in ["info", "warning", "critical"]:
        severity = "critical" if severity in ["error", "fatal"] else "warning"

    incident_id = f"inc_{int(time.time())}"
    
    # 1. Initialize DB incident
    db_incident = Incident(
        id=incident_id,
        alertname=alertname,
        service=service,
        severity=severity,
        status="active",
        alert_payload=webhook_data,
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
        "alert_payload": webhook_data,
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

from .schemas import SettingsResponse

@app.get("/api/v1/settings", response_model=SettingsResponse)
def get_settings(db: Session = Depends(get_db)):
    from .models import SystemSetting
    settings = db.query(SystemSetting).all()
    s_dict = {s.key: s.value or "" for s in settings}
    required_keys = [
        "prometheus_url", "logs_mode", "kubernetes_namespace", "restart_mode",
        "github_repo", "github_branch", "github_token", "slack_webhook_url",
        "langfuse_public_key", "langfuse_secret_key", "langfuse_base_url",
        "logs_file_path", "remediation_webhook_url", "remediation_command"
    ]
    for key in required_keys:
        if key not in s_dict:
            s_dict[key] = ""
    return SettingsResponse(**s_dict)

@app.put("/api/v1/settings", response_model=SettingsResponse)
def update_settings(payload: SettingsResponse, db: Session = Depends(get_db)):
    from .models import SystemSetting
    payload_dict = payload.model_dump()
    for key, value in payload_dict.items():
        setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if setting:
            setting.value = str(value)
        else:
            setting = SystemSetting(key=key, value=str(value))
            db.add(setting)
        if key in ["langfuse_public_key", "langfuse_secret_key", "langfuse_base_url"]:
            os.environ[key.upper()] = str(value)
    db.commit()
    return get_settings(db)

@app.post("/api/v1/settings/test")
def test_setting_connection(payload: dict):
    target = payload.get("target")
    value = payload.get("value")
    
    if target == "prometheus":
        import httpx
        try:
            url = f"{value.rstrip('/')}/api/v1/query"
            res = httpx.get(url, params={"query": "1"}, timeout=3.0)
            if res.status_code == 200:
                return {"status": "success", "message": "Successfully reached Prometheus API."}
            return {"status": "error", "message": f"Prometheus returned status code {res.status_code}."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to connect: {str(e)}"}
            
    elif target == "slack":
        import httpx
        try:
            slack_payload = {
                "text": "🛡️ *SentinelGraph Connection Test*: Slack webhook integration is verified and active!"
            }
            res = httpx.post(value, json=slack_payload, timeout=3.0)
            if res.status_code in [200, 201]:
                return {"status": "success", "message": "Successfully posted test message to Slack."}
            return {"status": "error", "message": f"Slack webhook returned status {res.status_code}."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to post to Slack: {str(e)}"}
            
    elif target == "github":
        import httpx
        try:
            headers = {}
            token = payload.get("token")
            if token:
                headers["Authorization"] = f"token {token}"
            url = f"https://api.github.com/repos/{value}/commits"
            res = httpx.get(url, headers=headers, timeout=3.0)
            if res.status_code == 200:
                return {"status": "success", "message": f"Successfully connected to GitHub repo '{value}' commits registry."}
            return {"status": "error", "message": f"GitHub returned status {res.status_code} (repo may be private or invalid)."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to connect to GitHub: {str(e)}"}
            
    elif target == "webhook":
        import httpx
        try:
            test_payload = {
                "service": "test-service",
                "action": "test",
                "timestamp": time.time(),
                "trigger": "SentinelGraph Connection Test"
            }
            res = httpx.post(value, json=test_payload, timeout=3.0)
            if res.status_code in [200, 201, 202, 204]:
                return {"status": "success", "message": f"Successfully sent webhook payload. Status code: {res.status_code}."}
            return {"status": "error", "message": f"Webhook returned status code {res.status_code}."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to post to webhook: {str(e)}"}
            
    elif target == "command":
        import subprocess
        # Test command by substituting {service} with 'test-service'
        cmd = value.replace("{service}", "test-service")
        try:
            res = subprocess.run(
                cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3.0
            )
            if res.returncode == 0:
                return {"status": "success", "message": f"Successfully executed command. Output: {res.stdout.strip()[:100]}"}
            return {"status": "error", "message": f"Command returned exit code {res.returncode}. Stderr: {res.stderr.strip()[:100]}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to execute command: {str(e)}"}
            
    elif target == "local_file":
        try:
            import os
            path = value.replace("{service}", "test-service")
            dir_name = os.path.dirname(path) or "."
            if os.path.exists(path):
                return {"status": "success", "message": f"Log file exists and is readable at '{path}'."}
            elif os.path.exists(dir_name):
                return {"status": "success", "message": f"Path '{path}' does not exist yet, but parent directory '{dir_name}' is accessible."}
            else:
                return {"status": "error", "message": f"Parent directory '{dir_name}' does not exist."}
        except Exception as e:
            return {"status": "error", "message": f"Invalid path pattern: {str(e)}"}
            
    return {"status": "error", "message": "Unknown test target."}

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

