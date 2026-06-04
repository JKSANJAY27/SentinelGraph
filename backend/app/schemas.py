from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

# Alertmanager schemas
class AlertItem(BaseModel):
    status: str
    labels: Dict[str, str]
    annotations: Dict[str, str]
    startsAt: str
    generatorURL: str

class AlertmanagerWebhook(BaseModel):
    receiver: str
    status: str
    alerts: List[AlertItem]
    commonLabels: Dict[str, str]
    commonAnnotations: Dict[str, str]

# Incident API schemas
class IncidentBase(BaseModel):
    alertname: str
    service: str
    severity: str
    status: str

class IncidentCreate(IncidentBase):
    id: str
    alert_payload: Optional[Dict[str, Any]] = None

class IncidentUpdate(BaseModel):
    status: Optional[str] = None
    state_json: Optional[Dict[str, Any]] = None

class IncidentResponse(IncidentBase):
    id: str
    created_at: datetime
    alert_payload: Optional[Dict[str, Any]] = None
    state_json: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class ApprovalRequest(BaseModel):
    action: str  # "approve" or "reject"
    comments: Optional[str] = None

class SettingsResponse(BaseModel):
    prometheus_url: str
    logs_mode: str
    kubernetes_namespace: str
    restart_mode: str
    github_repo: str
    github_branch: str
    github_token: str
    slack_webhook_url: str
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_base_url: str

