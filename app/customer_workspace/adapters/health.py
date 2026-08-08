"""Workspace health adapter."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.customer_workspace.read_sources import customer_health_payload
from app.customer_workspace.schemas import HealthResponse, HealthSystemStatus


def get_workspace_health(db: Session, tenant_id: str) -> HealthResponse:
    payload = customer_health_payload(db, tenant_id)
    systems = {
        key: HealthSystemStatus(status=value["status"], label=value["label"])
        for key, value in (payload.get("systems") or {}).items()
    }
    return HealthResponse(
        overall_status=payload["overall_status"],
        message=payload["message"],
        systems=systems,
    )
