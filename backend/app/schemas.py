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
