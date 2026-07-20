"""Server-side effective config resolution for Slice 2A onboarding."""

from __future__ import annotations

from typing import Any

from app.admin.onboarding.draft_schemas import (
    DataStartDraftPayload,
    RoutingDraftPayload,
    ServiceProfileDraftPayload,
)
from app.admin.onboarding.slice2a_registry import (
    DATA_START_MODES,
    INTERNAL_ROUTING_DESTINATIONS,
    capability_needs_service_profile,
    recommended_profiles_for_capabilities,
)
from app.admin.onboarding.type_mapping import lead_type_for_service_type
from app.admin.onboarding.field_mode import resolve_field_mode
from app.service_profiles.registry import get_profile

INTAKE_ENFORCEMENT_METADATA_ONLY = "metadata_only"


def _parse_service_profile_draft(payload: dict | None) -> ServiceProfileDraftPayload:
    if not payload:
        return ServiceProfileDraftPayload()
    return ServiceProfileDraftPayload.model_validate(payload)


def _parse_routing_draft(payload: dict | None) -> RoutingDraftPayload:
    if not payload:
        return RoutingDraftPayload()
    return RoutingDraftPayload.model_validate(payload)


def _parse_data_start_draft(payload: dict | None) -> DataStartDraftPayload:
    if not payload:
        return DataStartDraftPayload()
    return DataStartDraftPayload.model_validate(payload)


def validate_service_profile_draft(
    draft: ServiceProfileDraftPayload,
    *,
    capability_keys: list[str],
    allowed_profile_keys: set[str],
    allowed_field_keys: set[str],
) -> list[str]:
    errors: list[str] = []
    for key in draft.selected_profiles:
        if key not in allowed_profile_keys:
            errors.append(f"Unknown or unavailable service profile: {key}")
    if capability_needs_service_profile(capability_keys) and not draft.selected_profiles:
        errors.append("At least one service profile required for selected capabilities.")
    selected = set(draft.selected_profiles)
    for service_type, fields in draft.lead_requirements.items():
        if service_type not in selected:
            errors.append(f"Lead requirements for unselected profile: {service_type}")
            continue
        profile = get_profile(service_type)
        if profile is None:
            errors.append(f"Unknown profile in lead requirements: {service_type}")
            continue
        profile_fields = set(profile.required_fields) | set(profile.optional_fields)
        for field_key, mode in fields.items():
            if field_key not in allowed_field_keys or field_key not in profile_fields:
                errors.append(f"Unknown field '{field_key}' for profile '{service_type}'")
            if mode not in ("required", "optional", "inherit", "skip"):
                errors.append(f"Invalid mode for {service_type}.{field_key}")
    return errors


def build_effective_service_config(
    modules_payload: dict,
    sp_payload: dict | None,
    *,
    allowed_profile_keys: set[str],
    allowed_field_keys: set[str],
) -> dict[str, Any]:
    draft = _parse_service_profile_draft(sp_payload)
    caps = modules_payload.get("capabilities") or []
    errors = validate_service_profile_draft(
        draft,
        capability_keys=caps,
        allowed_profile_keys=allowed_profile_keys,
        allowed_field_keys=allowed_field_keys,
    )
    profiles_out: list[dict[str, Any]] = []
    for service_type in draft.selected_profiles:
        profile = get_profile(service_type)
        if profile is None:
            continue
        field_overrides = draft.lead_requirements.get(service_type) or {}
        required: list[str] = []
        optional: list[str] = []
        field_details: list[dict[str, Any]] = []
        all_fields = list(dict.fromkeys([*profile.required_fields, *profile.optional_fields]))
        for field_key in all_fields:
            resolved = resolve_field_mode(
                field_key=field_key,
                profile=profile,
                override=field_overrides.get(field_key),
            )
            effective = resolved["effective"]
            field_details.append(
                {
                    "field_key": field_key,
                    "platform_default": resolved["platform_default"],
                    "override": None if resolved["override"] == "inherit" else resolved["override"],
                    "effective": effective,
                    "source": resolved["source"],
                    "override_label_sv": resolved["override_label_sv"],
                    "effective_label_sv": resolved["effective_label_sv"],
                }
            )
            if effective == "required":
                required.append(field_key)
            elif effective == "optional":
                optional.append(field_key)
        profiles_out.append(
            {
                "service_type": service_type,
                "default_route": profile.default_route,
                "required_fields": required,
                "optional_fields": optional,
                "fields": field_details,
            }
        )
    return {
        "selected_profiles": list(draft.selected_profiles),
        "recommended_profiles": recommended_profiles_for_capabilities(caps),
        "profiles": profiles_out,
        "valid": len(errors) == 0,
        "errors": errors,
        "needs_profile": capability_needs_service_profile(caps),
    }


