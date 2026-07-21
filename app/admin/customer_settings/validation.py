"""Shared validation, materialization, and runtime projection helpers."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.admin.customer_settings.domains import collect_forbidden_keys
from app.admin.integrations.selection_models import (
    IntegrationSelectionRecord,
    parse_selections_map,
    selections_from_registry_draft,
)
from app.admin.integrations.selection_sync import (
    RuntimeIntegrationGates,
    compute_runtime_gates_from_selections,
    sync_allowed_integrations_from_selections,
)
from app.admin.onboarding.effective_config import (
    build_effective_routing,
    build_effective_service_config,
    materialize_internal_routing_hints,
    materialize_lead_config,
    validate_routing_draft,
    validate_service_profile_draft,
)
from app.admin.onboarding.industry_registry import validate_industry_keys
from app.admin.onboarding.draft_schemas import RoutingDraftPayload, ServiceProfileDraftPayload
from app.admin.onboarding.integration_draft_schemas import (
    FinanceDestinationPatch,
    GroupImplementationDraft,
    IntegrationsDraftPayload,
    IntegrationSelectionDraft,
)
from app.admin.onboarding.integration_groups import (
    apply_finance_destination_patch,
    build_finance_destination_status,
    evaluate_required_integration_groups,
    group_implementation_from_draft,
    has_valid_accounting_routing,
    module_required_canonical_keys,
    reject_coming_later_group_implementation,
)
from app.admin.onboarding.integration_selection_draft import effective_selection_status
from app.admin.onboarding.registries import PRODUCT_CAPABILITIES, resolve_modules_to_tenant_config
from app.admin.onboarding.runtime_evaluation import validate_runtime_dependencies
from app.admin.onboarding.slice2a_registry import lead_field_registry, profiles_for_onboarding
from app.integrations.keys import INTEGRATION_REGISTRY, normalize_integration_key
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

AUTOMATION_ALLOWED_KEYS = frozenset(
    {
        "preset_key",
        "preset_version",
        "effective_policy_snapshot",
        "approval_first",
        "demo_mode",
    }
)


@dataclass
class DomainValidationResult:
    normalized_payload: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)
    credential_preservation: bool = True


@dataclass
class RuntimeProjectionChanges:
    enabled_job_types: list[str] | None = None
    allowed_integrations: list[str] | None = None
    enabled_external_writes: list[str] | None = None
    auto_actions: dict[str, Any] | None = None
    gate_details: dict[str, Any] = field(default_factory=dict)


class DomainValidationError(ValueError):
    pass


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat() + "Z"


def _allowed_profile_keys() -> set[str]:
    return {p["key"] for p in profiles_for_onboarding() if p["availability"] == "available"}


def _allowed_field_keys() -> set[str]:
    return {f["key"] for f in lead_field_registry()}


def _capability_keys_from_tenant(record: TenantConfigRecord) -> list[str]:
    settings = record.settings or {}
    caps = settings.get("capabilities")
    if isinstance(caps, dict):
        return sorted(key for key, value in caps.items() if value)
    if isinstance(caps, list):
        return sorted(str(item) for item in caps)
    return []


def modules_draft_from_tenant(record: TenantConfigRecord) -> dict[str, Any]:
    return {"capabilities": _capability_keys_from_tenant(record)}


def integrations_draft_from_tenant(settings: dict[str, Any]) -> IntegrationsDraftPayload:
    integrations = settings.get("integrations") or {}
    selections_raw = integrations.get("selections") or {}
    selections = {}
    for key, payload in (selections_raw.items() if isinstance(selections_raw, dict) else []):
        if not isinstance(payload, dict):
            continue
        canonical = normalize_integration_key(key)
        if canonical is None:
            continue
        selections[canonical] = {
            "selection_status": payload.get("selection_status", "not_selected"),
            "migration_review_required": bool(payload.get("migration_review_required", False)),
        }
    groups = group_implementation_from_draft(integrations.get("group_implementations"))
    return IntegrationsDraftPayload(
        selections=selections,
        group_implementations=groups,
    )


def validate_domain_config(
    db: Session,
    *,
    domain: str,
    payload: dict[str, Any],
    record: TenantConfigRecord,
) -> DomainValidationResult:
    forbidden = collect_forbidden_keys(payload)
    if forbidden:
        raise DomainValidationError(f"Forbidden fields in payload: {', '.join(sorted(forbidden))}")

    if domain == "identity":
        return _validate_identity(payload, record)
    if domain == "modules":
        return _validate_modules(payload, record)
    if domain == "services":
        return _validate_services(payload, record)
    if domain == "integrations":
        return _validate_integrations(db, payload, record)
    if domain == "routing":
        return _validate_routing(payload, record)
    if domain == "automation":
        return _validate_automation(payload, record)
    if domain == "intake":
        return _validate_intake(payload, record)
    raise DomainValidationError(f"Unknown domain: {domain}")


def materialize_domain_config(
    *,
    domain: str,
    settings: dict[str, Any],
    normalized_payload: dict[str, Any],
    record: TenantConfigRecord,
    operator_id: str,
) -> dict[str, Any]:
    merged = copy.deepcopy(settings or {})
    if domain == "identity":
        company = dict(merged.get("company") or {})
        for key in (
            "industries",
            "org_number",
            "primary_contact",
            "contact_email",
            "phone",
            "timezone",
            "language",
        ):
            if key in normalized_payload:
                company[key] = normalized_payload[key]
        merged["company"] = company
        return merged
    if domain == "modules":
        merged["capabilities"] = {key: True for key in normalized_payload["capabilities"]}
        return merged
    if domain == "services":
        memory = dict(merged.get("memory") or {})
        memory.update(normalized_payload.get("memory") or {})
        if "service_profile" in normalized_payload:
            sp_payload = normalized_payload["service_profile"]
            modules = modules_draft_from_tenant(record)
            effective = build_effective_service_config(
                modules,
                sp_payload,
                allowed_profile_keys=_allowed_profile_keys(),
                allowed_field_keys=_allowed_field_keys(),
            )
            lead_config = dict(memory.get("lead_config") or {})
            lead_config.update(materialize_lead_config(effective))
            memory["lead_config"] = lead_config
            memory["service_profile"] = sp_payload
        merged["memory"] = memory
        return merged
    if domain == "routing":
        routing = dict(merged.get("routing") or {})
        routing.update(normalized_payload.get("routing") or normalized_payload)
        merged["routing"] = routing
        memory = dict(merged.get("memory") or {})
        sp_payload = (memory.get("service_profile") or {})
        effective_routing = build_effective_routing(sp_payload, routing)
        internal_hints = dict(memory.get("internal_routing_hints") or {})
        internal_hints.update(materialize_internal_routing_hints(effective_routing))
        memory["internal_routing_hints"] = internal_hints
        merged["memory"] = memory
        return merged
    if domain == "integrations":
        integrations = dict(merged.get("integrations") or {})
        if "selections" in normalized_payload:
            configured_by = f"operator:{operator_id}"
            existing = parse_selections_map(integrations.get("selections"))
            patch_selections = selections_from_registry_draft(
                normalized_payload["selections"],
                configured_by=configured_by,
                configured_at=_utcnow_iso(),
            )
            existing.update(patch_selections)
            integrations["selections"] = {
                key: rec.to_settings_dict() for key, rec in sorted(existing.items())
            }
        if "group_implementations" in normalized_payload:
            current_groups = dict(integrations.get("group_implementations") or {})
            current_groups.update(normalized_payload["group_implementations"])
            integrations["group_implementations"] = current_groups
        merged["integrations"] = integrations
        return merged
    if domain == "automation":
        automation = dict(merged.get("automation") or {})
        for key, value in normalized_payload.items():
            if key in AUTOMATION_ALLOWED_KEYS:
                automation[key] = value
        merged["automation"] = automation
        return merged
    if domain == "intake":
        intake = dict(merged.get("intake") or {})
        intake.update(normalized_payload.get("intake") or normalized_payload)
        merged["intake"] = intake
        return merged
    raise DomainValidationError(f"Unknown domain: {domain}")


def compute_runtime_projection_changes(
    db: Session,
    *,
    domain: str,
    record: TenantConfigRecord,
    settings: dict[str, Any],
    normalized_payload: dict[str, Any] | None = None,
) -> RuntimeProjectionChanges:
    changes = RuntimeProjectionChanges()
    if domain == "modules":
        caps = (normalized_payload or {}).get("capabilities") or _capability_keys_from_tenant(record)
        job_types, _ = resolve_modules_to_tenant_config(caps, [])
        changes.enabled_job_types = job_types
    if domain == "integrations":
        temp = copy.deepcopy(record)
        temp.settings = settings
        gates = sync_allowed_integrations_from_selections(
            db, temp, dry_run=True, fail_closed=True, allow_expand_on_activation=False
        )
        changes.allowed_integrations = gates.allowed_integrations
        changes.enabled_external_writes = gates.enabled_external_writes
        changes.gate_details = gates.changes
    if domain == "automation" and normalized_payload:
        snapshot = normalized_payload.get("effective_policy_snapshot")
        if isinstance(snapshot, dict) and "auto_actions" in snapshot:
            changes.auto_actions = snapshot.get("auto_actions")
    return changes


def apply_runtime_projections(
    db: Session,
    *,
    domain: str,
    record: TenantConfigRecord,
    projection: RuntimeProjectionChanges,
) -> list[str]:
    changed: list[str] = []
    if domain == "modules" and projection.enabled_job_types is not None:
        record.enabled_job_types = list(projection.enabled_job_types)
        changed.append("enabled_job_types")
    if domain == "integrations":
        sync_allowed_integrations_from_selections(
            db, record, dry_run=False, fail_closed=True, allow_expand_on_activation=False
        )
        changed.extend(["allowed_integrations", "enabled_external_writes"])
    if domain == "automation" and projection.auto_actions is not None:
        record.auto_actions = dict(projection.auto_actions)
        changed.append("auto_actions")
    return changed


def compute_consequences(
    db: Session,
    *,
    domain: str,
    record: TenantConfigRecord,
    validation: DomainValidationResult,
    projected_settings: dict[str, Any],
) -> dict[str, Any]:
    settings = record.settings or {}
    modules = modules_draft_from_tenant(record)
    if domain == "modules":
        modules = {"capabilities": validation.normalized_payload.get("capabilities") or []}
    memory = projected_settings.get("memory") or settings.get("memory") or {}
    routing = projected_settings.get("routing") or settings.get("routing") or {}
    integrations_draft = integrations_draft_from_tenant(projected_settings)

    warnings = list(validation.warnings)
    blocking = list(validation.blocking)

    if domain in {"modules", "integrations", "routing"}:
        group_evals = evaluate_required_integration_groups(
            capability_keys=list(modules.get("capabilities") or []),
            integrations_draft=integrations_draft,
            modules_draft=modules,
            service_profile_draft=memory.get("service_profile"),
            routing_draft=routing,
        )
        for ev in group_evals:
            if not ev.satisfied:
                blocking.append(f"integration_group.{ev.group_key}.{ev.reason}")

    finance_status = build_finance_destination_status(
        draft=integrations_draft,
        modules_draft=modules,
        service_profile_draft=memory.get("service_profile"),
        routing_draft=routing,
        tenant_id=record.tenant_id,
    )
    if finance_status.get("active_implementation") == "manual_accounting_routing":
        if not finance_status.get("accounting_routing_valid"):
            blocking.append("finance_destination.manual_accounting_routing_missing_routing")

    runtime = compute_runtime_projection_changes(
        db,
        domain=domain,
        record=record,
        settings=projected_settings,
        normalized_payload=validation.normalized_payload,
    )

    return {
        "valid": not blocking,
        "warnings": warnings,
        "blocking": blocking,
        "runtime_gates": {
            "allowed_integrations": runtime.allowed_integrations,
            "enabled_external_writes": runtime.enabled_external_writes,
            "enabled_job_types": runtime.enabled_job_types,
            "details": runtime.gate_details,
        },
        "finance_destination": finance_status,
        "credential_preservation": validation.credential_preservation,
    }


def _validate_identity(payload: dict[str, Any], record: TenantConfigRecord) -> DomainValidationResult:
    normalized = {k: v for k, v in payload.items() if k != "slug"}
    if "slug" in payload:
        raise DomainValidationError("slug is read-only in customer settings.")
    if "industries" in normalized:
        unknown = validate_industry_keys(normalized.get("industries") or [])
        if unknown:
            raise DomainValidationError(f"Unknown industries: {', '.join(unknown)}")
    if "name" in payload:
        normalized["name"] = str(payload["name"]).strip()
    return DomainValidationResult(normalized_payload=normalized)


def _validate_modules(payload: dict[str, Any], record: TenantConfigRecord) -> DomainValidationResult:
    if "capabilities" not in payload:
        raise DomainValidationError("capabilities is required for modules domain.")
    caps = [str(c) for c in payload["capabilities"]]
    unknown = [c for c in caps if c not in PRODUCT_CAPABILITIES]
    if unknown:
        raise DomainValidationError(f"Unknown capabilities: {', '.join(unknown)}")
    unknown_runtime = validate_runtime_dependencies(caps)
    if unknown_runtime:
        raise DomainValidationError(f"Unknown runtime dependencies: {', '.join(unknown_runtime)}")
    return DomainValidationResult(normalized_payload={"capabilities": sorted(set(caps))})


def _validate_services(payload: dict[str, Any], record: TenantConfigRecord) -> DomainValidationResult:
    sp_payload = payload.get("service_profile") or payload.get("memory") or payload
    if not isinstance(sp_payload, dict):
        sp_payload = {}
    modules = modules_draft_from_tenant(record)
    draft_errors = validate_service_profile_draft(
        ServiceProfileDraftPayload.model_validate(sp_payload),
        capability_keys=modules.get("capabilities") or [],
        allowed_profile_keys=_allowed_profile_keys(),
        allowed_field_keys=_allowed_field_keys(),
    )
    if draft_errors:
        raise DomainValidationError("; ".join(draft_errors))
    return DomainValidationResult(
        normalized_payload={"service_profile": sp_payload if isinstance(sp_payload, dict) else {}},
    )


def _validate_routing(payload: dict[str, Any], record: TenantConfigRecord) -> DomainValidationResult:
    routing_payload = payload.get("routing") or payload
    if not isinstance(routing_payload, dict):
        routing_payload = {}
    memory = (record.settings or {}).get("memory") or {}
    sp_payload = memory.get("service_profile") or {}
    errors = validate_routing_draft(
        RoutingDraftPayload.model_validate(routing_payload),
        selected_profiles=list((sp_payload.get("selected_profiles") or [])),
    )
    blocking: list[str] = []
    warnings: list[str] = []
    if errors:
        raise DomainValidationError("; ".join(errors))
    modules = modules_draft_from_tenant(record)
    if "invoice_handling" in (modules.get("capabilities") or []):
        if not has_valid_accounting_routing(
            modules_draft=modules,
            service_profile_draft=sp_payload,
            routing_draft=routing_payload if isinstance(routing_payload, dict) else {},
        ):
            blocking.append("finance_destination.manual_accounting_routing_missing_routing")
    return DomainValidationResult(
        normalized_payload={"routing": routing_payload if isinstance(routing_payload, dict) else {}},
        blocking=blocking,
        warnings=warnings,
    )


def _validate_integrations(
    db: Session,
    payload: dict[str, Any],
    record: TenantConfigRecord,
) -> DomainValidationResult:
    draft = integrations_draft_from_tenant(record.settings or {})
    warnings: list[str] = []
    blocking: list[str] = []

    if "finance_destination" in payload:
        try:
            fd = FinanceDestinationPatch.model_validate(payload["finance_destination"])
        except Exception as exc:
            raise DomainValidationError(str(exc)) from exc
        try:
            draft = apply_finance_destination_patch(
                draft,
                choice=fd.choice,
                visma_disposition=fd.visma_disposition,
            )
        except ValueError as exc:
            raise DomainValidationError(str(exc)) from exc

    if "selections" in payload:
        for raw_key, sel_payload in payload["selections"].items():
            canonical = normalize_integration_key(raw_key)
            if canonical is None:
                raise DomainValidationError(f"Unknown integration key: {raw_key}")
            meta = INTEGRATION_REGISTRY.get(canonical, {})
            if meta.get("support_status") == "coming_later":
                raise DomainValidationError(f"Integration '{canonical}' is coming_later.")
            status = str((sel_payload or {}).get("selection_status", "not_selected"))
            if status not in {"not_selected", "selected_optional", "selected_required"}:
                raise DomainValidationError(f"Invalid selection_status for {canonical}.")
            draft.selections[canonical] = IntegrationSelectionDraft.model_validate(sel_payload)

    if "group_implementations" in payload:
        for group_key, impl in (payload["group_implementations"] or {}).items():
            if isinstance(impl, dict) and impl.get("type") == "integration":
                reject_coming_later_group_implementation(impl.get("integration_key"))
            draft.group_implementations[group_key] = GroupImplementationDraft.model_validate(impl)

    normalized: dict[str, Any] = {}
    if payload.get("selections") or "finance_destination" in payload:
        selection_patch: dict[str, Any] = {}
        for key, sel in draft.selections.items():
            if key in (payload.get("selections") or {}) or (
                "finance_destination" in payload and key == "visma"
            ):
                selection_patch[key] = sel.model_dump()
        if selection_patch:
            normalized["selections"] = selection_patch
    if payload.get("group_implementations") or (
        "finance_destination" in payload
        and payload["finance_destination"].get("choice") == "manual_accounting_routing"
    ):
        group_patch = {
            key: impl.model_dump()
            for key, impl in draft.group_implementations.items()
            if key in (payload.get("group_implementations") or {})
            or (
                "finance_destination" in payload
                and key == "finance_destination"
            )
        }
        if group_patch:
            normalized["group_implementations"] = group_patch

    modules = modules_draft_from_tenant(record)
    projected_draft = draft

    if payload.get("selections"):
        required_keys = module_required_canonical_keys(modules.get("capabilities") or [])
        for raw_key, sel_payload in payload["selections"].items():
            canonical = normalize_integration_key(raw_key)
            if canonical is None:
                continue
            new_status = str((sel_payload or {}).get("selection_status", "not_selected"))
            if new_status != "selected_required":
                continue
            if canonical not in required_keys:
                continue
            from app.admin.integrations.selection_resolver import (
                _has_tenant_credential,
                _has_verified_config,
            )

            if not (
                _has_tenant_credential(db, record.tenant_id, canonical)
                and _has_verified_config(record.settings or {}, canonical)
            ):
                blocking.append(f"integrations.{canonical}.required_not_verified")

    return DomainValidationResult(
        normalized_payload=normalized or payload,
        warnings=warnings,
        blocking=blocking,
        credential_preservation=True,
    )


def _validate_automation(payload: dict[str, Any], record: TenantConfigRecord) -> DomainValidationResult:
    unknown = [k for k in payload if k not in AUTOMATION_ALLOWED_KEYS]
    if unknown:
        raise DomainValidationError(f"Unsupported automation fields: {', '.join(sorted(unknown))}")
    return DomainValidationResult(normalized_payload=dict(payload))


def _validate_intake(payload: dict[str, Any], record: TenantConfigRecord) -> DomainValidationResult:
    intake_payload = payload.get("intake") or payload
    mode = intake_payload.get("mode")
    if mode is not None and not isinstance(mode, str):
        raise DomainValidationError("intake.mode must be a string.")
    return DomainValidationResult(
        normalized_payload={"intake": intake_payload if isinstance(intake_payload, dict) else {}},
    )
