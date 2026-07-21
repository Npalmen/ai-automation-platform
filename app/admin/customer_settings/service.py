"""Customer settings service — post-activation configuration orchestration."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.admin.customer_settings.audit import (
    build_settings_audit_event,
    diff_field_paths,
    domain_snapshot,
)
from app.admin.customer_settings.domains import (
    assert_domain_permission,
    normalize_domain,
)
from app.admin.customer_settings.preview import build_domain_preview
from app.admin.customer_settings.presenters import _domain_payload, build_aggregate_view
from app.admin.customer_settings.readiness_invalidation import readiness_domains_for_patch
from app.admin.customer_settings.validation import (
    DomainValidationError,
    apply_runtime_projections,
    compute_consequences,
    compute_runtime_projection_changes,
    materialize_domain_config,
    validate_domain_config,
)
from app.admin.tenant_lifecycle.service import bump_config_version
from app.core.admin_session import OperatorIdentity
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository


class ConfigVersionConflict(Exception):
    def __init__(self, current_version: int):
        self.current_version = current_version
        super().__init__(f"config_version conflict: expected stale, current={current_version}")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _get_tenant_or_404(db: Session, tenant_id: str) -> TenantConfigRecord:
    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    return record


def _lock_tenant(db: Session, tenant_id: str) -> TenantConfigRecord:
    record = (
        db.query(TenantConfigRecord)
        .filter(TenantConfigRecord.tenant_id == tenant_id)
        .with_for_update()
        .first()
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Tenant not found.")
    return record


def _assert_version(record: TenantConfigRecord, expected: int) -> None:
    current = int(record.config_version or 1)
    if current != expected:
        raise ConfigVersionConflict(current)


def get_customer_settings_view(
    db: Session,
    tenant_id: str,
    operator: OperatorIdentity,
) -> dict[str, Any]:
    record = _get_tenant_or_404(db, tenant_id)
    return build_aggregate_view(db, record, operator)


def get_domain_settings(
    db: Session,
    tenant_id: str,
    domain: str,
    operator: OperatorIdentity,
) -> dict[str, Any]:
    domain = normalize_domain(domain)
    assert_domain_permission(operator, domain, "read")
    record = _get_tenant_or_404(db, tenant_id)
    return {
        "tenant_id": tenant_id,
        "domain": domain,
        "config_version": int(record.config_version or 1),
        "payload": _domain_payload(record, domain),
    }


def preview_domain_settings(
    db: Session,
    *,
    tenant_id: str,
    domain: str,
    payload: dict[str, Any],
    operator: OperatorIdentity,
) -> dict[str, Any]:
    domain = normalize_domain(domain)
    record = _get_tenant_or_404(db, tenant_id)
    try:
        return build_domain_preview(
            db,
            record=record,
            domain=domain,
            payload=payload,
            operator=operator,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DomainValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def patch_domain_settings(
    db: Session,
    *,
    tenant_id: str,
    domain: str,
    expected_config_version: int,
    payload: dict[str, Any],
    operator: OperatorIdentity,
    change_reason: str | None = None,
) -> dict[str, Any]:
    domain = normalize_domain(domain)
    try:
        assert_domain_permission(operator, domain, "write")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    try:
        record = _lock_tenant(db, tenant_id)
        _assert_version(record, expected_config_version)

        previous_version = int(record.config_version or 1)
        before_settings = copy.deepcopy(record.settings or {})
        before_snapshot = domain_snapshot(before_settings, domain)

        validation = validate_domain_config(db, domain=domain, payload=payload, record=record)
        projected_settings = materialize_domain_config(
            domain=domain,
            settings=before_settings,
            normalized_payload=validation.normalized_payload,
            record=record,
            operator_id=operator["id"],
        )
        consequences = compute_consequences(
            db,
            domain=domain,
            record=record,
            validation=validation,
            projected_settings=projected_settings,
        )
        if consequences["blocking"] or validation.blocking:
            raise DomainValidationError(
                "; ".join(consequences["blocking"] + validation.blocking)
            )

        if domain == "identity" and "name" in validation.normalized_payload:
            record.name = validation.normalized_payload["name"]

        record.settings = projected_settings
        flag_modified(record, "settings")

        runtime_projection = compute_runtime_projection_changes(
            db,
            domain=domain,
            record=record,
            settings=projected_settings,
            normalized_payload=validation.normalized_payload,
        )
        runtime_changed = apply_runtime_projections(
            db,
            domain=domain,
            record=record,
            projection=runtime_projection,
        )

        readiness_invalidated = readiness_domains_for_patch(domain)
        new_version = bump_config_version(record, operator_id=operator["id"])
        record.updated_at = _utcnow()

        after_snapshot = domain_snapshot(record.settings or {}, domain)
        changed_paths = diff_field_paths(before_snapshot, after_snapshot)

        db.add(
            build_settings_audit_event(
                tenant_id=tenant_id,
                domain=domain,
                operator_id=operator["id"],
                operator_role=operator.get("role") or "unknown",
                previous_config_version=previous_version,
                new_config_version=new_version,
                changed_paths=changed_paths,
                readiness_domains_invalidated=readiness_invalidated,
                runtime_projections_changed=runtime_changed,
                change_reason=change_reason,
                previous_summary=before_snapshot,
                new_summary=after_snapshot,
            )
        )
        db.commit()
        db.refresh(record)
    except ConfigVersionConflict as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={"message": "config_version conflict", "config_version": exc.current_version},
        ) from exc
    except DomainValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    return {
        "tenant_id": tenant_id,
        "domain": domain,
        "config_version": int(record.config_version or 1),
        "changed_domains": [domain],
        "readiness_invalidated": readiness_invalidated,
        "runtime_projections_changed": runtime_changed,
        "warnings": consequences.get("warnings", []) + validation.warnings,
        "domain_payload": _domain_payload(record, domain),
    }