def materialize_lead_config(effective: dict[str, Any]) -> dict[str, Any]:
    services: list[dict[str, Any]] = []
    lead_requirements: dict[str, dict[str, list[str]]] = {}
    for profile_entry in effective.get("profiles") or []:
        service_type = profile_entry["service_type"]
        lead_type = lead_type_for_service_type(service_type)
        services.append(
            {
                "lead_type": lead_type or service_type,
                "name": service_type.replace("_", " ").title(),
                "keywords": [],
            }
        )
        required = profile_entry.get("required_fields") or []
        optional = profile_entry.get("optional_fields") or []
        if required or optional:
            lead_requirements[service_type] = {
                "required": list(required),
                "optional": list(optional),
            }
    return {"services": services, "lead_requirements": lead_requirements}


def validate_routing_draft(
    draft: RoutingDraftPayload,
    *,
    selected_profiles: list[str],
) -> list[str]:
    errors: list[str] = []
    selected = set(selected_profiles)
    for service_type, route in draft.route_overrides.items():
        if service_type not in selected:
            errors.append(f"Routing override for unselected profile: {service_type}")
        if route is None:
            continue
        if route not in INTERNAL_ROUTING_DESTINATIONS:
            errors.append(f"Unknown routing destination: {route}")
        if route == "":
            errors.append(f"Empty routing override for {service_type}")
    return errors


def build_effective_routing(
    sp_payload: dict | None,
    routing_payload: dict | None,
) -> dict[str, Any]:
    sp_draft = _parse_service_profile_draft(sp_payload)
    rt_draft = _parse_routing_draft(routing_payload)
    errors = validate_routing_draft(rt_draft, selected_profiles=sp_draft.selected_profiles)
    routes: list[dict[str, Any]] = []
    for service_type in sp_draft.selected_profiles:
        profile = get_profile(service_type)
        if profile is None:
            continue
        platform_default = profile.default_route
        override = rt_draft.route_overrides.get(service_type)
        if override is None or service_type not in rt_draft.route_overrides:
            effective = platform_default
            source = "platform_default"
        else:
            effective = override
            source = "tenant_override"
        if not effective:
            effective = "manual_review"
            source = "fallback_manual_review"
        routes.append(
            {
                "service_type": service_type,
                "platform_default": platform_default,
                "override": override if service_type in rt_draft.route_overrides else None,
                "effective": effective,
                "source": source,
            }
        )
    return {
        "routes": routes,
        "valid": len(errors) == 0,
        "errors": errors,
    }


def materialize_internal_routing_hints(effective: dict[str, Any]) -> dict[str, str]:
    hints: dict[str, str] = {}
    for route in effective.get("routes") or []:
        if route.get("source") == "tenant_override" and route.get("override"):
            hints[route["service_type"]] = route["override"]
    return hints


def build_effective_data_start(data_start_payload: dict | None) -> dict[str, Any]:
    draft = _parse_data_start_draft(data_start_payload)
    mode_def = DATA_START_MODES.get(draft.mode)
    mode_valid = mode_def is not None and mode_def.supported_in_current_slice
    return {
        "mode": draft.mode,
        "mode_valid": mode_valid,
        "cutoff_strategy": "server_generated_at_activation",
        "cutoff_strategy_status": "passed" if mode_valid else "failed",
        "runtime_enforcement": "enforced" if mode_valid else "not_verifiable",
        "enforcement": "utc_internal_date" if mode_valid else INTAKE_ENFORCEMENT_METADATA_ONLY,
        "recommended": bool(mode_def and mode_def.recommended),
        "valid": mode_valid,
        "errors": [] if mode_valid else [f"Unsupported data start mode: {draft.mode}"],
    }


