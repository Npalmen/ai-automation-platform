"""Slice 2A local E2E verification (API). Outputs JSON report without secrets."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from datetime import datetime, timezone

import requests

from app.admin.onboarding.effective_config import materialize_slice2a_config
from app.core.settings import get_settings


def _headers(key: str, origin: str = "http://localhost:5173") -> dict[str, str]:
    return {
        "X-Admin-API-Key": key,
        "Content-Type": "application/json",
        "Origin": origin,
    }


def main() -> int:
    settings = get_settings()
    key = settings.ADMIN_API_KEY
    if not key:
        print(json.dumps({"error": "ADMIN_API_KEY not configured"}))
        return 1

    base = "http://127.0.0.1:8000"
    slug = f"slice2a-verify-{datetime.now(timezone.utc).strftime('%H%M%S')}"
    report: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "slug": slug,
        "steps": {},
        "external_actions_observed": False,
    }

    def step(name: str, ok: bool, detail: dict | None = None):
        report["steps"][name] = {"status": "PASS" if ok else "FAIL", **(detail or {})}

    # Create session
    r = requests.post(
        f"{base}/admin/onboarding",
        headers=_headers(key),
        json={
            "company_name": "Slice 2A Verify AB",
            "slug": slug,
            "timezone": "Europe/Stockholm",
            "language": "sv",
        },
    )
    if r.status_code != 201:
        step("create_session", False, {"http": r.status_code, "body": r.text[:500]})
        print(json.dumps(report, indent=2, default=str))
        return 1
    session = r.json()
    session_id = session["id"]
    tenant_id = session["tenant_id"]
    version = session["version"]
    report["session_id"] = session_id
    report["tenant_id"] = tenant_id
    step("create_session", True)

    def patch(path: str, body: dict) -> dict:
        nonlocal version
        body = {**body, "version": version}
        resp = requests.patch(f"{base}/admin/onboarding/{session_id}/{path}", headers=_headers(key), json=body)
        if resp.status_code != 200:
            raise RuntimeError(f"PATCH {path} failed {resp.status_code}: {resp.text[:400]}")
        data = resp.json()
        version = data["version"]
        return data

    try:
        patch("identity", {"company_name": "Slice 2A Verify AB", "slug": slug})
        patch("modules", {"capabilities": ["followups"], "integrations": []})
        patch("automation", {"preset_key": "observe_only", "preset_version": 1})
        patch(
            "service-profile",
            {
                "selected_profiles": ["generic_lead"],
                "lead_requirements": {
                    "generic_lead": {
                        "contact_name": "inherit",
                        "phone_or_email": "required",
                    }
                },
            },
        )
        step("steps_1_4", True)

        # Routing preview before patch — should not mutate step state count
        states_before = requests.get(
            f"{base}/admin/onboarding/{session_id}/routing",
            headers=_headers(key),
        ).json()
        preview = requests.post(
            f"{base}/admin/onboarding/{session_id}/routing-preview",
            headers=_headers(key),
            json={},
        ).json()
        states_after_preview = requests.get(
            f"{base}/admin/onboarding/{session_id}/routing",
            headers=_headers(key),
        ).json()
        step(
            "routing_preview_no_mutation",
            preview.get("mutated") is False
            and states_before.get("draft") == states_after_preview.get("draft"),
            {"preview_rows": len(preview.get("preview") or [])},
        )

        patch("routing", {"route_overrides": {"generic_lead": "sales"}})
        step("routing_patch", True)

        # Reset to inherit
        reset = requests.post(
            f"{base}/admin/onboarding/{session_id}/routing-reset",
            headers=_headers(key),
            json={"version": version, "service_types": ["generic_lead"]},
        )
        if reset.status_code != 200:
            step("routing_reset", False, {"http": reset.status_code})
        else:
            reset_body = reset.json()
            overrides = (reset_body.get("draft") or {}).get("route_overrides") or {}
            step("routing_reset", "generic_lead" not in overrides)

        version = requests.get(f"{base}/admin/onboarding/{session_id}", headers=_headers(key)).json()["version"]
        patch("routing", {"route_overrides": {"generic_lead": "support"}})

        patch("data-start", {"mode": "new_incoming_only"})
        step("data_start", True)

        plan1 = requests.get(
            f"{base}/admin/onboarding/{session_id}/activation-plan",
            headers=_headers(key),
        ).json()
        patch("routing", {"route_overrides": {"generic_lead": "manual_review"}})
        plan2 = requests.get(
            f"{base}/admin/onboarding/{session_id}/activation-plan",
            headers=_headers(key),
        ).json()
        step(
            "activation_plan_updates_on_2a_change",
            plan1.get("plan_hash") != plan2.get("plan_hash"),
            {"plan1": plan1.get("plan_hash", "")[:16], "plan2": plan2.get("plan_hash", "")[:16]},
        )

        readiness = requests.post(
            f"{base}/admin/onboarding/{session_id}/readiness",
            headers=_headers(key),
            json={},
        ).json()
        step(
            "readiness",
            readiness.get("overall_status") == "ready_with_warnings",
            {"overall": readiness.get("overall_status"), "warnings": [w["id"] for w in readiness.get("warnings", [])]},
        )

        session = requests.get(f"{base}/admin/onboarding/{session_id}", headers=_headers(key)).json()
        activate = requests.post(
            f"{base}/admin/onboarding/{session_id}/activate",
            headers=_headers(key),
            json={
                "version": session["version"],
                "readiness_check_version": session["readiness_check_version"],
                "plan_hash": plan2["plan_hash"],
                "reason": "Slice 2A E2E verification",
                "confirmation_phrase": slug,
                "acknowledged_warning_ids": [w["id"] for w in readiness.get("warnings", [])],
            },
        )
        if activate.status_code != 200:
            step("activate", False, {"http": activate.status_code, "body": activate.text[:500]})
            print(json.dumps(report, indent=2, default=str))
            return 1
        step("activate", True)

        # Tenant settings after activate
        detail = requests.get(f"{base}/admin/tenants/{tenant_id}/overview", headers=_headers(key)).json()
        onboarding_cfg = detail.get("onboarding_config") or {}
        settings_after = {}
        try:
            from app.repositories.postgres.database import SessionLocal
            from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

            db = SessionLocal()
            try:
                rec = TenantConfigRepository.get(db, tenant_id)
                settings_after = deepcopy(rec.settings or {}) if rec else {}
            finally:
                db.close()
        except Exception as exc:
            report["settings_read_error"] = str(exc)

        memory = settings_after.get("memory") or {}
        intake = settings_after.get("intake") or {}
        scheduler = settings_after.get("scheduler") or {}
        cutoff1 = intake.get("activation_cutoff_at")

        report["canonical_after"] = {
            "schema_version": settings_after.get("schema_version"),
            "service_profiles": onboarding_cfg.get("service_profiles") or memory.get("lead_config", {}).get("services"),
            "internal_routing_hints": memory.get("internal_routing_hints"),
            "intake": {
                "mode": intake.get("mode"),
                "activation_cutoff_at": cutoff1,
                "enforcement": intake.get("enforcement"),
            },
            "scheduler_run_mode": scheduler.get("run_mode"),
        }
        report["canonical_before"] = {"note": "inactive tenant defaults — no lead_config/intake pre-activate"}

        step(
            "canonical_settings",
            settings_after.get("schema_version") == 2
            and intake.get("mode") == "new_incoming_only"
            and intake.get("enforcement") == "metadata_only"
            and bool(cutoff1)
            and memory.get("internal_routing_hints", {}).get("generic_lead") == "manual_review"
            and scheduler.get("run_mode") == "paused",
        )

        # Idempotent materialize — cutoff must not change
        if settings_after:
            merged = materialize_slice2a_config(
                deepcopy(settings_after),
                modules_payload={"capabilities": ["followups"]},
                sp_payload={"selected_profiles": ["generic_lead"], "lead_requirements": {}},
                routing_payload={"route_overrides": {"generic_lead": "sales"}},
                data_start_payload={"mode": "new_incoming_only"},
                activation_cutoff_at=datetime.now(timezone.utc),
            )
            cutoff2 = (merged.get("intake") or {}).get("activation_cutoff_at")
            step("cutoff_idempotent", cutoff1 == cutoff2, {"unchanged": cutoff1 == cutoff2})

        # Registries deferred modes
        reg = requests.get(f"{base}/admin/onboarding/registries", headers=_headers(key)).json()
        deferred = [m for m in reg.get("data_start_modes", []) if not m.get("supported_in_current_slice")]
        step("deferred_data_start_modes_present", len(deferred) >= 2, {"deferred_keys": [m["key"] for m in deferred]})

        audits = requests.get(
            f"{base}/admin/tenants/{tenant_id}/overview",
            headers=_headers(key),
        ).json().get("audit", {}).get("recent", [])
        audit_actions = [a.get("action") for a in audits]
        step(
            "audit_events",
            "onboarding.activation_succeeded" in audit_actions
            and "onboarding.intake_cutoff_created" in audit_actions,
            {"actions": audit_actions[:15]},
        )

    except Exception as exc:
        report["error"] = str(exc)
        print(json.dumps(report, indent=2, default=str))
        return 1

    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["overall"] = (
        "PASS"
        if all(s.get("status") == "PASS" for s in report["steps"].values())
        else "PARTIAL"
    )
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["overall"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
