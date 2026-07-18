"""Tenant-specific onboarding readiness aggregator (Kapitel 9)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.admin.onboarding.registries import PRODUCT_CAPABILITIES, resolve_preset
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.runtime_evaluation import evaluate_all_runtime_requirements
from app.admin.onboarding.steps import (
    evaluate_data_start_step,
    evaluate_integrations_step,
    evaluate_routing_step,
    evaluate_service_profile_step,
)
from app.core.settings import Settings
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _check(
    *,
    id: str,
    message: str,
    source_class: str,
    step_key: str | None = None,
) -> dict[str, Any]:
    return {"id": id, "message": message, "source_class": source_class, "step_key": step_key}


_GMAIL_KNOWN_LIFECYCLES = frozenset(
    {
        "configured",
        "configured_not_running",
        "selected",
        "verified",
        "connected",
        "authorization_required",
        "not_applicable",
        "unknown",
    }
)


def _append_gmail_readiness_checks(
    *,
    item: dict[str, Any],
    db: Session,
    session_id: str,
    tenant: TenantConfigRecord,
    settings: Settings,
    passed: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    not_verifiable: list[dict[str, Any]],
    blocking: list[dict[str, Any]],
) -> bool:
    """Gmail-specific readiness buckets. Returns True when ready_with_warnings is forced."""
    from app.admin.onboarding.integration_draft_schemas import IntegrationsDraftPayload
    from app.admin.onboarding.integration_fingerprint import build_gmail_label_query
    from app.admin.onboarding.integration_fingerprint import fingerprint_gmail
    from app.admin.onboarding.integration_verification import IntegrationVerificationStore
    from app.admin.onboarding.repository import OnboardingRepository

    force_ready_with_warnings = False
    lifecycle = str(item.get("lifecycle_status") or "unknown")

    if lifecycle not in _GMAIL_KNOWN_LIFECYCLES:
        blocking.append(
            _check(
                id="integration.gmail.lifecycle_unknown",
                message=f"Okänd Gmail lifecycle-status: {lifecycle}.",
                source_class="declared",
                step_key="integrations",
            )
        )
        return False

    record = OnboardingRepository.get_draft(db, session_id, "integrations")
    raw_payload = (record.payload if record else {}) or {}
    try:
        draft = IntegrationsDraftPayload.model_validate(raw_payload)
    except Exception:
        blocking.append(
            _check(
                id="integration.gmail.draft_invalid",
                message="Gmail integrationsdraft kunde inte läsas.",
                source_class="declared",
                step_key="integrations",
            )
        )
        return False

    slug = (draft.gmail.label_scope_slug or "").strip()

    if settings.GOOGLE_MAIL_ACCESS_TOKEN:
        passed.append(
            _check(
                id="integration.gmail.platform_credential",
                message="Plattformens Gmail-credential är konfigurerad.",
                source_class="platform_level",
                step_key="integrations",
            )
        )
    else:
        warnings.append(
            _check(
                id="integration.gmail.platform_credential",
                message="Plattformens Gmail-token saknas.",
                source_class="platform_level",
                step_key="integrations",
            )
        )
        force_ready_with_warnings = True

    if slug and lifecycle in ("configured", "configured_not_running"):
        try:
            query = build_gmail_label_query(slug)
            if "is:unread" in query:
                passed.append(
                    _check(
                        id="integration.gmail.label_query",
                        message="Gmail label query är giltig och innehåller is:unread.",
                        source_class="locally_verified",
                        step_key="integrations",
                    )
                )
            else:
                blocking.append(
                    _check(
                        id="integration.gmail.label_query",
                        message="Gmail label query saknar is:unread.",
                        source_class="declared",
                        step_key="integrations",
                    )
                )
        except ValueError:
            blocking.append(
                _check(
                    id="integration.gmail.label_query",
                    message="Gmail label query är ogiltig.",
                    source_class="declared",
                    step_key="integrations",
                )
            )
    elif item.get("required"):
        blocking.append(
            _check(
                id="integration.gmail.label_query",
                message="Gmail label scope saknas.",
                source_class="declared",
                step_key="integrations",
            )
        )

    not_verifiable.append(
        _check(
            id="integration.gmail.tenant_mailbox_access",
            message="Tenant mailbox/label-åtkomst är inte verifierbar i wizard.",
            source_class="not_verifiable",
            step_key="integrations",
        )
    )

    if lifecycle == "configured_not_running":
        warnings.append(
            _check(
                id="integration.gmail.live_intake",
                message="Live Gmail-intag är konfigurerat men scan är pausad.",
                source_class="not_verifiable",
                step_key="integrations",
            )
        )
    else:
        warnings.append(
            _check(
                id="integration.gmail.live_intake",
                message="Live Gmail-intag är inte verifierbart i wizard.",
                source_class="not_verifiable",
                step_key="integrations",
            )
        )
    force_ready_with_warnings = True

    warnings.append(
        _check(
            id="integration.gmail.capability_operational",
            message="Gmail-kapabilitet är inte operational (scan pausad).",
            source_class="not_verifiable",
            step_key="integrations",
        )
    )

    fp_record = IntegrationVerificationStore.get(db, session_id, "gmail")
    fp = fingerprint_gmail(
        label_scope_slug=slug,
        tenant_slug=(tenant.slug if tenant else "") or "",
    )
    verified = IntegrationVerificationStore.is_verified_for_fingerprint(
        fp_record, expected_fingerprint=fp
    )
    if lifecycle in ("configured", "configured_not_running") and not verified:
        not_verifiable.append(
            _check(
                id="integration.gmail.verification_record",
                message="Gmail-verifieringspost saknas — endast deklarerad konfiguration.",
                source_class="not_verifiable",
                step_key="integrations",
            )
        )
    elif fp_record is not None and fp_record.verification_status not in (
        "verified",
        "pending",
        "invalidated",
        "failed",
    ):
        not_verifiable.append(
            _check(
                id="integration.gmail.verification_status_unknown",
                message="Gmail-verifieringsstatus är okänd.",
                source_class="not_verifiable",
                step_key="integrations",
            )
        )

    return force_ready_with_warnings


def compute_readiness(
    db: Session,
    *,
    session_id: str,
    tenant: TenantConfigRecord,
    settings: Settings,
    check_version: int,
) -> dict[str, Any]:
    identity = OnboardingRepository.get_draft(db, session_id, "identity")
    modules = OnboardingRepository.get_draft(db, session_id, "modules")
    automation = OnboardingRepository.get_draft(db, session_id, "automation")
    service_profile = OnboardingRepository.get_draft(db, session_id, "service_profile")
    routing = OnboardingRepository.get_draft(db, session_id, "routing")
    data_start = OnboardingRepository.get_draft(db, session_id, "data_start")

    identity_payload = (identity.payload if identity else {}) or {}
    modules_payload = (modules.payload if modules else {}) or {}
    automation_payload = (automation.payload if automation else {}) or {}
    sp_payload = (service_profile.payload if service_profile else None)
    routing_payload = (routing.payload if routing else None)
    data_start_payload = (data_start.payload if data_start else None)
    snapshot = automation_payload.get("effective_policy_snapshot") or {}

    blocking: list[dict] = []
    warnings: list[dict] = []
    passed: list[dict] = []
    not_applicable: list[dict] = []
    not_verifiable: list[dict] = []
    forces_ready_with_warnings = False

    if not identity_payload.get("company_name"):
        blocking.append(
            _check(
                id="identity.company_name",
                message="Företagsnamn saknas.",
                source_class="tenant_specific",
                step_key="identity",
            )
        )
    else:
        passed.append(
            _check(
                id="identity.company_name",
                message="Företagsnamn angivet.",
                source_class="tenant_specific",
                step_key="identity",
            )
        )

    if not tenant.slug:
        blocking.append(
            _check(
                id="identity.slug",
                message="Slug saknas.",
                source_class="tenant_specific",
                step_key="identity",
            )
        )
    else:
        passed.append(
            _check(
                id="identity.slug",
                message="Slug konfigurerad.",
                source_class="tenant_specific",
                step_key="identity",
            )
        )

    caps = modules_payload.get("capabilities") or []
    if not caps:
        blocking.append(
            _check(
                id="modules.capabilities",
                message="Minst en produktkapabilitet måste väljas.",
                source_class="tenant_specific",
                step_key="modules",
            )
        )
    else:
        unknown = [c for c in caps if c not in PRODUCT_CAPABILITIES]
        if unknown:
            blocking.append(
                _check(
                    id="modules.unknown_capability",
                    message=f"Okända kapabiliteter: {', '.join(unknown)}",
                    source_class="tenant_specific",
                    step_key="modules",
                )
            )
        else:
            passed.append(
                _check(
                    id="modules.capabilities",
                    message="Produktkapabiliteter valda.",
                    source_class="tenant_specific",
                    step_key="modules",
                )
            )

    preset_key = automation_payload.get("preset_key")
    preset_version = automation_payload.get("preset_version", 1)
    preset = resolve_preset(preset_key or "", int(preset_version)) if preset_key else None
    if not preset_key or preset is None:
        blocking.append(
            _check(
                id="automation.preset",
                message="Automation preset saknas eller är ogiltig.",
                source_class="tenant_specific",
                step_key="automation",
            )
        )
    else:
        passed.append(
            _check(
                id="automation.preset",
                message=f"Automation preset: {preset_key} v{preset_version}.",
                source_class="tenant_specific",
                step_key="automation",
            )
        )

    if tenant.status != "inactive":
        blocking.append(
            _check(
                id="tenant.status",
                message="Tenant måste vara inactive före aktivering.",
                source_class="tenant_specific",
            )
        )

    runtime_bundle = evaluate_all_runtime_requirements(
        db,
        capability_keys=caps,
        snapshot=snapshot,
        tenant=tenant,
        preset_key=preset_key,
        preset_version=int(preset_version) if preset_version else None,
    )
    blocking.extend(runtime_bundle.get("readiness_blocking") or [])
    warnings.extend(runtime_bundle.get("readiness_warnings") or [])
    if runtime_bundle.get("forces_ready_with_warnings"):
        forces_ready_with_warnings = True

    sp = evaluate_service_profile_step(
        modules_draft=modules_payload,
        tenant=tenant,
        service_profile_draft=sp_payload,
    )
    if sp["blocks_activation"]:
        blocking.append(
            _check(
                id="step.service_profile",
                message="Serviceprofil är ofullständig eller ogiltig.",
                source_class="tenant_specific",
                step_key="service_profile",
            )
        )
    elif sp["step_status"] == "completed":
        passed.append(
            _check(
                id="step.service_profile",
                message="Serviceprofil validerad.",
                source_class="tenant_specific",
                step_key="service_profile",
            )
        )
    elif sp["step_status"] == "not_applicable":
        not_applicable.append(
            _check(
                id="step.service_profile",
                message="Serviceprofil ej tillämplig.",
                source_class="not_applicable",
                step_key="service_profile",
            )
        )

    rt = evaluate_routing_step(
        modules_draft=modules_payload,
        service_profile_draft=sp_payload,
        routing_draft=routing_payload,
    )
    if rt["blocks_activation"]:
        blocking.append(
            _check(
                id="step.routing",
                message="Intern routing är ofullständig eller ogiltig.",
                source_class="tenant_specific",
                step_key="routing",
            )
        )
    elif rt["step_status"] == "completed":
        passed.append(
            _check(
                id="step.routing",
                message="Intern routing validerad.",
                source_class="tenant_specific",
                step_key="routing",
            )
        )
    elif rt["step_status"] == "not_applicable":
        not_applicable.append(
            _check(
                id="step.routing",
                message="Intern routing ej tillämplig.",
                source_class="not_applicable",
                step_key="routing",
            )
        )
    elif rt["step_status"] == "not_started":
        blocking.append(
            _check(
                id="step.routing.not_started",
                message="Routingsteget har inte slutförts.",
                source_class="declared",
                step_key="routing",
            )
        )

    integ = evaluate_integrations_step(
        db,
        modules_draft=modules_payload,
        tenant=tenant,
        settings=settings,
        session_id=session_id,
    )
    if (integ.get("details") or {}).get("draft_invalid") and "gmail" in (
        modules_payload.get("integrations") or []
    ):
        blocking.append(
            _check(
                id="integration.gmail.draft_invalid",
                message="Gmail integrationsdraft kunde inte läsas.",
                source_class="declared",
                step_key="integrations",
            )
        )
    if integ["blocks_activation"]:
        blocking.append(
            _check(
                id="step.integrations",
                message="Obligatorisk integration är inte verifierad eller konfigurerad.",
                source_class="tenant_specific",
                step_key="integrations",
            )
        )
    elif integ["step_status"] == "completed":
        passed.append(
            _check(
                id="step.integrations",
                message="Integrationer validerade.",
                source_class="tenant_specific",
                step_key="integrations",
            )
        )
        for item in (integ.get("details") or {}).get("integrations") or []:
            key = item.get("integration_key")
            if key == "gmail" and item.get("required"):
                if _append_gmail_readiness_checks(
                    item=item,
                    db=db,
                    session_id=session_id,
                    tenant=tenant,
                    settings=settings,
                    passed=passed,
                    warnings=warnings,
                    not_verifiable=not_verifiable,
                    blocking=blocking,
                ):
                    forces_ready_with_warnings = True
            if key == "visma" and item.get("required"):
                if item.get("verified"):
                    passed.append(
                        _check(
                            id="integration.visma.verified",
                            message="Visma verifierad.",
                            source_class="externally_verified",
                            step_key="integrations",
                        )
                    )
                elif item.get("connected") or item.get("lifecycle_status") == "connected":
                    blocking.append(
                        _check(
                            id="integration.visma.connected_not_verified",
                            message="Visma är ansluten men inte verifierad.",
                            source_class="tenant_specific",
                            step_key="integrations",
                        )
                    )
    elif integ["step_status"] == "not_applicable":
        not_applicable.append(
            _check(
                id="step.integrations",
                message="Integrationer ej tillämpliga.",
                source_class="not_applicable",
                step_key="integrations",
            )
        )

    data = evaluate_data_start_step(modules_draft=modules_payload, data_start_draft=data_start_payload)
    details = data.get("details") or {}
    if details.get("mode_valid"):
        passed.append(
            _check(
                id="data_start.mode_valid",
                message="Datastartläge är giltigt.",
                source_class="tenant_specific",
                step_key="data_start",
            )
        )
    else:
        blocking.append(
            _check(
                id="data_start.mode_valid",
                message="Datastartläge saknas eller är ogiltigt.",
                source_class="tenant_specific",
                step_key="data_start",
            )
        )
    if details.get("cutoff_strategy_status") == "passed":
        passed.append(
            _check(
                id="data_start.cutoff_strategy",
                message="Cutoff-strategi definierad (server-side vid aktivering).",
                source_class="tenant_specific",
                step_key="data_start",
            )
        )
    if details.get("runtime_enforcement") == "not_verifiable":
        not_verifiable.append(
            _check(
                id="data_start.runtime_enforcement",
                message="Runtime enforcement av intake-cutoff är inte verifierbar (metadata only).",
                source_class="not_verifiable",
                step_key="data_start",
            )
        )
        warnings.append(
            _check(
                id="warning.data_start.runtime_enforcement",
                message="Gamla mejl blockeras inte tekniskt av plattformen ännu.",
                source_class="not_verifiable",
                step_key="data_start",
            )
        )
        forces_ready_with_warnings = True

    if data["blocks_activation"]:
        blocking.append(
            _check(
                id="step.data_start",
                message="Datastart blockerar aktivering.",
                source_class="tenant_specific",
                step_key="data_start",
            )
        )
    elif data["step_status"] == "completed":
        passed.append(
            _check(
                id="step.data_start",
                message="Datastart konfigurerad.",
                source_class="tenant_specific",
                step_key="data_start",
            )
        )

    if not settings.GOOGLE_MAIL_ACCESS_TOKEN and "gmail" in (modules_payload.get("integrations") or []):
        warnings.append(
            _check(
                id="warning.platform.gmail_token",
                message="Plattformens Gmail-token saknas (platform-level).",
                source_class="platform_level",
                step_key="integrations",
            )
        )

    if blocking:
        overall = "not_ready"
    elif warnings or forces_ready_with_warnings:
        overall = "ready_with_warnings"
    else:
        overall = "ready"

    return {
        "overall_status": overall,
        "check_version": check_version,
        "blocking_checks": blocking,
        "warnings": warnings,
        "passed_checks": passed,
        "not_applicable": not_applicable,
        "not_verifiable": not_verifiable,
        "last_checked_at": _utcnow(),
    }
