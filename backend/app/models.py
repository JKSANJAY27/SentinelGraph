import datetime
from sqlalchemy import Column, String, DateTime, JSON
from .database import Base

class Incident(Base):
    __tablename__ = "incidents"

    id = Column(String, primary_key=True, index=True)
    alertname = Column(String, index=True)
    service = Column(String, index=True)
    severity = Column(String)
    status = Column(String, default="active")  # active, triaged, investigating, recovery_pending, recovered, postmortem_written
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    alert_payload = Column(JSON, nullable=True)
    state_json = Column(JSON, nullable=True)

class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=True)
