"""Server-generated activation plan with stable plan_hash binding."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.orm import Session

from app.admin.onboarding.effective_config import plan_fingerprint_from_drafts, plan_fingerprint_slice2b
from app.admin.onboarding.integration_verification import IntegrationVerificationStore
from app.admin.onboarding.readiness import compute_readiness
from app.admin.onboarding.slice2a_registry import lead_field_registry, profiles_for_onboarding
from app.admin.onboarding.registries import REGISTRY_REVISION, REGISTRY_SCHEMA_VERSION
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.runtime_evaluation import evaluate_all_runtime_requirements
from app.core.settings import Settings
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

_STATIC_CONSEQUENCES: tuple[dict[str, str], ...] = (
    {
        "id": "activation.scheduler_paused",
        "message": "Scheduler konfigureras men förblir paused vid aktivering.",
        "severity": "info",
    },
    {
        "id": "activation.no_gmail_live_scan",
        "message": "Gmail live-skanning startas inte.",
        "severity": "info",
    },
    {
        "id": "activation.no_api_key",
        "message": "API-nyckel skapas inte automatiskt.",
        "severity": "info",
    },
    {
        "id": "activation.intake_metadata_only",
        "message": "Intake-cutoff sparas som metadata; runtime enforcement är inte verifierbar.",
        "severity": "info",
    },
    {
        "id": "activation.service_profile_materialized",
        "message": "Serviceprofiler och lead requirements materialiseras till tenant memory.",
        "severity": "info",
    },
    {
        "id": "activation.internal_routing_materialized",
        "message": "Intern routing skrivs till memory.internal_routing_hints.",
        "severity": "info",
    },
    {
        "id": "activation.no_external_calls",
        "message": "Inga externa integrationer anropas vid aktivering.",
        "severity": "info",
    },
)


def _snapshot_fingerprint(
    modules_payload: dict,
    automation_payload: dict,
) -> dict[str, Any]:
    return {
        "capabilities": sorted(modules_payload.get("capabilities") or []),
        "integrations": sorted(modules_payload.get("integrations") or []),
        "preset_key": automation_payload.get("preset_key"),
        "preset_version": automation_payload.get("preset_version"),
    }


def _canonical_plan_payload(
    *,
    consequences: list[dict[str, str]],
    runtime_effects: list[dict[str, Any]],
    capability_states: list[dict[str, Any]],
    warning_ids: list[str],
    snapshot_fingerprint: dict[str, Any],
    slice2a_fingerprint: dict[str, Any],
    slice2b_fingerprint: dict[str, Any],
    registry_revision: str,
) -> dict[str, Any]:
    return {
        "consequences": sorted(consequences, key=lambda c: c["id"]),
        "runtime_effects": sorted(
            [
                {
                    "feature_key": e.get("feature_key"),
                    "configured": e.get("configured"),
                    "running": e.get("running"),
                    "message": e.get("message"),
                }
                for e in runtime_effects
            ],
            key=lambda x: str(x.get("feature_key")),
        ),
        "capability_states": sorted(
            [
                {
                    "capability_key": s.get("capability_key"),
                    "lifecycle_state": s.get("lifecycle_state"),
                }
                for s in capability_states
            ],
            key=lambda x: str(x.get("capability_key")),
        ),
        "warning_ids": sorted(warning_ids),
        "snapshot_fingerprint": snapshot_fingerprint,
        "slice2a_fingerprint": slice2a_fingerprint,
        "slice2b_fingerprint": slice2b_fingerprint,
        "registry_revision": registry_revision,
    }


def compute_plan_hash(canonical: dict[str, Any]) -> str:
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_activation_plan(
    db: Session,
    *,
    session_id: str,
    tenant: TenantConfigRecord,
    settings: Settings,
) -> dict[str, Any]:
    session = OnboardingRepository.get_session(db, session_id)
    if session is None:
        raise ValueError("session not found")

    modules_draft = OnboardingRepository.get_draft(db, session_id, "modules")
    automation_draft = OnboardingRepository.get_draft(db, session_id, "automation")
    sp_draft = OnboardingRepository.get_draft(db, session_id, "service_profile")
    routing_draft = OnboardingRepository.get_draft(db, session_id, "routing")
    data_start_draft = OnboardingRepository.get_draft(db, session_id, "data_start")
    integrations_draft = OnboardingRepository.get_draft(db, session_id, "integrations")
    external_routing_draft = OnboardingRepository.get_draft(db, session_id, "external_routing")
    modules_payload = (modules_draft.payload if modules_draft else {}) or {}
    automation_payload = (automation_draft.payload if automation_draft else {}) or {}
    snapshot = automation_payload.get("effective_policy_snapshot") or {}

    runtime_bundle = evaluate_all_runtime_requirements(
        db,
        capability_keys=modules_payload.get("capabilities") or [],
        snapshot=snapshot,
        tenant=tenant,
        preset_key=automation_payload.get("preset_key"),
        preset_version=automation_payload.get("preset_version"),
    )

    readiness = compute_readiness(
        db,
        session_id=session_id,
        tenant=tenant,
        settings=settings,
        check_version=session.readiness_check_version,
    )

    warning_ids = [w["id"] for w in readiness.get("warnings") or []]
    consequences = [dict(c) for c in _STATIC_CONSEQUENCES]
    runtime_effects = runtime_bundle.get("runtime_checks") or []
    capability_states = runtime_bundle.get("capability_states") or []

    snap_fp = _snapshot_fingerprint(modules_payload, automation_payload)
    allowed_profiles = {p["key"] for p in profiles_for_onboarding() if p["availability"] == "available"}
    allowed_fields = {f["key"] for f in lead_field_registry()}
    slice2a_fp = plan_fingerprint_from_drafts(
        modules_payload,
        sp_draft.payload if sp_draft else None,
        routing_draft.payload if routing_draft else None,
        data_start_draft.payload if data_start_draft else None,
        allowed_profile_keys=allowed_profiles,
        allowed_field_keys=allowed_fields,
    )
    slice2b_fp = plan_fingerprint_slice2b(
        integrations_draft.payload if integrations_draft else None,
        external_routing_draft.payload if external_routing_draft else None,
        verification_fingerprints_hash=IntegrationVerificationStore.fingerprints_hash(db, session_id),
        integration_state_revision=int(session.integration_state_revision or 0),
    )
    canonical = _canonical_plan_payload(
        consequences=consequences,
        runtime_effects=runtime_effects,
        capability_states=capability_states,
        warning_ids=warning_ids,
        snapshot_fingerprint=snap_fp,
        slice2a_fingerprint=slice2a_fp,
        slice2b_fingerprint=slice2b_fp,
        registry_revision=REGISTRY_REVISION,
    )
    plan_hash = compute_plan_hash(canonical)
    plan_id = hashlib.sha256(
        f"{session_id}:{plan_hash}".encode("utf-8")
    ).hexdigest()

    return {
        "plan_id": plan_id,
        "plan_hash": plan_hash,
        "session_version": session.version,
        "readiness_check_version": session.readiness_check_version,
        "registry_revision": REGISTRY_REVISION,
        "registry_schema_version": REGISTRY_SCHEMA_VERSION,
        "warning_ids": warning_ids,
        "consequences": consequences,
        "capability_states": capability_states,
        "runtime_effects": [
            {
                "feature_key": e.get("feature_key"),
                "status": e.get("status"),
                "configured": e.get("configured"),
                "running": e.get("running"),
                "message": e.get("message"),
            }
            for e in runtime_effects
        ],
    }
