"""
Operator incident management service (Kapitel 6).

Internal writes only — no external effects.
Incident timeline + audit share one SQLAlchemy session and one commit.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.admin.incident_models import IncidentRecord
from app.admin.incident_repository import (
    IncidentConflictError,
    IncidentNotFoundError,
    IncidentRepository,
)
from app.admin.incident_schemas import (
    ALLOWED_TRANSITIONS,
    CLOSED_STATUSES,
    OPEN_STATUSES,
    AvailableIncidentAction,
    IncidentDetail,
    IncidentListItem,
    IncidentListResponse,
    IncidentSignalOut,
    IncidentSummary,
    IncidentTenantOut,
    IncidentTimelineEventOut,
    IncidentWriteResponse,
    LinkedIncidentSummary,
    LinkedIncidentsGroup,
    RecommendedIncidentAction,
)
from app.admin.operations_triage import (
    _build_tenant_triage,
    _priority_id,
    dedupe_and_normalize_signals,
)
from app.core.admin_session import OperatorIdentity
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

logger = logging.getLogger(__name__)

_INCIDENT_AUDIT_CATEGORY = "incident"
_WRITE_ROLES = frozenset({"operations", "admin"})
_SEVERITY_BADGE = {
    "critical": "P1",
    "failed": "P2",
    "warning": "P3",
    "information": "P4",
}
_PANEL_SEVERITY = {
    "critical": "critical",
    "high": "failed",
    "medium": "warning",
    "info": "information",
}


class IncidentValidationError(Exception):
    """Request validation failed at service layer."""


class IncidentClosedError(IncidentConflictError):
    """Incident is closed and cannot be modified."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _panel_severity(internal: str) -> str:
    return _PANEL_SEVERITY.get(internal, "information")


def _severity_badge(severity: str) -> str:
    return _SEVERITY_BADGE.get(severity, "P4")


