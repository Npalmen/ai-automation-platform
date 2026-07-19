"""Allowlisted onboarding audit events (Slice 2B domain contract)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.repositories.postgres.audit_models import AuditEventRecord

_ONBOARDING_AUDIT_CATEGORY = "onboarding"

# Allowlisted domain actions (exact strings)
INTEGRATION_REQUESTED = "integration_requested"
INTEGRATION_CONFIGURATION_UPDATED = "integration_configuration_updated"
OAUTH_CONNECTION_STARTED = "oauth_connection_started"
OAUTH_CONNECTION_COMPLETED = "oauth_connection_completed"
OAUTH_CONNECTION_FAILED = "oauth_connection_failed"
INTEGRATION_VERIFICATION_STARTED = "integration_verification_started"
INTEGRATION_VERIFICATION_SUCCEEDED = "integration_verification_succeeded"
INTEGRATION_VERIFICATION_FAILED = "integration_verification_failed"
EXTERNAL_ROUTING_UPDATED = "external_routing_updated"
EXTERNAL_ROUTING_RESET = "external_routing_reset"
INTEGRATION_CONFIG_MATERIALIZED = "integration_config_materialized"
EXTERNAL_ROUTING_MATERIALIZED = "external_routing_materialized"

ALLOWLISTED_ONBOARDING_AUDIT_ACTIONS = frozenset(
    {
        INTEGRATION_REQUESTED,
        INTEGRATION_CONFIGURATION_UPDATED,
        OAUTH_CONNECTION_STARTED,
        OAUTH_CONNECTION_COMPLETED,
        OAUTH_CONNECTION_FAILED,
        INTEGRATION_VERIFICATION_STARTED,
        INTEGRATION_VERIFICATION_SUCCEEDED,
        INTEGRATION_VERIFICATION_FAILED,
        EXTERNAL_ROUTING_UPDATED,
        EXTERNAL_ROUTING_RESET,
        INTEGRATION_CONFIG_MATERIALIZED,
        EXTERNAL_ROUTING_MATERIALIZED,
        # Slice 1/2A lifecycle (retained)
        "onboarding.session_created",
        "onboarding.identity_updated",
        "onboarding.modules_updated",
        "onboarding.automation_updated",
        "onboarding.readiness_checked",
        "onboarding.service_config_materialized",
        "onboarding.routing_config_materialized",
        "onboarding.intake_cutoff_created",
        "onboarding.activation_succeeded",
        "onboarding.session_cancelled",
        "onboarding.api_key_created",
        # transitional patched aliases
        "onboarding.integrations_patched",
        "onboarding.external_routing_patched",
        # Google Mail OAuth (operator panel + callback)
        "integration.google_mail.oauth_started",
        "integration.google_mail.oauth_connected",
        "integration.google_mail.oauth_failed",
        "integration.google_mail.oauth_disconnected",
    }
)

_BLOCKED_DETAIL_KEYS = frozenset(
    {
        "password",
        "api_key",
        "token",
        "secret",
        "credential",
        "access_token",
        "refresh_token",
        "authorization_code",
        "client_secret",
        "key_hash",
        "code",
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sanitize_audit_details(details: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in details.items():
        lower = key.lower()
        if any(part in lower for part in _BLOCKED_DETAIL_KEYS):
            continue
        if isinstance(value, dict):
            clean[key] = sanitize_audit_details(value)
        elif isinstance(value, list):
            clean[key] = [
                sanitize_audit_details(v) if isinstance(v, dict) else v for v in value
            ]
        else:
            clean[key] = value
    return clean


def emit_onboarding_audit(
    db: Session,
    *,
    tenant_id: str,
    action: str,
    status: str,
    details: dict[str, Any],
    require_allowlist: bool = True,
) -> AuditEventRecord:
    if require_allowlist and action not in ALLOWLISTED_ONBOARDING_AUDIT_ACTIONS:
        raise ValueError(f"Audit action not allowlisted: {action}")
    record = AuditEventRecord(
        event_id=str(uuid4()),
        tenant_id=tenant_id,
        category=_ONBOARDING_AUDIT_CATEGORY,
        action=action,
        status=status,
        details=sanitize_audit_details(details),
        created_at=_utcnow(),
    )
    db.add(record)
    return record
