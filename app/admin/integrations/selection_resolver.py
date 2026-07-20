"""Derive tenant integration selection from persisted config (Slice A legacy fallback)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.integrations.keys import (
    CANONICAL_INTEGRATION_KEYS,
    normalize_integration_key,
    normalize_integration_key_list,
)

SelectionStatus = Literal[
    "not_selected",
    "selected_optional",
    "selected_required",
    "migration_review_required",
]

TENANT_OAUTH_PROVIDERS: dict[str, str] = {
    "google_mail": "google_mail",
    "visma": "visma",
    "google_sheets": "google_sheets",
}

ALERT_SUPPRESSION_REASON = "integration_not_selected_after_selection_model_migration"


@dataclass(frozen=True)
class IntegrationSelectionView:
    integration_key: str
    selection_status: SelectionStatus
    requirement_source: Literal["manual", "module_recommendation", "module_requirement", "legacy_allowed"]


def _tenant_settings(record: Any) -> dict[str, Any]:
    return getattr(record, "settings", None) or {}


def _explicit_selection_status(settings: dict[str, Any], integration_key: str) -> SelectionStatus | None:
    selections = (settings.get("integrations") or {}).get("selections") or {}
    for raw_key, payload in selections.items():
        canonical = normalize_integration_key(raw_key)
        if canonical != integration_key:
            continue
        if not isinstance(payload, dict):
            continue
        status = str(payload.get("selection_status") or "").strip()
        if status in (
            "not_selected",
            "selected_optional",
            "selected_required",
            "migration_review_required",
        ):
            return status  # type: ignore[return-value]
    return None


def _has_tenant_credential(db: Session, tenant_id: str, integration_key: str) -> bool:
    provider = TENANT_OAUTH_PROVIDERS.get(integration_key)
    if provider:
        from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository

        return OAuthCredentialRepository.get(db, tenant_id, provider) is not None
    if integration_key == "google_sheets":
        settings = {}
        from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

        settings = TenantConfigRepository.get_settings(db, tenant_id)
        sheets = settings.get("google_sheets") or {}
        return bool(str(sheets.get("spreadsheet_id") or "").strip())
    return False


def _has_verified_config(settings: dict[str, Any], integration_key: str) -> bool:
    verification = (settings.get("integrations") or {}).get("verification") or {}
    for raw_key, payload in verification.items():
        canonical = normalize_integration_key(raw_key)
        if canonical != integration_key:
            continue
        if isinstance(payload, dict) and payload.get("verified_at"):
            return True
    return False


def derive_integration_selection(
    db: Session,
    record: Any,
    integration_key: str,
) -> IntegrationSelectionView:
    """Derive selection for one integration using explicit selections or legacy signals."""
    canonical = normalize_integration_key(integration_key)
    if canonical is None:
        raise ValueError(f"Unknown integration key: {integration_key}")

    settings = _tenant_settings(record)
    explicit = _explicit_selection_status(settings, canonical)
    if explicit is not None:
        source: Literal[
            "manual", "module_recommendation", "module_requirement", "legacy_allowed"
        ] = "manual"
        payload = (settings.get("integrations") or {}).get("selections") or {}
        for raw_key, item in payload.items():
            if normalize_integration_key(raw_key) == canonical and isinstance(item, dict):
                raw_source = str(item.get("requirement_source") or "").strip()
                if raw_source in (
                    "manual",
                    "module_recommendation",
                    "module_requirement",
                ):
                    source = raw_source  # type: ignore[assignment]
        return IntegrationSelectionView(
            integration_key=canonical,
            selection_status=explicit,
            requirement_source=source,
        )

    tenant_id = getattr(record, "tenant_id", "")
    allowed = set(normalize_integration_key_list(getattr(record, "allowed_integrations", None)))
    has_credential = _has_tenant_credential(db, tenant_id, canonical)
    has_verified = _has_verified_config(settings, canonical)
    in_allowed = canonical in allowed

    if has_credential and has_verified and not in_allowed:
        return IntegrationSelectionView(
            integration_key=canonical,
            selection_status="migration_review_required",
            requirement_source="legacy_allowed",
        )
    if has_credential or has_verified:
        return IntegrationSelectionView(
            integration_key=canonical,
            selection_status="selected_optional",
            requirement_source="legacy_allowed",
        )
    if in_allowed:
        return IntegrationSelectionView(
            integration_key=canonical,
            selection_status="selected_required",
            requirement_source="legacy_allowed",
        )
    return IntegrationSelectionView(
        integration_key=canonical,
        selection_status="not_selected",
        requirement_source="manual",
    )


def should_evaluate_tenant_health(selection: IntegrationSelectionView) -> bool:
    return selection.selection_status in (
        "selected_optional",
        "selected_required",
        "migration_review_required",
    )


def should_raise_tenant_warning(
    selection: IntegrationSelectionView,
    *,
    health_status: str,
    previously_healthy: bool = False,
) -> bool:
    if not should_evaluate_tenant_health(selection):
        return False
    if health_status in ("not_applicable", "not_connected"):
        return False
    if health_status == "healthy":
        return False
    if selection.selection_status == "selected_optional":
        if health_status == "not_configured":
            return False
        if health_status == "warning" and not previously_healthy:
            return False
    return health_status in ("warning", "error", "not_configured")


def list_known_integration_selections(
    db: Session,
    record: Any,
) -> dict[str, IntegrationSelectionView]:
    return {
        key: derive_integration_selection(db, record, key)
        for key in sorted(CANONICAL_INTEGRATION_KEYS)
    }


def resolve_alerts_for_unselected_integrations(
    db: Session,
    *,
    tenant_id: str,
    dry_run: bool = False,
) -> int:
    """Resolve open integration health alerts for integrations that are not selected."""
    from app.admin.alerts.audit_events import ALERT_RESOLVED, write_operator_alert_audit
    from app.admin.alerts.models import OperatorAlertRecord
    from app.admin.alerts.schemas import ACTIVE_ALERT_STATUSES
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        return 0

    selections = list_known_integration_selections(db, record)
    unselected = {
        key
        for key, view in selections.items()
        if view.selection_status == "not_selected"
    }
    if not unselected:
        return 0

    count = 0
    alerts = (
        db.query(OperatorAlertRecord)
        .filter(
            OperatorAlertRecord.tenant_id == tenant_id,
            OperatorAlertRecord.status.in_(ACTIVE_ALERT_STATUSES),
            OperatorAlertRecord.integration_key.in_(list(unselected)),
        )
        .all()
    )
    for alert in alerts:
        count += 1
        if dry_run:
            continue
        alert.status = "resolved"
        alert.resolved_at = datetime.now(timezone.utc)
        alert.resolution_reason = ALERT_SUPPRESSION_REASON
        alert.updated_at = alert.resolved_at
        alert.version += 1
        write_operator_alert_audit(
            db,
            action=ALERT_RESOLVED,
            tenant_id=tenant_id,
            details={
                "alert_id": alert.id,
                "alert_type": alert.alert_type,
                "integration_key": alert.integration_key,
                "resolution_reason": ALERT_SUPPRESSION_REASON,
            },
        )
    if not dry_run:
        db.flush()
    return count