def build_effective_config_summary(
    modules_payload: dict,
    sp_payload: dict | None,
    routing_payload: dict | None,
    data_start_payload: dict | None,
    *,
    allowed_profile_keys: set[str],
    allowed_field_keys: set[str],
) -> dict[str, Any]:
    service = build_effective_service_config(
        modules_payload,
        sp_payload,
        allowed_profile_keys=allowed_profile_keys,
        allowed_field_keys=allowed_field_keys,
    )
    routing = build_effective_routing(sp_payload, routing_payload)
    data_start = build_effective_data_start(data_start_payload)
    return {
        "service_profile": service,
        "routing": routing,
        "data_start": data_start,
    }


def plan_fingerprint_from_drafts(
    modules_payload: dict,
    sp_payload: dict | None,
    routing_payload: dict | None,
    data_start_payload: dict | None,
    *,
    allowed_profile_keys: set[str],
    allowed_field_keys: set[str],
) -> dict[str, Any]:
    sp = _parse_service_profile_draft(sp_payload)
    rt = _parse_routing_draft(routing_payload)
    ds = _parse_data_start_draft(data_start_payload)
    normalized_lead: dict[str, dict[str, str]] = {}
    for st, fields in sorted(sp.lead_requirements.items()):
        normalized_lead[st] = {fk: mode for fk, mode in sorted(fields.items()) if mode != "inherit"}
    normalized_routing = {
        k: v for k, v in sorted(rt.route_overrides.items()) if v is not None
    }
    effective = build_effective_config_summary(
        modules_payload,
        sp_payload,
        routing_payload,
        data_start_payload,
        allowed_profile_keys=allowed_profile_keys,
        allowed_field_keys=allowed_field_keys,
    )
    return {
        "capabilities": sorted(modules_payload.get("capabilities") or []),
        "integrations": sorted(modules_payload.get("integrations") or []),
        "selected_profiles": sorted(sp.selected_profiles),
        "lead_requirements": normalized_lead,
        "route_overrides": normalized_routing,
        "data_start_mode": ds.mode,
        "effective_valid": {
            "service_profile": effective["service_profile"]["valid"],
            "routing": effective["routing"]["valid"],
            "data_start": effective["data_start"]["valid"],
        },
    }


def materialize_slice2a_config(
    tenant_settings: dict,
    *,
    modules_payload: dict,
    sp_payload: dict | None,
    routing_payload: dict | None,
    data_start_payload: dict | None,
    activation_cutoff_at,
) -> dict:
    """Merge Slice 2A drafts into tenant settings (canonical paths)."""
    from app.admin.onboarding.slice2a_registry import (
        SETTINGS_SCHEMA_VERSION,
        lead_field_registry,
        profiles_for_onboarding,
    )

    allowed_profile_keys = {
        p["key"] for p in profiles_for_onboarding() if p["availability"] == "available"
    }
    allowed_field_keys = {f["key"] for f in lead_field_registry()}
    settings = dict(tenant_settings or {})
    settings["schema_version"] = SETTINGS_SCHEMA_VERSION
    effective_service = build_effective_service_config(
        modules_payload,
        sp_payload,
        allowed_profile_keys=allowed_profile_keys,
        allowed_field_keys=allowed_field_keys,
    )
    effective_routing = build_effective_routing(sp_payload, routing_payload)
    effective_data_start = build_effective_data_start(data_start_payload)

    memory = dict(settings.get("memory") or {})
    lead_config = dict(memory.get("lead_config") or {})
    lead_config.update(materialize_lead_config(effective_service))
    memory["lead_config"] = lead_config

    internal_hints = dict(memory.get("internal_routing_hints") or {})
    internal_hints.update(materialize_internal_routing_hints(effective_routing))
    memory["internal_routing_hints"] = internal_hints
    settings["memory"] = memory

    intake = dict(settings.get("intake") or {})
    if effective_data_start["valid"]:
        intake["mode"] = effective_data_start["mode"]
        intake["enforcement"] = INTAKE_ENFORCEMENT_METADATA_ONLY
        if not intake.get("activation_cutoff_at"):
            intake["activation_cutoff_at"] = activation_cutoff_at.isoformat()
    settings["intake"] = intake
    return settings


