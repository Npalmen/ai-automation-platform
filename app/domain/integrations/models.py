from sqlalchemy import Column, String, Integer, JSON, DateTime
from sqlalchemy.sql import func
from app.repositories.postgres.database import Base


class IntegrationEvent(Base):
    __tablename__ = "integration_events"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, index=True)
    tenant_id = Column(String, index=True)

    integration_type = Column(String, index=True)
    payload = Column(JSON)

    status = Column(String, default="pending")  # pending, success, failed, dead
    attempts = Column(Integer, default=0)
    last_error = Column(String, nullable=True)

    idempotency_key = Column(String, unique=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