def _age_hours(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    delta = _utcnow() - dt
    return max(0, int(delta.total_seconds() // 3600))


def _ensure_not_closed(incident: IncidentRecord) -> None:
    if incident.status == "closed":
        raise IncidentClosedError("Incidenten är stängd och kan inte ändras.")


def _sanitize_audit_details(details: dict[str, Any]) -> dict[str, Any]:
    blocked = {
        "password",
        "api_key",
        "token",
        "secret",
        "credential",
        "access_token",
        "refresh_token",
        "client_secret",
    }
    clean: dict[str, Any] = {}
    for key, value in details.items():
        lower = key.lower()
        if any(part in lower for part in blocked):
            continue
        if isinstance(value, dict):
            clean[key] = _sanitize_audit_details(value)
        else:
            clean[key] = value
    return clean


def _add_audit_event_no_commit(
    db: Session,
    *,
    tenant_id: str,
    action: str,
    status: str,
    details: dict[str, Any],
) -> AuditEventRecord:
    record = AuditEventRecord(
        event_id=str(uuid4()),
        tenant_id=tenant_id,
        category=_INCIDENT_AUDIT_CATEGORY,
        action=action,
        status=status,
        details=_sanitize_audit_details(details),
        created_at=_utcnow(),
    )
    db.add(record)
    return record


def _audit_tenant_id(incident: IncidentRecord, db: Session) -> str:
    tenants = IncidentRepository.list_active_tenants(db, incident.incident_id)
    if tenants:
        return tenants[0].tenant_id
    return "_operator"


def _domain_source_id(row: dict[str, Any]) -> str:
    job_id = row.get("job_id")
    if job_id:
        return str(job_id)
    approval_id = row.get("approval_id")
    if approval_id:
        return str(approval_id)
    raw = row.get("source_id")
    if isinstance(raw, str) and ":" in raw:
        return raw.split(":", 1)[1]
    if raw:
        return str(raw)
    return _priority_id(row)


def resolve_signal_row(
    db: Session,
    *,
    tenant_id: str,
    signal_id: str,
    app_settings: Any,
) -> dict[str, Any] | None:
    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        return None
    rows = _build_tenant_triage(
        db,
        tenant_id=tenant_id,
        tenant_name=record.name or tenant_id,
        app_settings=app_settings,
        record=record,
    )
    rows = dedupe_and_normalize_signals(rows)
    for row in rows:
        if _priority_id(row) == signal_id:
            return row
    return None


def build_signal_snapshot(row: dict[str, Any]) -> dict[str, str]:
    internal_severity = row.get("severity") or "info"
    return {
        "signal_id": _priority_id(row),
        "tenant_id": row.get("tenant_id") or "",
        "source_type": row.get("source_type") or "",
        "source_id": _domain_source_id(row),
        "snapshot_title": row.get("title") or "",
        "snapshot_summary": (row.get("detail") or "")[:500],
        "snapshot_severity": _panel_severity(internal_severity),
    }


def find_linked_incidents(
    db: Session,
    signal_id: str,
) -> LinkedIncidentsGroup:
    records = IncidentRepository.find_linked_incidents_for_signal(db, signal_id)
    open_items: list[LinkedIncidentSummary] = []
    closed_items: list[LinkedIncidentSummary] = []
    for record in records:
        summary = LinkedIncidentSummary(
            incident_id=record.incident_id,
            title=record.title,
            status=record.status,  # type: ignore[arg-type]
            severity=record.severity,  # type: ignore[arg-type]
        )
        if record.status in CLOSED_STATUSES:
            closed_items.append(summary)
        else:
            open_items.append(summary)
    return LinkedIncidentsGroup(open=open_items, closed=closed_items)


def build_recommended_incident_action(
    item: dict[str, Any],
) -> RecommendedIncidentAction | None:
    tenant_id = item.get("tenant_id")
    signal_id = item.get("id")
    if not tenant_id or not signal_id:
        return None
    return RecommendedIncidentAction(
        tenant_id=tenant_id,
        signal_id=signal_id,
        prefill_title=item.get("title") or "",
        prefill_severity=item.get("severity") or "information",  # type: ignore[arg-type]
    )


def resolve_available_incident_actions(
    incident: IncidentRecord,
    operator_role: str,
) -> list[AvailableIncidentAction]:
    actions: list[AvailableIncidentAction] = []
    is_closed = incident.status == "closed"
    can_write = operator_role in _WRITE_ROLES

    transitions = ALLOWED_TRANSITIONS.get(incident.status, set())
    for target in sorted(transitions):
        actions.append(
            AvailableIncidentAction(
                action_id=f"incident.status.{target}",
                label=_status_action_label(target),
                required_role="operations",
                requires_reason=True,
                requires_confirmation=True,
                allowed=can_write and not is_closed,
                blocked_reason=(
                    "incident_closed"
                    if is_closed
                    else ("insufficient_role" if not can_write else None)
                ),
            )
        )

    if incident.owner_id is None:
        actions.append(
            AvailableIncidentAction(
                action_id="incident.assign_self",
                label="Tilldela mig",
                required_role="operations",
                requires_reason=True,
                requires_confirmation=True,
                allowed=can_write and not is_closed,
                blocked_reason=(
                    "incident_closed"
                    if is_closed
                    else ("insufficient_role" if not can_write else None)
                ),
            )
        )

    return actions


def _status_action_label(status: str) -> str:
    labels = {
        "acknowledged": "Bekräfta incident",
        "investigating": "Påbörja utredning",
        "monitoring": "Övervaka",
        "resolved": "Markera som löst",
        "closed": "Stäng incident",
    }
    return labels.get(status, status)


def _timeline_to_out(record) -> IncidentTimelineEventOut:
    return IncidentTimelineEventOut(
        event_id=record.event_id,
        event_type=record.event_type,
        actor_id=record.actor_id,
        actor_display_name=record.actor_display_name,
        actor_role=record.actor_role,
        message=record.message,
        metadata=record.metadata_json or {},
        created_at=record.created_at,
    )


def _tenant_to_out(record) -> IncidentTenantOut:
    return IncidentTenantOut(
        tenant_id=record.tenant_id,
        tenant_name_snapshot=record.tenant_name_snapshot,
        linked_at=record.created_at,
        unlinked_at=record.unlinked_at,
    )


def _signal_to_out(record) -> IncidentSignalOut:
    return IncidentSignalOut(
        signal_id=record.signal_id,
        tenant_id=record.tenant_id,
        source_type=record.source_type,
        source_id=record.source_id,
        snapshot_title=record.snapshot_title,
        snapshot_summary=record.snapshot_summary,
        snapshot_severity=record.snapshot_severity,  # type: ignore[arg-type]
        linked_at=record.linked_at,
        unlinked_at=record.unlinked_at,
    )


def _incident_to_list_item(db: Session, record: IncidentRecord) -> IncidentListItem:
    return IncidentListItem(
        incident_id=record.incident_id,
        title=record.title,
        description=record.description,
        severity=record.severity,  # type: ignore[arg-type]
        severity_badge=_severity_badge(record.severity),  # type: ignore[arg-type]
        status=record.status,  # type: ignore[arg-type]
        owner_id=record.owner_id,
        owner_display_name=record.owner_display_name,
        tenant_count=IncidentRepository.active_tenant_count(db, record.incident_id),
        signal_count=IncidentRepository.active_signal_count(db, record.incident_id),
        created_at=record.created_at,
        updated_at=record.updated_at,
        age_hours=_age_hours(record.created_at),
    )


def get_incident_detail(
    db: Session,
    incident_id: str,
    *,
    operator_role: str = "read_only",
) -> IncidentDetail | None:
    record = IncidentRepository.get_incident(db, incident_id)
    if record is None:
        return None
    tenants = IncidentRepository.list_active_tenants(db, incident_id)
    signals = IncidentRepository.list_active_signals(db, incident_id)
    timeline = IncidentRepository.list_timeline(db, incident_id)
    return IncidentDetail(
        incident_id=record.incident_id,
        title=record.title,
        description=record.description,
        severity=record.severity,  # type: ignore[arg-type]
        severity_badge=_severity_badge(record.severity),  # type: ignore[arg-type]
        status=record.status,  # type: ignore[arg-type]
        owner_id=record.owner_id,
        owner_display_name=record.owner_display_name,
        created_by=record.created_by,
        created_by_display_name=record.created_by_display_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
        acknowledged_at=record.acknowledged_at,
        resolved_at=record.resolved_at,
        closed_at=record.closed_at,
        resolution_summary=record.resolution_summary,
        version=record.version,
        tenants=[_tenant_to_out(t) for t in tenants],
        signals=[_signal_to_out(s) for s in signals],
        timeline=[_timeline_to_out(e) for e in timeline],
        available_actions=resolve_available_incident_actions(record, operator_role),
    )


def list_incidents(
    db: Session,
    *,
    search: str | None = None,
    status: str | None = None,
    severity: str | None = None,
    tenant_id: str | None = None,
    owner: str | None = None,
    updated_since: datetime | None = None,
    sort: str = "updated_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> IncidentListResponse:
    records, total = IncidentRepository.list_incidents(
        db,
        search=search,
        status=status,
        severity=severity,
        tenant_id=tenant_id,
        owner=owner,
        updated_since=updated_since,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    summary = IncidentSummary(
        open=IncidentRepository.count_by_status(db, OPEN_STATUSES),
        investigating=IncidentRepository.count_by_status(db, {"investigating"}),
        monitoring=IncidentRepository.count_by_status(db, {"monitoring"}),
        resolved=IncidentRepository.count_by_status(db, {"resolved"}),
        critical=IncidentRepository.count_critical(db),
        affected_tenants=IncidentRepository.count_affected_tenants(db),
    )
    return IncidentListResponse(
        generated_at=_utcnow(),
        total=total,
        limit=limit,
        offset=offset,
        summary=summary,
        items=[_incident_to_list_item(db, r) for r in records],
    )


def _verify_tenant_exists(db: Session, tenant_id: str) -> str:
    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        raise IncidentNotFoundError(f"Tenant '{tenant_id}' not found.")
    return record.name or tenant_id


def create_incident(
    db: Session,
    *,
    operator: OperatorIdentity,
    title: str,
    description: str | None,
    severity: str,
    tenant_ids: list[str],
    signal_links: list[dict[str, str]],
    reason: str,
    app_settings: Any,
) -> IncidentDetail:
    verified_tenants: list[tuple[str, str]] = []
    for tenant_id in tenant_ids:
        name = _verify_tenant_exists(db, tenant_id)
        verified_tenants.append((tenant_id, name))

    verified_signals: list[dict[str, str]] = []
    for link in signal_links:
        tenant_id = link["tenant_id"]
        signal_id = link["signal_id"]
        _verify_tenant_exists(db, tenant_id)
        row = resolve_signal_row(
            db,
            tenant_id=tenant_id,
            signal_id=signal_id,
            app_settings=app_settings,
        )
        if row is None:
            raise IncidentNotFoundError(
                f"Signal '{signal_id}' hittades inte för tenant '{tenant_id}'."
            )
        verified_signals.append(build_signal_snapshot(row))

    incident = IncidentRepository.create_incident(
        db,
        title=title,
        description=description,
        severity=severity,
        created_by=operator["id"],
        created_by_display_name=operator["display_name"],
    )
    incident_id = incident.incident_id

    IncidentRepository.add_timeline_event(
        db,
        incident_id=incident_id,
        event_type="created",
        actor_id=operator["id"],
        actor_display_name=operator["display_name"],
        actor_role=operator["role"],
        message=f"Incident skapad: {title}",
        metadata={"reason": reason, "severity": severity},
    )

    for tenant_id, tenant_name in verified_tenants:
        IncidentRepository.link_tenant(
            db,
            incident_id=incident_id,
            tenant_id=tenant_id,
            tenant_name_snapshot=tenant_name,
        )
        IncidentRepository.add_timeline_event(
            db,
            incident_id=incident_id,
            event_type="tenant_linked",
            actor_id=operator["id"],
            actor_display_name=operator["display_name"],
            actor_role=operator["role"],
            message=f"Tenant kopplad: {tenant_name}",
            metadata={"tenant_id": tenant_id},
        )

    for snap in verified_signals:
        IncidentRepository.link_signal(db, incident_id=incident_id, **snap)
        IncidentRepository.add_timeline_event(
            db,
            incident_id=incident_id,
            event_type="signal_linked",
            actor_id=operator["id"],
            actor_display_name=operator["display_name"],
            actor_role=operator["role"],
            message=f"Signal kopplad: {snap['snapshot_title']}",
            metadata={"signal_id": snap["signal_id"], "tenant_id": snap["tenant_id"]},
        )

    audit_tenant = verified_tenants[0][0] if verified_tenants else "_operator"
    _add_audit_event_no_commit(
        db,
        tenant_id=audit_tenant,
        action="incident.create",
        status="completed",
        details={
            "incident_id": incident_id,
            "operator_id": operator["id"],
            "operator_display_name": operator["display_name"],
            "operator_role": operator["role"],
            "reason": reason,
            "severity": severity,
            "tenant_ids": [t[0] for t in verified_tenants],
            "signal_ids": [s["signal_id"] for s in verified_signals],
        },
    )
    db.commit()

    detail = get_incident_detail(db, incident_id, operator_role=operator["role"])
    if detail is None:
        raise IncidentNotFoundError(f"Incident '{incident_id}' not found.")
    return detail


def change_status(
    db: Session,
    *,
    incident_id: str,
    operator: OperatorIdentity,
    target_status: str,
    reason: str,
    resolution_summary: str | None,
    expected_version: int,
) -> IncidentWriteResponse:
    incident = IncidentRepository.get_incident(db, incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"Incident '{incident_id}' not found.")
    _ensure_not_closed(incident)

    if incident.status == target_status:
        raise IncidentConflictError(
            f"Incidenten har redan status '{target_status}'."
        )

    allowed = ALLOWED_TRANSITIONS.get(incident.status, set())
    if target_status not in allowed:
        raise IncidentConflictError(
            f"Statusövergång från '{incident.status}' till '{target_status}' är inte tillåten."
        )

    if target_status in ("resolved", "closed") and not (resolution_summary or "").strip():
        raise IncidentValidationError(
            "resolution_summary krävs när status blir resolved eller closed."
        )

    now = _utcnow()
    values: dict[str, Any] = {"status": target_status}
    if target_status == "acknowledged" and incident.acknowledged_at is None:
        values["acknowledged_at"] = now
    if target_status == "resolved":
        values["resolved_at"] = now
        values["resolution_summary"] = (resolution_summary or "").strip()
    if target_status == "closed":
        values["closed_at"] = now
        if resolution_summary:
            values["resolution_summary"] = resolution_summary.strip()

    updated = IncidentRepository.atomic_update_incident(
        db,
        incident_id,
        expected_version,
        values=values,
    )

    event_type = "closed" if target_status == "closed" else "status_changed"
    IncidentRepository.add_timeline_event(
        db,
        incident_id=incident_id,
        event_type=event_type,
        actor_id=operator["id"],
        actor_display_name=operator["display_name"],
        actor_role=operator["role"],
        message=f"Status ändrad till {target_status}",
        metadata={
            "from_status": incident.status,
            "to_status": target_status,
            "reason": reason,
        },
    )
    _add_audit_event_no_commit(
        db,
        tenant_id=_audit_tenant_id(updated, db),
        action="incident.status_change",
        status="completed",
        details={
            "incident_id": incident_id,
            "operator_id": operator["id"],
            "operator_role": operator["role"],
            "reason": reason,
            "from_status": incident.status,
            "to_status": target_status,
            "expected_version": expected_version,
            "new_version": updated.version,
        },
    )
    db.commit()
    return IncidentWriteResponse(
        incident_id=incident_id,
        version=updated.version,
        message=f"Status uppdaterad till {target_status}.",
    )


def add_note(
    db: Session,
    *,
    incident_id: str,
    operator: OperatorIdentity,
    message: str,
) -> IncidentWriteResponse:
    incident = IncidentRepository.get_incident(db, incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"Incident '{incident_id}' not found.")
    _ensure_not_closed(incident)

    IncidentRepository.add_timeline_event(
        db,
        incident_id=incident_id,
        event_type="note_added",
        actor_id=operator["id"],
        actor_display_name=operator["display_name"],
        actor_role=operator["role"],
        message=message,
        metadata={},
    )
    IncidentRepository.touch_incident_updated_at(db, incident_id)
    _add_audit_event_no_commit(
        db,
        tenant_id=_audit_tenant_id(incident, db),
        action="incident.note_added",
        status="completed",
        details={
            "incident_id": incident_id,
            "operator_id": operator["id"],
            "operator_role": operator["role"],
            "message_length": len(message),
        },
    )
    db.commit()
    refreshed = IncidentRepository.get_incident(db, incident_id)
    return IncidentWriteResponse(
        incident_id=incident_id,
        version=refreshed.version if refreshed else incident.version,
        message="Anteckning tillagd.",
    )


def update_fields(
    db: Session,
    *,
    incident_id: str,
    operator: OperatorIdentity,
    title: str | None,
    description: str | None,
    severity: str | None,
    reason: str,
    expected_version: int,
) -> IncidentWriteResponse:
    incident = IncidentRepository.get_incident(db, incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"Incident '{incident_id}' not found.")
    _ensure_not_closed(incident)

    values: dict[str, Any] = {}
    if title is not None:
        values["title"] = title
    if description is not None:
        values["description"] = description
    if severity is not None:
        values["severity"] = severity
    if not values:
        raise IncidentValidationError("Inga fält att uppdatera angavs.")

    updated = IncidentRepository.atomic_update_incident(
        db,
        incident_id,
        expected_version,
        values=values,
    )
    IncidentRepository.add_timeline_event(
        db,
        incident_id=incident_id,
        event_type="field_updated",
        actor_id=operator["id"],
        actor_display_name=operator["display_name"],
        actor_role=operator["role"],
        message="Incidentfält uppdaterade",
        metadata={"fields": list(values.keys()), "reason": reason},
    )
    _add_audit_event_no_commit(
        db,
        tenant_id=_audit_tenant_id(updated, db),
        action="incident.field_update",
        status="completed",
        details={
            "incident_id": incident_id,
            "operator_id": operator["id"],
            "operator_role": operator["role"],
            "reason": reason,
            "fields": list(values.keys()),
            "new_version": updated.version,
        },
    )
    db.commit()
    return IncidentWriteResponse(
        incident_id=incident_id,
        version=updated.version,
        message="Incident uppdaterad.",
    )


def assign_self(
    db: Session,
    *,
    incident_id: str,
    operator: OperatorIdentity,
    reason: str,
    expected_version: int,
) -> IncidentWriteResponse:
    incident = IncidentRepository.get_incident(db, incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"Incident '{incident_id}' not found.")
    _ensure_not_closed(incident)

    values: dict[str, Any] = {
        "owner_id": operator["id"],
        "owner_display_name": operator["display_name"],
    }
    if incident.status == "open":
        values["status"] = "acknowledged"
        values["acknowledged_at"] = _utcnow()

    updated = IncidentRepository.atomic_update_incident(
        db,
        incident_id,
        expected_version,
        values=values,
    )

    IncidentRepository.add_timeline_event(
        db,
        incident_id=incident_id,
        event_type="owner_assigned",
        actor_id=operator["id"],
        actor_display_name=operator["display_name"],
        actor_role=operator["role"],
        message=f"Ansvarig tilldelad: {operator['display_name']}",
        metadata={"reason": reason},
    )
    _add_audit_event_no_commit(
        db,
        tenant_id=_audit_tenant_id(updated, db),
        action="incident.assign_self",
        status="completed",
        details={
            "incident_id": incident_id,
            "operator_id": operator["id"],
            "operator_display_name": operator["display_name"],
            "operator_role": operator["role"],
            "reason": reason,
            "new_version": updated.version,
        },
    )
    db.commit()
    return IncidentWriteResponse(
        incident_id=incident_id,
        version=updated.version,
        message="Du är nu ansvarig för incidenten.",
    )


def link_tenant(
    db: Session,
    *,
    incident_id: str,
    operator: OperatorIdentity,
    tenant_id: str,
    reason: str,
) -> IncidentWriteResponse:
    incident = IncidentRepository.get_incident(db, incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"Incident '{incident_id}' not found.")
    _ensure_not_closed(incident)

    tenant_name = _verify_tenant_exists(db, tenant_id)
    IncidentRepository.link_tenant(
        db,
        incident_id=incident_id,
        tenant_id=tenant_id,
        tenant_name_snapshot=tenant_name,
    )
    IncidentRepository.add_timeline_event(
        db,
        incident_id=incident_id,
        event_type="tenant_linked",
        actor_id=operator["id"],
        actor_display_name=operator["display_name"],
        actor_role=operator["role"],
        message=f"Tenant kopplad: {tenant_name}",
        metadata={"tenant_id": tenant_id, "reason": reason},
    )
    IncidentRepository.touch_incident_updated_at(db, incident_id)
    _add_audit_event_no_commit(
        db,
        tenant_id=tenant_id,
        action="incident.tenant_link",
        status="completed",
        details={
            "incident_id": incident_id,
            "operator_id": operator["id"],
            "operator_role": operator["role"],
            "reason": reason,
            "tenant_id": tenant_id,
        },
    )
    db.commit()
    refreshed = IncidentRepository.get_incident(db, incident_id)
    return IncidentWriteResponse(
        incident_id=incident_id,
        version=refreshed.version if refreshed else incident.version,
        message=f"Tenant '{tenant_id}' kopplad.",
    )


def unlink_tenant(
    db: Session,
    *,
    incident_id: str,
    operator: OperatorIdentity,
    tenant_id: str,
    reason: str,
) -> IncidentWriteResponse:
    incident = IncidentRepository.get_incident(db, incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"Incident '{incident_id}' not found.")
    _ensure_not_closed(incident)

    record = IncidentRepository.unlink_tenant(db, incident_id, tenant_id)
    IncidentRepository.add_timeline_event(
        db,
        incident_id=incident_id,
        event_type="tenant_unlinked",
        actor_id=operator["id"],
        actor_display_name=operator["display_name"],
        actor_role=operator["role"],
        message=f"Tenant bortkopplad: {record.tenant_name_snapshot or tenant_id}",
        metadata={"tenant_id": tenant_id, "reason": reason},
    )
    IncidentRepository.touch_incident_updated_at(db, incident_id)
    _add_audit_event_no_commit(
        db,
        tenant_id=tenant_id,
        action="incident.tenant_unlink",
        status="completed",
        details={
            "incident_id": incident_id,
            "operator_id": operator["id"],
            "operator_role": operator["role"],
            "reason": reason,
            "tenant_id": tenant_id,
        },
    )
    db.commit()
    refreshed = IncidentRepository.get_incident(db, incident_id)
    return IncidentWriteResponse(
        incident_id=incident_id,
        version=refreshed.version if refreshed else incident.version,
        message=f"Tenant '{tenant_id}' bortkopplad.",
    )


def link_signal(
    db: Session,
    *,
    incident_id: str,
    operator: OperatorIdentity,
    tenant_id: str,
    signal_id: str,
    reason: str,
    app_settings: Any,
) -> IncidentWriteResponse:
    incident = IncidentRepository.get_incident(db, incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"Incident '{incident_id}' not found.")
    _ensure_not_closed(incident)

    _verify_tenant_exists(db, tenant_id)
    row = resolve_signal_row(
        db,
        tenant_id=tenant_id,
        signal_id=signal_id,
        app_settings=app_settings,
    )
    if row is None:
        raise IncidentNotFoundError(
            f"Signal '{signal_id}' hittades inte för tenant '{tenant_id}'."
        )
    snap = build_signal_snapshot(row)
    IncidentRepository.link_signal(db, incident_id=incident_id, **snap)
    IncidentRepository.add_timeline_event(
        db,
        incident_id=incident_id,
        event_type="signal_linked",
        actor_id=operator["id"],
        actor_display_name=operator["display_name"],
        actor_role=operator["role"],
        message=f"Signal kopplad: {snap['snapshot_title']}",
        metadata={"signal_id": signal_id, "tenant_id": tenant_id, "reason": reason},
    )
    IncidentRepository.touch_incident_updated_at(db, incident_id)
    _add_audit_event_no_commit(
        db,
        tenant_id=tenant_id,
        action="incident.signal_link",
        status="completed",
        details={
            "incident_id": incident_id,
            "operator_id": operator["id"],
            "operator_role": operator["role"],
            "reason": reason,
            "signal_id": signal_id,
            "tenant_id": tenant_id,
        },
    )
    db.commit()
    refreshed = IncidentRepository.get_incident(db, incident_id)
    return IncidentWriteResponse(
        incident_id=incident_id,
        version=refreshed.version if refreshed else incident.version,
        message=f"Signal '{signal_id}' kopplad.",
    )


def unlink_signal(
    db: Session,
    *,
    incident_id: str,
    operator: OperatorIdentity,
    signal_id: str,
    reason: str,
) -> IncidentWriteResponse:
    incident = IncidentRepository.get_incident(db, incident_id)
    if incident is None:
        raise IncidentNotFoundError(f"Incident '{incident_id}' not found.")
    _ensure_not_closed(incident)

    record = IncidentRepository.unlink_signal(db, incident_id, signal_id)
    IncidentRepository.add_timeline_event(
        db,
        incident_id=incident_id,
        event_type="signal_unlinked",
        actor_id=operator["id"],
        actor_display_name=operator["display_name"],
        actor_role=operator["role"],
        message=f"Signal bortkopplad: {record.snapshot_title}",
        metadata={"signal_id": signal_id, "reason": reason},
    )
    IncidentRepository.touch_incident_updated_at(db, incident_id)
    _add_audit_event_no_commit(
        db,
        tenant_id=record.tenant_id,
        action="incident.signal_unlink",
        status="completed",
        details={
            "incident_id": incident_id,
            "operator_id": operator["id"],
            "operator_role": operator["role"],
            "reason": reason,
            "signal_id": signal_id,
        },
    )
    db.commit()
    refreshed = IncidentRepository.get_incident(db, incident_id)
    return IncidentWriteResponse(
        incident_id=incident_id,
        version=refreshed.version if refreshed else incident.version,
        message=f"Signal '{signal_id}' bortkopplad.",
    )