def plan_fingerprint_slice2b(
    integrations_payload: dict | None,
    external_routing_payload: dict | None,
    *,
    verification_fingerprints_hash: str,
    integration_state_revision: int,
) -> dict[str, Any]:
    import hashlib
    import json

    integ = integrations_payload or {}
    er = external_routing_payload or {}
    integ_raw = json.dumps(integ, sort_keys=True, separators=(",", ":"))
    er_raw = json.dumps(er, sort_keys=True, separators=(",", ":"))
    return {
        "integrations_config_hash": hashlib.sha256(integ_raw.encode("utf-8")).hexdigest(),
        "external_routing_hash": hashlib.sha256(er_raw.encode("utf-8")).hexdigest(),
        "verification_fingerprints_hash": verification_fingerprints_hash,
        "integration_state_revision": integration_state_revision,
    }


def materialize_slice2b_config(
    tenant_settings: dict,
    *,
    modules_payload: dict,
    integrations_payload: dict | None,
    external_routing_payload: dict | None,
    verification_records: list,
    integration_state_revision: int,
    tenant_slug: str,
) -> dict:
    """Merge Slice 2B drafts into tenant settings (schema v3 paths)."""
    from app.admin.onboarding.integration_draft_schemas import (
        ExternalRoutingDraftPayload,
        IntegrationsDraftPayload,
    )
    from app.admin.onboarding.integration_fingerprint import build_gmail_label_query
    from app.admin.onboarding.slice2b_registry import SETTINGS_SCHEMA_VERSION_SLICE2B

    settings = dict(tenant_settings or {})
    settings["schema_version"] = SETTINGS_SCHEMA_VERSION_SLICE2B
    integ_draft = IntegrationsDraftPayload.model_validate(integrations_payload or {})
    er_draft = ExternalRoutingDraftPayload.model_validate(external_routing_payload or {})

    intake = dict(settings.get("intake") or {})
    gmail_cfg = dict(intake.get("gmail") or {})
    if integ_draft.gmail.label_scope_slug.strip():
        try:
            gmail_cfg["label_query"] = build_gmail_label_query(integ_draft.gmail.label_scope_slug)
        except ValueError:
            pass
    gmail_cfg["unread_only"] = True
    gmail_cfg["scheduler"] = "paused"
    intake["gmail"] = gmail_cfg
    settings["intake"] = intake

    gs = dict(settings.get("google_sheets") or {})
    if integ_draft.google_sheets.spreadsheet_id.strip():
        gs["spreadsheet_id"] = integ_draft.google_sheets.spreadsheet_id.strip()
        gs["export_tabs"] = list(integ_draft.google_sheets.export_tabs)
    settings["google_sheets"] = gs

    integrations_block = dict(settings.get("integrations") or {})
    external_targets: dict[str, Any] = {}
    lead_target = er_draft.targets.get("lead")
    if lead_target and lead_target.board_id:
        external_targets["lead"] = {
            "target_type": "monday_board",
            "board_id": lead_target.board_id,
            "board_name": lead_target.board_name,
            "group_id": lead_target.group_id,
            "group_name": lead_target.group_name,
        }
    integrations_block["external_routing_targets"] = external_targets
    integrations_block["state_revision"] = integration_state_revision

    verification_out: dict[str, Any] = {}
    for record in verification_records:
        if record.verification_status != "verified":
            continue
        verification_out[record.integration_key] = {
            "verified_at": record.verified_at.isoformat() if record.verified_at else None,
            "source_class": record.source_class,
            "config_fingerprint": record.config_fingerprint,
        }
    integrations_block["verification"] = verification_out
    settings["integrations"] = integrations_block

    memory = dict(settings.get("memory") or {})
    routing_hints = dict(memory.get("routing_hints") or {})
    if lead_target and lead_target.board_id:
        routing_hints["lead"] = {
            "system": "monday",
            "target": {
                "board_id": lead_target.board_id,
                "board_name": lead_target.board_name,
                "group_id": lead_target.group_id,
                "group_name": lead_target.group_name,
            },
        }
    memory["routing_hints"] = routing_hints
    settings["memory"] = memory
    return settings
