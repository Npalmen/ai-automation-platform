"""Step evaluation for service profile, routing, integrations, and data start."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.admin.onboarding.effective_config import (
    build_effective_data_start,
    build_effective_routing,
    build_effective_service_config,
)
from app.admin.onboarding.registries import (
    INTEGRATIONS,
    PRODUCT_CAPABILITIES,
    IntegrationDefinition,
)
from app.admin.onboarding.slice2a_registry import (
    capability_needs_service_profile,
    lead_field_registry,
    profiles_for_onboarding,
)
from app.core.settings import Settings
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


def _allowed_profile_keys() -> set[str]:
    return {p["key"] for p in profiles_for_onboarding() if p["availability"] == "available"}


def _allowed_field_keys() -> set[str]:
    return {f["key"] for f in lead_field_registry()}


def _selected_capabilities(modules_draft: dict) -> list[str]:
    return list(modules_draft.get("capabilities") or [])


def _selected_integrations(modules_draft: dict) -> list[str]:
    return list(modules_draft.get("integrations") or [])


def _required_integrations_for_capabilities(capability_keys: list[str]) -> set[str]:
    from app.admin.onboarding.integration_groups import registry_keys_for_group

    required: set[str] = set()
    for key in capability_keys:
        cap = PRODUCT_CAPABILITIES.get(key)
        if cap:
            required.update(cap.required_integrations)
            for group in cap.required_integration_groups:
                required.update(registry_keys_for_group(group))
    return required


def evaluate_service_profile_step(
    *,
    modules_draft: dict,
    tenant: TenantConfigRecord | None,
    service_profile_draft: dict | None = None,
) -> dict[str, Any]:
    caps = _selected_capabilities(modules_draft)
    if not caps:
        return {
            "step_status": "not_applicable",
            "verification_level": "not_applicable",
            "blocks_activation": False,
            "read_only": False,
            "read_only_reason": None,
            "details": {"capabilities": []},
        }

    if not capability_needs_service_profile(caps):
        return {
            "step_status": "not_applicable",
            "verification_level": "not_applicable",
            "blocks_activation": False,
            "read_only": False,
            "read_only_reason": None,
            "details": {},
        }

    effective = build_effective_service_config(
        modules_draft,
        service_profile_draft,
        allowed_profile_keys=_allowed_profile_keys(),
        allowed_field_keys=_allowed_field_keys(),
    )
    if not effective["valid"]:
        status = "in_progress" if not effective.get("selected_profiles") else "blocked"
        return {
            "step_status": status,
            "verification_level": "declared",
            "blocks_activation": True,
            "read_only": False,
            "read_only_reason": None,
            "details": {"errors": effective.get("errors"), "effective": effective},
        }

    return {
        "step_status": "completed",
        "verification_level": "locally_verified",
        "blocks_activation": False,
        "read_only": False,
        "read_only_reason": None,
        "details": {"effective": effective},
    }


def evaluate_routing_step(
    *,
    modules_draft: dict,
    service_profile_draft: dict | None,
    routing_draft: dict | None,
) -> dict[str, Any]:
    caps = _selected_capabilities(modules_draft)
    effective_sp = build_effective_service_config(
        modules_draft,
        service_profile_draft,
        allowed_profile_keys=_allowed_profile_keys(),
        allowed_field_keys=_allowed_field_keys(),
    )
    if not effective_sp.get("selected_profiles"):
        if not capability_needs_service_profile(caps):
            return {
                "step_status": "not_applicable",
                "verification_level": "not_applicable",
                "blocks_activation": False,
                "read_only": False,
                "read_only_reason": None,
                "details": {},
            }
        return {
            "step_status": "not_started",
            "verification_level": "declared",
            "blocks_activation": True,
            "read_only": False,
            "read_only_reason": None,
            "details": {},
        }

    effective = build_effective_routing(service_profile_draft, routing_draft)
    if not effective["valid"]:
        return {
            "step_status": "blocked",
            "verification_level": "declared",
            "blocks_activation": True,
            "read_only": False,
            "read_only_reason": None,
            "details": {"errors": effective.get("errors"), "effective": effective},
        }

    return {
        "step_status": "completed",
        "verification_level": "locally_verified",
        "blocks_activation": False,
        "read_only": False,
        "read_only_reason": None,
        "details": {"effective": effective},
    }


def _integration_status(
    db: Session,
    tenant: TenantConfigRecord | None,
    integ: IntegrationDefinition,
    settings: Settings,
) -> dict[str, Any]:
    tenant_id = tenant.tenant_id if tenant else ""
    allowed = set(tenant.allowed_integrations or []) if tenant else set()
    requested = integ.allowed_integration_key in allowed

    connected = False
    locally_verified = False

    if integ.credential_model == "platform_env":
        if integ.key == "gmail":
            connected = bool(settings.GOOGLE_MAIL_ACCESS_TOKEN)
        elif integ.key == "monday":
            connected = bool(settings.MONDAY_API_KEY)
        elif integ.key == "fortnox":
            connected = bool(getattr(settings, "FORTNOX_ACCESS_TOKEN", ""))
        locally_verified = connected
    elif integ.credential_model == "per_tenant_oauth":
        row = (
            db.query(OAuthCredentialRecord)
            .filter(
                OAuthCredentialRecord.tenant_id == tenant_id,
                OAuthCredentialRecord.provider == "visma",
            )
            .first()
        )
        connected = row is not None
        locally_verified = connected
    elif integ.credential_model == "tenant_settings":
        gs = ((tenant.settings or {}).get("google_sheets") or {}) if tenant else {}
        connected = bool(gs.get("spreadsheet_id"))
        locally_verified = connected

    return {
        "integration_key": integ.key,
        "label": integ.label_sv,
        "requested": requested,
        "connected": connected,
        "locally_verified": locally_verified,
        "credential_model": integ.credential_model,
    }


def evaluate_integrations_step(
    db: Session,
    *,
    modules_draft: dict,
    tenant: TenantConfigRecord | None,
    settings: Settings,
    session_id: str | None = None,
) -> dict[str, Any]:
    from app.admin.onboarding.integration_draft_schemas import IntegrationsDraftPayload
    from app.admin.onboarding.integration_groups import (
        evaluate_required_integration_groups,
        registry_keys_for_group,
        required_integration_groups_for_capabilities,
        unsatisfied_required_groups,
    )
    from app.admin.onboarding.integration_selection_draft import effective_selection_status
    from app.admin.onboarding.integration_verification import IntegrationVerificationStore
    from app.admin.onboarding.repository import OnboardingRepository
    from app.integrations.keys import INTEGRATION_REGISTRY

    caps = _selected_capabilities(modules_draft)
    explicit_integrations = _selected_integrations(modules_draft)
    required = _required_integrations_for_capabilities(caps)
    required_groups = required_integration_groups_for_capabilities(caps)

    integrations_draft: IntegrationsDraftPayload | None = None
    external_routing: dict = {}
    service_profile_draft: dict = {}
    routing_draft: dict = {}
    if session_id:
        integ_record = OnboardingRepository.get_draft(db, session_id, "integrations")
        try:
            integrations_draft = IntegrationsDraftPayload.model_validate(
                (integ_record.payload if integ_record else {}) or {}
            )
        except ValidationError:
            return {
                "step_status": "blocked",
                "verification_level": "declared",
                "blocks_activation": True,
                "read_only": False,
                "read_only_reason": None,
                "details": {"integrations": [], "draft_invalid": True},
            }
        er_record = OnboardingRepository.get_draft(db, session_id, "external_routing")
        external_routing = (er_record.payload if er_record else {}) or {}
        sp_record = OnboardingRepository.get_draft(db, session_id, "service_profile")
        service_profile_draft = (sp_record.payload if sp_record else {}) or {}
        rt_record = OnboardingRepository.get_draft(db, session_id, "routing")
        routing_draft = (rt_record.payload if rt_record else {}) or {}

    draft_requested = set(integrations_draft.requested_integrations if integrations_draft else [])
    selection_keys: set[str] = set()
    if integrations_draft and integrations_draft.selections:
        for canonical in integrations_draft.selections:
            meta = INTEGRATION_REGISTRY.get(canonical, {})
            selection_keys.add(str(meta.get("registry_key", canonical)))
    group_keys: set[str] = set()
    for group in required_groups:
        group_keys.update(registry_keys_for_group(group))
    all_keys = sorted(
        set(explicit_integrations) | required | draft_requested | selection_keys | group_keys
    )

    if not all_keys and not required_groups:
        return {
            "step_status": "not_applicable",
            "verification_level": "not_applicable",
            "blocks_activation": False,
            "read_only": False,
            "read_only_reason": None,
            "details": {"integrations": []},
        }

    items: list[dict[str, Any]] = []
    blocking: list[str] = []
    warnings: list[str] = []

    for key in all_keys:
        integ = INTEGRATIONS.get(key)
        if not integ or not integ.supported_in_current_slice:
            continue

        module_required = key in required or key in explicit_integrations
        selection_status, migration_review_required = (
            effective_selection_status(
                integrations_draft,
                key,
                required_by_module=module_required,
            )
            if integrations_draft
            else ("selected_required" if module_required or key in draft_requested else "not_selected", False)
        )

        if selection_status == "not_selected":
            items.append(
                {
                    "integration_key": key,
                    "label": integ.label_sv,
                    "required": False,
                    "selection_status": selection_status,
                    "migration_review_required": migration_review_required,
                    "lifecycle_status": "not_applicable",
                    "connected": False,
                    "verified": False,
                    "locally_verified": False,
                }
            )
            continue

        is_required = selection_status == "selected_required"
        legacy = _integration_status(db, tenant, integ, settings) if tenant else {}

        configured = False
        verified = False
        lifecycle = "selected"

        if integrations_draft and session_id:
            if key == "gmail":
                configured = integrations_draft.gmail.requested and bool(
                    integrations_draft.gmail.label_scope_slug.strip()
                )
                fp_record = IntegrationVerificationStore.get(db, session_id, key)
                from app.admin.onboarding.integration_fingerprint import fingerprint_gmail

                fp = fingerprint_gmail(
                    label_scope_slug=integrations_draft.gmail.label_scope_slug,
                    tenant_slug=(tenant.slug if tenant else "") or "",
                )
                verified = IntegrationVerificationStore.is_verified_for_fingerprint(
                    fp_record, expected_fingerprint=fp
                )
                if configured and verified:
                    lifecycle = "configured_not_running"
                elif configured:
                    lifecycle = "configured"
                elif is_required:
                    lifecycle = "selected"
            elif key == "visma":
                row = (
                    db.query(OAuthCredentialRecord)
                    .filter(
                        OAuthCredentialRecord.tenant_id == (tenant.tenant_id if tenant else ""),
                        OAuthCredentialRecord.provider == "visma",
                    )
                    .first()
                    if tenant
                    else None
                )
                connected = row is not None
                configured = integrations_draft.visma.requested or is_required
                fp_record = IntegrationVerificationStore.get(db, session_id, key)
                from app.admin.onboarding.integration_fingerprint import fingerprint_visma

                fp = fingerprint_visma(
                    connection_updated_at=row.updated_at or row.connected_at if row else None
                )
                verified = bool(fp) and IntegrationVerificationStore.is_verified_for_fingerprint(
                    fp_record, expected_fingerprint=fp
                )
                if verified:
                    lifecycle = "verified"
                elif connected:
                    lifecycle = "connected"
                elif configured:
                    lifecycle = "configured"
                if is_required and not verified:
                    blocking.append(key)
            elif key == "monday":
                lead_target = (external_routing.get("targets") or {}).get("lead") or {}
                board_id = str(lead_target.get("board_id") or "").strip()
                configured = bool(board_id)
                fp_record = IntegrationVerificationStore.get(db, session_id, key)
                from app.admin.onboarding.integration_fingerprint import fingerprint_monday

                fp = fingerprint_monday(
                    board_id=board_id,
                    group_id=lead_target.get("group_id"),
                ) if board_id else ""
                verified = bool(fp) and IntegrationVerificationStore.is_verified_for_fingerprint(
                    fp_record, expected_fingerprint=fp
                )
                if verified:
                    lifecycle = "verified"
                elif configured:
                    lifecycle = "configured"
                if is_required and not verified:
                    blocking.append(key)
            elif key == "google_sheets":
                configured = bool(integrations_draft.google_sheets.spreadsheet_id.strip())
                fp_record = IntegrationVerificationStore.get(db, session_id, key)
                from app.admin.onboarding.integration_fingerprint import fingerprint_google_sheets

                fp = (
                    fingerprint_google_sheets(
                        spreadsheet_id=integrations_draft.google_sheets.spreadsheet_id,
                        export_tabs=list(integrations_draft.google_sheets.export_tabs),
                    )
                    if configured
                    else ""
                )
                verified = bool(fp) and IntegrationVerificationStore.is_verified_for_fingerprint(
                    fp_record, expected_fingerprint=fp
                )
                if verified:
                    lifecycle = "verified"
                elif configured:
                    lifecycle = "connected"
                if is_required and not verified:
                    blocking.append(key)
        else:
            lifecycle = "selected" if legacy.get("requested") else "unknown"

        if key == "gmail" and is_required:
            if not configured:
                blocking.append(key)
            elif not settings.GOOGLE_MAIL_ACCESS_TOKEN:
                warnings.append("gmail_platform_credential")
        elif key == "gmail" and selection_status == "selected_optional" and not configured:
            warnings.append("gmail_optional_unconfigured")

        items.append(
            {
                "integration_key": key,
                "label": integ.label_sv,
                "required": is_required,
                "selection_status": selection_status,
                "migration_review_required": migration_review_required,
                "lifecycle_status": lifecycle,
                "connected": legacy.get("connected", False),
                "verified": verified,
                "locally_verified": verified,
            }
        )

    group_evaluations = []
    if integrations_draft and session_id and required_groups:
        group_evaluations = evaluate_required_integration_groups(
            capability_keys=caps,
            integrations_draft=integrations_draft,
            modules_draft=modules_draft,
            service_profile_draft=service_profile_draft,
            routing_draft=routing_draft,
        )
        for evaluation in unsatisfied_required_groups(group_evaluations):
            blocking.append(f"group:{evaluation.group_key}")

    if blocking:
        return {
            "step_status": "blocked",
            "verification_level": "declared",
            "blocks_activation": True,
            "read_only": False,
            "read_only_reason": None,
            "details": {
                "integrations": items,
                "blocking": blocking,
                "warnings": warnings,
                "integration_groups": [
                    {
                        "group_key": ev.group_key,
                        "satisfied": ev.satisfied,
                        "implementation": ev.implementation,
                        "reason": ev.reason,
                    }
                    for ev in group_evaluations
                ],
            },
        }

    if warnings and all(i.get("lifecycle_status") == "configured_not_running" for i in items if i["required"]):
        return {
            "step_status": "completed",
            "verification_level": "locally_verified",
            "blocks_activation": False,
            "read_only": False,
            "read_only_reason": None,
            "details": {
                "integrations": items,
                "warnings": warnings,
                "integration_groups": [
                    {
                        "group_key": ev.group_key,
                        "satisfied": ev.satisfied,
                        "implementation": ev.implementation,
                        "reason": ev.reason,
                    }
                    for ev in group_evaluations
                ],
            },
        }

    return {
        "step_status": "completed",
        "verification_level": "externally_verified",
        "blocks_activation": False,
        "read_only": False,
        "read_only_reason": None,
        "details": {
            "integrations": items,
            "integration_groups": [
                {
                    "group_key": ev.group_key,
                    "satisfied": ev.satisfied,
                    "implementation": ev.implementation,
                    "reason": ev.reason,
                }
                for ev in group_evaluations
            ],
        },
    }


def evaluate_data_start_step(
    *,
    modules_draft: dict,
    data_start_draft: dict | None = None,
) -> dict[str, Any]:
    _ = modules_draft
    effective = build_effective_data_start(data_start_draft)
    if not effective["valid"]:
        return {
            "step_status": "blocked",
            "verification_level": "declared",
            "blocks_activation": True,
            "read_only": False,
            "read_only_reason": None,
            "details": effective,
        }
    return {
        "step_status": "completed",
        "verification_level": "locally_verified",
        "blocks_activation": False,
        "read_only": False,
        "read_only_reason": None,
        "details": effective,
    }


def tenant_has_api_key(db: Session, tenant_id: str) -> bool:
    return (
        db.query(TenantApiKeyRecord)
        .filter(
            TenantApiKeyRecord.tenant_id == tenant_id,
            TenantApiKeyRecord.is_active.is_(True),
        )
        .count()
        > 0
    )
