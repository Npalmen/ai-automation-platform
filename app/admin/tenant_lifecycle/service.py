"""Tenant lifecycle business logic."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from uuid import uuid4
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.admin.tenant_lifecycle.constants import (
    ALLOWED_LIFECYCLE_TRANSITIONS,
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_LABELS_SV,
    LIFECYCLE_ONBOARDING,
    VALID_LIFECYCLE_STATUSES,
)
from app.admin.tenant_lifecycle.models import TenantActivationSnapshotRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_tenant_or_404(db: Session, tenant_id: str) -> TenantConfigRecord:
    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    return record


def _pause_signals(settings: dict | None) -> tuple[bool, str | None]:
    settings = settings or {}
    operations = settings.get("operations") or {}
    scheduler = settings.get("scheduler") or {}
    ops_paused = bool(operations.get("paused", False))
    run_mode = scheduler.get("run_mode") or "manual"
    return ops_paused or run_mode == "paused", run_mode


def bump_config_version(
    record: TenantConfigRecord,
    *,
    operator_id: str | None = None,
) -> int:
    record.config_version = int(record.config_version or 1) + 1
    record.updated_at = _utcnow()
    if operator_id:
        record.last_config_updated_by = operator_id
    return record.config_version


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def present_lifecycle(record: TenantConfigRecord) -> dict[str, Any]:
    ops_paused, run_mode = _pause_signals(record.settings)
    status = record.lifecycle_status or LIFECYCLE_ONBOARDING
    if status not in VALID_LIFECYCLE_STATUSES:
        status = LIFECYCLE_ONBOARDING
    return {
        "tenant_id": record.tenant_id,
        "lifecycle_status": status,
        "lifecycle_label_sv": LIFECYCLE_LABELS_SV.get(status, status),
        "config_version": int(record.config_version or 1),
        "lifecycle_updated_at": record.lifecycle_updated_at,
        "lifecycle_updated_by": _optional_str(record.lifecycle_updated_by),
        "is_test_tenant": bool(record.is_test_tenant),
        "operations_paused": ops_paused,
        "scheduler_run_mode": run_mode,
        "last_config_updated_by": _optional_str(record.last_config_updated_by),
    }


def get_lifecycle(db: Session, tenant_id: str) -> dict[str, Any]:
    return present_lifecycle(_get_tenant_or_404(db, tenant_id))


def _assert_version(record: TenantConfigRecord, expected: int) -> None:
    if int(record.config_version or 1) != expected:
        raise HTTPException(status_code=409, detail="config_version conflict")


def _set_lifecycle(
    db: Session,
    record: TenantConfigRecord,
    *,
    new_status: str,
    operator_id: str,
    reason: str | None,
    audit_action: str,
) -> TenantConfigRecord:
    if new_status not in VALID_LIFECYCLE_STATUSES:
        raise HTTPException(status_code=422, detail="Invalid lifecycle_status.")
    current = record.lifecycle_status or LIFECYCLE_ONBOARDING
    allowed = ALLOWED_LIFECYCLE_TRANSITIONS.get(current, frozenset())
    if new_status != current and new_status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Transition {current} → {new_status} is not allowed.",
        )
    record.lifecycle_status = new_status
    record.lifecycle_updated_at = _utcnow()
    record.lifecycle_updated_by = operator_id
    if new_status == LIFECYCLE_ACTIVE and record.status != "active":
        record.status = "active"
    bump_config_version(record, operator_id=operator_id)
    db.add(
        AuditEventRecord(
            event_id=str(uuid4()),
            tenant_id=record.tenant_id,
            category="tenant_lifecycle",
            action=audit_action,
            status="succeeded",
            details={
                "from": current,
                "to": new_status,
                "operator_id": operator_id,
                "reason": reason,
                "config_version": record.config_version,
            },
            created_at=_utcnow(),
        )
    )
    db.commit()
    db.refresh(record)
    return record


def patch_lifecycle(
    db: Session,
    *,
    tenant_id: str,
    operator_id: str,
    lifecycle_status: str,
    config_version: int,
    reason: str | None,
) -> dict[str, Any]:
    record = _get_tenant_or_404(db, tenant_id)
    _assert_version(record, config_version)
    record = _set_lifecycle(
        db,
        record,
        new_status=lifecycle_status,
        operator_id=operator_id,
        reason=reason,
        audit_action="tenant.lifecycle_updated",
    )
    return present_lifecycle(record)


def archive_tenant(
    db: Session,
    *,
    tenant_id: str,
    operator_id: str,
    config_version: int,
    reason: str | None,
) -> dict[str, Any]:
    record = _get_tenant_or_404(db, tenant_id)
    _assert_version(record, config_version)
    record = _set_lifecycle(
        db,
        record,
        new_status=LIFECYCLE_ARCHIVED,
        operator_id=operator_id,
        reason=reason,
        audit_action="tenant.archived",
    )
    return present_lifecycle(record)


def restore_tenant(
    db: Session,
    *,
    tenant_id: str,
    operator_id: str,
    config_version: int,
    reason: str | None,
) -> dict[str, Any]:
    record = _get_tenant_or_404(db, tenant_id)
    _assert_version(record, config_version)
    target = LIFECYCLE_ACTIVE if record.status == "active" else LIFECYCLE_ONBOARDING
    record = _set_lifecycle(
        db,
        record,
        new_status=target,
        operator_id=operator_id,
        reason=reason,
        audit_action="tenant.restored",
    )
    return present_lifecycle(record)


def pause_operations(
    db: Session,
    *,
    tenant_id: str,
    operator_id: str,
    config_version: int,
    reason: str | None,
) -> dict[str, Any]:
    record = _get_tenant_or_404(db, tenant_id)
    _assert_version(record, config_version)
    settings = copy.deepcopy(record.settings or {})
    settings.setdefault("operations", {})["paused"] = True
    settings.setdefault("scheduler", {})["run_mode"] = "paused"
    record.settings = settings
    flag_modified(record, "settings")
    bump_config_version(record, operator_id=operator_id)
    db.add(
        AuditEventRecord(
            event_id=str(uuid4()),
            tenant_id=tenant_id,
            category="tenant_operations",
            action="tenant.operations_paused",
            status="succeeded",
            details={"operator_id": operator_id, "reason": reason},
            created_at=_utcnow(),
        )
    )
    db.commit()
    db.refresh(record)
    return present_lifecycle(record)


def resume_operations(
    db: Session,
    *,
    tenant_id: str,
    operator_id: str,
    config_version: int,
    reason: str | None,
) -> dict[str, Any]:
    record = _get_tenant_or_404(db, tenant_id)
    _assert_version(record, config_version)
    settings = copy.deepcopy(record.settings or {})
    settings.setdefault("operations", {})["paused"] = False
    # Do not auto-enable scheduler — activation policy keeps run_mode separate.
    db.add(
        AuditEventRecord(
            event_id=str(uuid4()),
            tenant_id=tenant_id,
            category="tenant_operations",
            action="tenant.operations_resumed",
            status="succeeded",
            details={"operator_id": operator_id, "reason": reason},
            created_at=_utcnow(),
        )
    )
    record.settings = settings
    flag_modified(record, "settings")
    bump_config_version(record, operator_id=operator_id)
    db.commit()
    db.refresh(record)
    return present_lifecycle(record)


ALLOWED_SETTINGS_SECTIONS = frozenset(
    {"identity", "modules", "services", "routing", "intake", "integrations"}
)


def get_settings_section(db: Session, tenant_id: str, section: str) -> dict[str, Any]:
    if section not in ALLOWED_SETTINGS_SECTIONS:
        raise HTTPException(status_code=404, detail="Unknown settings section.")
    record = _get_tenant_or_404(db, tenant_id)
    settings = record.settings or {}
    if section == "identity":
        payload = (settings.get("company") or {}) | {
            "name": record.name,
            "slug": record.slug,
        }
    elif section == "modules":
        payload = {
            "enabled_job_types": record.enabled_job_types or [],
            "allowed_integrations": record.allowed_integrations or [],
            "capabilities": settings.get("capabilities") or {},
        }
    elif section == "services":
        payload = settings.get("memory") or {}
    elif section == "routing":
        payload = settings.get("routing") or {}
    elif section == "intake":
        payload = settings.get("intake") or {}
    elif section == "integrations":
        payload = {
            "integrations": settings.get("integrations") or {},
            "google_sheets": settings.get("google_sheets") or {},
        }
    else:
        payload = {}
    return {
        "tenant_id": tenant_id,
        "section": section,
        "config_version": int(record.config_version or 1),
        "payload": payload,
    }


def patch_settings_section(
    db: Session,
    *,
    tenant_id: str,
    section: str,
    operator_id: str,
    config_version: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if section not in ALLOWED_SETTINGS_SECTIONS:
        raise HTTPException(status_code=404, detail="Unknown settings section.")
    record = _get_tenant_or_404(db, tenant_id)
    _assert_version(record, config_version)
    settings = copy.deepcopy(record.settings or {})
    if section == "identity":
        company = settings.setdefault("company", {})
        for key in ("industries", "org_number", "primary_contact", "contact_email", "phone", "timezone", "language"):
            if key in payload:
                company[key] = payload[key]
        if payload.get("name"):
            record.name = str(payload["name"])
        if payload.get("slug"):
            record.slug = str(payload["slug"])
    elif section == "modules":
        if "enabled_job_types" in payload:
            record.enabled_job_types = list(payload["enabled_job_types"] or [])
        if "allowed_integrations" in payload:
            record.allowed_integrations = list(payload["allowed_integrations"] or [])
        if "capabilities" in payload:
            settings["capabilities"] = payload["capabilities"]
    elif section == "services":
        settings["memory"] = {**(settings.get("memory") or {}), **payload}
    elif section == "routing":
        settings["routing"] = {**(settings.get("routing") or {}), **payload}
    elif section == "intake":
        settings["intake"] = {**(settings.get("intake") or {}), **payload}
    elif section == "integrations":
        if "integrations" in payload:
            settings["integrations"] = payload["integrations"]
        if "google_sheets" in payload:
            settings["google_sheets"] = payload["google_sheets"]
    record.settings = settings
    flag_modified(record, "settings")
    bump_config_version(record, operator_id=operator_id)
    db.add(
        AuditEventRecord(
            event_id=str(uuid4()),
            tenant_id=tenant_id,
            category="tenant_settings",
            action=f"tenant.settings.{section}_updated",
            status="succeeded",
            details={"operator_id": operator_id, "section": section},
            created_at=_utcnow(),
        )
    )
    db.commit()
    db.refresh(record)
    return get_settings_section(db, tenant_id, section)


def list_activation_history(db: Session, tenant_id: str) -> dict[str, Any]:
    _get_tenant_or_404(db, tenant_id)
    rows = (
        db.query(TenantActivationSnapshotRecord)
        .filter(TenantActivationSnapshotRecord.tenant_id == tenant_id)
        .order_by(TenantActivationSnapshotRecord.activated_at.desc())
        .all()
    )
    return {
        "tenant_id": tenant_id,
        "items": [
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "config_version": row.config_version,
                "plan_hash": row.plan_hash,
                "readiness_check_version": row.readiness_check_version,
                "activated_by_operator_id": row.activated_by_operator_id,
                "activated_at": row.activated_at,
            }
            for row in rows
        ],
    }


def save_activation_snapshot(
    db: Session,
    *,
    tenant_id: str,
    snapshot_id: str,
    config_version: int,
    plan_hash: str,
    readiness_check_version: int,
    snapshot_json: dict[str, Any],
    operator_id: str,
    activated_at: datetime,
) -> TenantActivationSnapshotRecord:
    row = TenantActivationSnapshotRecord(
        id=snapshot_id,
        tenant_id=tenant_id,
        config_version=config_version,
        plan_hash=plan_hash,
        readiness_check_version=readiness_check_version,
        snapshot_json=snapshot_json,
        activated_by_operator_id=operator_id,
        activated_at=activated_at,
    )
    db.add(row)
    return row
