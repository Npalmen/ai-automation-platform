from typing import List

from app.core.audit_models import AuditEvent


AUDIT_EVENTS: List[AuditEvent] = []


def save_audit_event(event: AuditEvent) -> AuditEvent:
    AUDIT_EVENTS.append(event)
    return event


def list_audit_events() -> list[AuditEvent]:
    return AUDIT_EVENTS