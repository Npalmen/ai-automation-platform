"""Preview (dry-run) for customer settings domain changes."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.admin.customer_settings.domains import assert_domain_permission
from app.admin.customer_settings.readiness_invalidation import readiness_domains_for_patch
from app.admin.customer_settings.validation import (
    DomainValidationError,
    compute_consequences,
    compute_runtime_projection_changes,
    materialize_domain_config,
    validate_domain_config,
)
from app.core.admin_session import OperatorIdentity
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


def preview_fingerprint(
    *,
    tenant_id: str,
    config_version: int,
    domain: str,
    normalized_payload: dict[str, Any],
) -> str:
    raw = json.dumps(
        {
            "tenant_id": tenant_id,
            "config_version": config_version,
            "domain": domain,
            "payload": normalized_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def build_domain_preview(
    db: Session,
    *,
    record: TenantConfigRecord,
    domain: str,
    payload: dict[str, Any],
    operator: OperatorIdentity,
) -> dict[str, Any]:
    assert_domain_permission(operator, domain, "preview")
    validation = validate_domain_config(db, domain=domain, payload=payload, record=record)
    projected_settings = materialize_domain_config(
        domain=domain,
        settings=record.settings or {},
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
    runtime = compute_runtime_projection_changes(
        db,
        domain=domain,
        record=record,
        settings=projected_settings,
        normalized_payload=validation.normalized_payload,
    )
    return {
        "tenant_id": record.tenant_id,
        "domain": domain,
        "config_version": int(record.config_version or 1),
        "valid": consequences["valid"] and not validation.blocking,
        "warnings": consequences["warnings"] + validation.warnings,
        "blocking": consequences["blocking"] + validation.blocking,
        "readiness_domains_affected": readiness_domains_for_patch(domain),
        "runtime_gates": consequences["runtime_gates"],
        "credential_preservation": validation.credential_preservation,
        "normalized_payload": validation.normalized_payload,
        "preview_fingerprint": preview_fingerprint(
            tenant_id=record.tenant_id,
            config_version=int(record.config_version or 1),
            domain=domain,
            normalized_payload=validation.normalized_payload,
        ),
        "finance_destination": consequences.get("finance_destination"),
    }
