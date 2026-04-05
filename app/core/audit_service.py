from typing import Dict, Any
from sqlalchemy.orm import Session

from app.core.audit_models import AuditEvent
from app.repositories.postgres.audit_repository import AuditRepository


def create_audit_event(
    db: Session,
    tenant_id: str,
    category: str,
    action: str,
    status: str,
    details: Dict[str, Any] | None = None
) -> AuditEvent:
    event = AuditEvent(
        tenant_id=tenant_id,
        category=category,
        action=action,
        status=status,
        details=details or {},
    )

    AuditRepository.create_event(db, event)
    return event