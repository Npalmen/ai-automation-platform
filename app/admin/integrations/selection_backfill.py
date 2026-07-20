"""Evidence-based backfill for settings.integrations.selections (Slice B)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.admin.integrations.selection_models import (
    IntegrationSelectionRecord,
    ensure_selections_envelope,
    parse_selections_map,
)
from app.admin.integrations.selection_sync import MIGRATION_BACKFILL_ACTOR
from app.admin.integrations.selection_resolver import (
    _has_tenant_credential,
    _has_verified_config,
)
from app.admin.onboarding.registries import INTEGRATIONS, PRODUCT_CAPABILITIES
from app.integrations.keys import (
    CANONICAL_INTEGRATION_KEYS,
    normalize_integration_key,
    normalize_integration_key_list,
    registry_key_to_canonical,
)
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

BackfillReason = Literal[
    "explicit_onboarding",
    "allowed_with_module_requirement",
    "allowed_uncertain",
    "credential_without_allowlist",
    "allowed_only_sheets_cautious",
    "no_signals",
    "already_present",
]


@dataclass
class IntegrationBackfillDecision:
    integration_key: str
    selection_status: Literal["not_selected", "selected_optional", "selected_required"]
    migration_review_required: bool
    requirement_source: Literal["legacy_backfill"] = "legacy_backfill"
    reason: BackfillReason = "no_signals"


@dataclass
class TenantBackfillReport:
    tenant_id: str
    updated: bool
    skipped: bool
    decisions: list[IntegrationBackfillDecision] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _module_required_canonical_keys(capability_keys: list[str]) -> set[str]:
    required: set[str] = set()
    for cap_key in capability_keys:
        cap = PRODUCT_CAPABILITIES.get(cap_key)
        if not cap:
            continue
        for registry_key in cap.required_integrations:
            canonical = registry_key_to_canonical(registry_key)
            if canonical:
                required.add(canonical)
    return required


def _explicit_onboarding_selection(
    settings: dict[str, Any],
    integration_key: str,
) -> bool:
    onboarding = settings.get("onboarding") or {}
    materialized = onboarding.get("integrations") or {}
    if not isinstance(materialized, dict):
        return False
    selections = materialized.get("selections") or materialized.get("requested_integrations") or []
    if isinstance(selections, dict):
        for raw_key, payload in selections.items():
            canonical = registry_key_to_canonical(raw_key) or normalize_integration_key(raw_key)
            if canonical != integration_key:
                continue
            if isinstance(payload, dict):
                return str(payload.get("selection_status", "")) != "not_selected"
            return True
    if isinstance(selections, list):
        for raw in selections:
            canonical = registry_key_to_canonical(str(raw)) or normalize_integration_key(str(raw))
            if canonical == integration_key:
                return True
    return False


def _has_sheets_evidence(settings: dict[str, Any], db: Session, tenant_id: str) -> bool:
    if _has_tenant_credential(db, tenant_id, "google_sheets"):
        return True
    if _has_verified_config(settings, "google_sheets"):
        return True
    if _explicit_onboarding_selection(settings, "google_sheets"):
        return True
    routing = (settings.get("integrations") or {}).get("external_routing_targets") or {}
    if isinstance(routing, dict) and routing:
        return False
    return False


def classify_integration_for_backfill(
    db: Session,
    record: Any,
    integration_key: str,
    *,
    capability_keys: list[str] | None = None,
) -> IntegrationBackfillDecision:
    tenant_id = getattr(record, "tenant_id", "")
    settings = getattr(record, "settings", None) or {}
    allowed = set(normalize_integration_key_list(getattr(record, "allowed_integrations", None)))
    module_required = _module_required_canonical_keys(capability_keys or [])
    has_cred = _has_tenant_credential(db, tenant_id, integration_key)
    has_verified = _has_verified_config(settings, integration_key)
    in_allowed = integration_key in allowed
    explicit = _explicit_onboarding_selection(settings, integration_key)

    if integration_key == "google_sheets":
        if explicit or (has_cred and has_verified):
            status: Literal["not_selected", "selected_optional", "selected_required"] = (
                "selected_required" if integration_key in module_required else "selected_optional"
            )
            return IntegrationBackfillDecision(
                integration_key=integration_key,
                selection_status=status,
                migration_review_required=False,
                reason="explicit_onboarding",
            )
        if in_allowed:
            return IntegrationBackfillDecision(
                integration_key=integration_key,
                selection_status="selected_optional",
                migration_review_required=True,
                reason="allowed_only_sheets_cautious",
            )
        return IntegrationBackfillDecision(
            integration_key=integration_key,
            selection_status="not_selected",
            migration_review_required=False,
            reason="no_signals",
        )

    if explicit:
        status = "selected_required" if integration_key in module_required else "selected_optional"
        return IntegrationBackfillDecision(
            integration_key=integration_key,
            selection_status=status,
            migration_review_required=False,
            reason="explicit_onboarding",
        )

    if in_allowed and integration_key in module_required:
        return IntegrationBackfillDecision(
            integration_key=integration_key,
            selection_status="selected_required",
            migration_review_required=False,
            reason="allowed_with_module_requirement",
        )

    if in_allowed:
        return IntegrationBackfillDecision(
            integration_key=integration_key,
            selection_status="selected_optional",
            migration_review_required=True,
            reason="allowed_uncertain",
        )

    if has_cred or has_verified:
        return IntegrationBackfillDecision(
            integration_key=integration_key,
            selection_status="selected_optional",
            migration_review_required=True,
            reason="credential_without_allowlist",
        )

    return IntegrationBackfillDecision(
        integration_key=integration_key,
        selection_status="not_selected",
        migration_review_required=False,
        reason="no_signals",
    )


def build_backfill_selections(
    db: Session,
    record: Any,
    *,
    capability_keys: list[str] | None = None,
) -> dict[str, IntegrationSelectionRecord]:
    if capability_keys is None:
        capability_keys = _capability_keys_from_job_types(
            list(getattr(record, "enabled_job_types", None) or [])
        )
    configured_at = _utcnow_iso()
    decisions = [
        classify_integration_for_backfill(db, record, key, capability_keys=capability_keys)
        for key in sorted(CANONICAL_INTEGRATION_KEYS)
    ]
    out: dict[str, IntegrationSelectionRecord] = {}
    for decision in decisions:
        if decision.selection_status == "not_selected" and not decision.migration_review_required:
            continue
        out[decision.integration_key] = IntegrationSelectionRecord(
            integration_key=decision.integration_key,
            selection_status=decision.selection_status,
            migration_review_required=decision.migration_review_required,
            requirement_source="legacy_backfill",
            configured_at=configured_at,
            configured_by=MIGRATION_BACKFILL_ACTOR,
        )
    return out


def backfill_tenant_selections(
    db: Session,
    tenant_id: str,
    *,
    dry_run: bool = False,
    capability_keys: list[str] | None = None,
) -> TenantBackfillReport:
    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        return TenantBackfillReport(tenant_id=tenant_id, updated=False, skipped=True, errors=["tenant_not_found"])

    settings = ensure_selections_envelope(dict(record.settings or {}))
    existing = parse_selections_map((settings.get("integrations") or {}).get("selections"))
    if existing:
        return TenantBackfillReport(
            tenant_id=tenant_id,
            updated=False,
            skipped=True,
            decisions=[],
            errors=[],
        )

    if capability_keys is None:
        capability_keys = _capability_keys_from_job_types(
            list(getattr(record, "enabled_job_types", None) or [])
        )

    decisions = [
        classify_integration_for_backfill(db, record, key, capability_keys=capability_keys)
        for key in sorted(CANONICAL_INTEGRATION_KEYS)
    ]
    full_map = build_backfill_selections(db, record, capability_keys=capability_keys)
    for decision in decisions:
        if decision.integration_key not in full_map:
            full_map[decision.integration_key] = IntegrationSelectionRecord(
                integration_key=decision.integration_key,
                selection_status=decision.selection_status,
                migration_review_required=decision.migration_review_required,
                requirement_source="legacy_backfill",
                configured_at=_utcnow_iso(),
                configured_by=MIGRATION_BACKFILL_ACTOR,
            )

    if not dry_run:
        integrations = dict(settings.get("integrations") or {})
        integrations["selections"] = {
            key: rec.to_settings_dict() for key, rec in sorted(full_map.items())
        }
        settings["integrations"] = integrations
        record.settings = settings
        try:
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(record, "settings")
        except AttributeError:
            pass

    return TenantBackfillReport(
        tenant_id=tenant_id,
        updated=not dry_run,
        skipped=dry_run,
        decisions=decisions,
    )


def verify_selections_vs_allowed_integrations(
    record: Any,
) -> dict[str, Any]:
    settings = getattr(record, "settings", None) or {}
    selections = parse_selections_map((settings.get("integrations") or {}).get("selections"))
    allowed = set(normalize_integration_key_list(getattr(record, "allowed_integrations", None)))
    writes = set(
        normalize_integration_key_list((settings.get("integrations") or {}).get("enabled_external_writes"))
    )
    selected = {
        key
        for key, rec in selections.items()
        if rec.selection_status != "not_selected"
    }
    return {
        "tenant_id": getattr(record, "tenant_id", ""),
        "selected_keys": sorted(selected),
        "allowed_integrations": sorted(allowed),
        "enabled_external_writes": sorted(writes),
        "allowed_not_in_selected": sorted(allowed - selected),
        "selected_not_in_allowed": sorted(selected - allowed),
    }


def run_backfill_all_tenants(
    db: Session,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    from app.repositories.postgres.tenant_config_models import TenantConfigRecord

    run_id = str(uuid.uuid4())
    started = datetime.now(timezone.utc)
    tenant_reports: list[dict[str, Any]] = []
    tenants = db.query(TenantConfigRecord).all()
    updated = 0
    skipped = 0

    for record in tenants:
        caps = list(getattr(record, "enabled_job_types", None) or [])
        report = backfill_tenant_selections(
            db,
            record.tenant_id,
            dry_run=dry_run,
            capability_keys=_capability_keys_from_job_types(caps),
        )
        if report.skipped and not report.errors:
            skipped += 1
        elif report.updated:
            updated += 1
        tenant_reports.append(
            {
                "tenant_id": report.tenant_id,
                "updated": report.updated,
                "skipped": report.skipped,
                "decisions": [d.__dict__ for d in report.decisions],
                "errors": report.errors,
            }
        )

    if not dry_run:
        db.flush()

    return {
        "run_id": run_id,
        "dry_run": dry_run,
        "started_at": started.isoformat(),
        "tenants_seen": len(tenants),
        "tenants_updated": updated,
        "tenants_skipped": skipped,
        "tenants": tenant_reports,
    }


def _capability_keys_from_job_types(job_types: list[str]) -> list[str]:
    caps: list[str] = []
    jt = set(job_types or [])
    for cap in PRODUCT_CAPABILITIES.values():
        if set(cap.enabled_job_types) & jt:
            caps.append(cap.key)
    return caps
