"""Runtime feature and capability lifecycle evaluation for onboarding."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

from app.admin.onboarding.registries import (
    PRODUCT_CAPABILITIES,
    RUNTIME_FEATURES,
    capability_requires_api_key,
    collect_required_runtime,
    resolve_preset,
)
from app.admin.onboarding.steps import tenant_has_api_key
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

CapabilityLifecycleState = Literal[
    "selected",
    "configured",
    "configured_not_running",
    "activated",
    "running",
    "not_applicable",
]

RuntimeCheckStatus = Literal[
    "passed",
    "warning",
    "blocked",
    "not_verifiable",
    "not_applicable",
]


def validate_runtime_dependencies(capability_keys: list[str]) -> list[str]:
    """Return unknown runtime dependency keys (empty if valid)."""
    unknown: list[str] = []
    for key in collect_required_runtime(capability_keys):
        if key not in RUNTIME_FEATURES:
            unknown.append(key)
    return unknown


def _scheduler_mode(snapshot: dict, tenant: TenantConfigRecord | None) -> str | None:
    if snapshot.get("scheduler_run_mode"):
        return str(snapshot["scheduler_run_mode"])
    if tenant and tenant.settings:
        sched = (tenant.settings or {}).get("scheduler") or {}
        return sched.get("run_mode")
    return None


def evaluate_runtime_feature(
    feature_key: str,
    *,
    snapshot: dict,
    tenant: TenantConfigRecord | None,
    db: Session,
    tenant_id: str,
) -> dict[str, Any]:
    if feature_key not in RUNTIME_FEATURES:
        return {
            "feature_key": feature_key,
            "status": "blocked",
            "configured": False,
            "running": False,
            "blocks_activation": True,
            "message": f"Okänd runtime-funktion: {feature_key}.",
        }

    if feature_key == "scheduler":
        mode = _scheduler_mode(snapshot, tenant)
        configured = mode is not None
        running = configured and mode != "paused"
        if not configured:
            return {
                "feature_key": feature_key,
                "status": "blocked",
                "configured": False,
                "running": False,
                "blocks_activation": True,
                "message": "Scheduler saknar konfiguration i automation preset.",
            }
        if running:
            return {
                "feature_key": feature_key,
                "status": "warning",
                "configured": True,
                "running": True,
                "blocks_activation": False,
                "message": "Scheduler är konfigurerad men inte pausad i onboarding-läge.",
            }
        return {
            "feature_key": feature_key,
            "status": "passed",
            "configured": True,
            "running": False,
            "blocks_activation": False,
            "message": "Scheduler konfigurerad (paused).",
        }

    if feature_key == "automation_master":
        flags = snapshot.get("automation_flags") or {}
        configured = bool(flags)
        running = any(flags.get(k) for k in flags)
        return {
            "feature_key": feature_key,
            "status": "passed" if configured else "blocked",
            "configured": configured,
            "running": running,
            "blocks_activation": not configured,
            "message": "Automation-flaggor från preset." if configured else "Automation preset saknas.",
        }

    if feature_key == "gmail_live_scan":
        return {
            "feature_key": feature_key,
            "status": "not_applicable",
            "configured": False,
            "running": False,
            "blocks_activation": False,
            "message": "Gmail live-skanning startas inte av onboarding.",
        }

    if feature_key == "api_access":
        has_key = tenant_has_api_key(db, tenant_id) if tenant_id else False
        return {
            "feature_key": feature_key,
            "status": "passed" if has_key else "blocked",
            "configured": has_key,
            "running": has_key,
            "blocks_activation": False,
            "message": "API-nyckel finns." if has_key else "API-nyckel saknas.",
        }

    return {
        "feature_key": feature_key,
        "status": "not_verifiable",
        "configured": False,
        "running": False,
        "blocks_activation": False,
        "message": f"Runtime '{feature_key}' kan inte verifieras lokalt.",
    }


def evaluate_capability_lifecycle(
    capability_key: str,
    *,
    selected: bool,
    snapshot: dict,
    tenant: TenantConfigRecord | None,
    db: Session,
    runtime_evaluations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    cap = PRODUCT_CAPABILITIES.get(capability_key)
    if not cap or not selected:
        return {
            "capability_key": capability_key,
            "lifecycle_state": "not_applicable",
            "selected": False,
            "configured": False,
            "activated": False,
            "running": False,
            "message": "Ej vald.",
        }

    tenant_active = tenant is not None and tenant.status == "active"
    runtime_ok = True
    any_not_running = False
    for rt in cap.required_runtime:
        ev = runtime_evaluations.get(rt)
        if not ev or ev.get("status") == "blocked":
            runtime_ok = False
        if ev and ev.get("configured") and not ev.get("running"):
            any_not_running = True

    if not snapshot:
        return {
            "capability_key": capability_key,
            "lifecycle_state": "selected",
            "selected": True,
            "configured": False,
            "activated": tenant_active,
            "running": False,
            "message": "Automation preset saknas.",
        }

    if not runtime_ok:
        return {
            "capability_key": capability_key,
            "lifecycle_state": "selected",
            "selected": True,
            "configured": False,
            "activated": tenant_active,
            "running": False,
            "message": "Runtime-beroenden ej uppfyllda.",
        }

    if any_not_running and "scheduler" in cap.required_runtime:
        lifecycle: CapabilityLifecycleState = "configured_not_running"
        return {
            "capability_key": capability_key,
            "lifecycle_state": lifecycle,
            "selected": True,
            "configured": True,
            "activated": tenant_active,
            "running": False,
            "message": "Konfigurerad men scheduler körs inte (paused).",
        }

    if tenant_active:
        lifecycle = "activated"
    else:
        lifecycle = "configured"

    return {
        "capability_key": capability_key,
        "lifecycle_state": lifecycle,
        "selected": True,
        "configured": True,
        "activated": tenant_active,
        "running": False,
        "message": "Kapabilitet konfigurerad.",
    }


def evaluate_all_runtime_requirements(
    db: Session,
    *,
    capability_keys: list[str],
    snapshot: dict,
    tenant: TenantConfigRecord | None,
    preset_key: str | None,
    preset_version: int | None,
) -> dict[str, Any]:
    unknown = validate_runtime_dependencies(capability_keys)
    if unknown:
        return {
            "runtime_checks": [
                {
                    "feature_key": u,
                    "status": "blocked",
                    "configured": False,
                    "running": False,
                    "blocks_activation": True,
                    "message": f"Okänt runtime-beroende: {u}.",
                }
                for u in unknown
            ],
            "capability_states": [],
            "readiness_warnings": [],
            "readiness_blocking": [
                {
                    "id": "runtime.unknown_dependency",
                    "message": f"Okända runtime-beroenden: {', '.join(unknown)}.",
                    "source_class": "declared",
                    "step_key": "modules",
                }
            ],
            "forces_ready_with_warnings": False,
        }

    if preset_key and preset_version:
        preset = resolve_preset(preset_key, preset_version)
        if preset is None:
            return {
                "runtime_checks": [],
                "capability_states": [],
                "readiness_warnings": [],
                "readiness_blocking": [
                    {
                        "id": "automation.preset_version",
                        "message": "Okänd eller inaktuell automation preset-version.",
                        "source_class": "tenant_specific",
                        "step_key": "automation",
                    }
                ],
                "forces_ready_with_warnings": False,
            }

    required = collect_required_runtime(capability_keys)
    tenant_id = tenant.tenant_id if tenant else ""
    runtime_checks: dict[str, dict[str, Any]] = {}
    for feature_key in sorted(required):
        runtime_checks[feature_key] = evaluate_runtime_feature(
            feature_key,
            snapshot=snapshot,
            tenant=tenant,
            db=db,
            tenant_id=tenant_id,
        )

    capability_states = [
        evaluate_capability_lifecycle(
            key,
            selected=key in capability_keys,
            snapshot=snapshot,
            tenant=tenant,
            db=db,
            runtime_evaluations=runtime_checks,
        )
        for key in capability_keys
        if key in PRODUCT_CAPABILITIES
    ]

    readiness_blocking: list[dict[str, Any]] = []
    readiness_warnings: list[dict[str, Any]] = []
    forces_ready_with_warnings = False

    for check in runtime_checks.values():
        if check.get("blocks_activation") and check.get("status") == "blocked":
            readiness_blocking.append(
                {
                    "id": f"runtime.{check['feature_key']}.blocked",
                    "message": check["message"],
                    "source_class": "tenant_specific",
                    "step_key": "automation",
                }
            )
        elif check.get("status") == "warning":
            readiness_warnings.append(
                {
                    "id": f"runtime.{check['feature_key']}.warning",
                    "message": check["message"],
                    "source_class": "declared",
                    "step_key": "automation",
                }
            )

    for state in capability_states:
        if state.get("lifecycle_state") == "configured_not_running":
            readiness_warnings.append(
                {
                    "id": f"capability.{state['capability_key']}.configured_not_running",
                    "message": state["message"],
                    "source_class": "declared",
                    "step_key": "modules",
                }
            )
            forces_ready_with_warnings = True

    if capability_requires_api_key(capability_keys):
        api_ev = evaluate_runtime_feature(
            "api_access",
            snapshot=snapshot,
            tenant=tenant,
            db=db,
            tenant_id=tenant_id,
        )
        runtime_checks["api_access"] = api_ev
        if not api_ev.get("configured"):
            readiness_blocking.append(
                {
                    "id": "runtime.api_key",
                    "message": "API-nyckel krävs men har inte skapats.",
                    "source_class": "tenant_specific",
                    "step_key": "modules",
                }
            )

    return {
        "runtime_checks": list(runtime_checks.values()),
        "capability_states": capability_states,
        "readiness_warnings": readiness_warnings,
        "readiness_blocking": readiness_blocking,
        "forces_ready_with_warnings": forces_ready_with_warnings,
    }
