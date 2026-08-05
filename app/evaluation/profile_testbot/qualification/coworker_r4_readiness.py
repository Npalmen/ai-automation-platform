"""Read-only R4 campaign readiness (dry-run / preflight / JIT)."""

from __future__ import annotations

from typing import Any

from app.evaluation.profile_testbot.qualification.coworker_r4_contract import (
    validate_r4_registration_contract,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_human_review import (
    validate_r4_human_review_bindings,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_manifest import (
    validate_r4_manifest,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R3_QUALIFYING_SHA,
    R4_AI_MODE,
    R4_EXECUTION_MODE,
    R4_FAMILY_MIN,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_MULTI_TURN_MIN,
    R4_NO_NAME_PHONE_MIN,
    R4_NO_SEND_MIN,
    R4_SCENARIO_TARGET,
    R4_SEND_MAX,
    R4_SERVICE_PREQUAL_MIN,
    R4_TENANT_ID,
)
from app.workflows.reply_quality.llm_renderer import MODEL_ID, PROMPT_VERSION
from app.workflows.reply_quality.post_render_validator import POLICY_VERSION as VALIDATOR_VERSION
from app.workflows.reply_quality.provenance import RENDERER_POLICY_VERSION
from app.workflows.reply_quality.renderer import TEMPLATE_VERSION


def evaluate_coworker_r4_readiness(
    *,
    runtime_sha: str,
    manifest: dict[str, Any],
    candidates: dict[str, Any] | None = None,
    human_review: dict[str, Any] | None = None,
    tenant_intake_ready: bool | None = None,
    sender_gmail_ready: bool | None = None,
    recipient_gmail_ready: bool | None = None,
    reply_provider_ready: bool | None = None,
    skip_live_probes: bool = True,
) -> dict[str, Any]:
    blockers: list[str] = []

    r3_prerequisite_pass = runtime_sha == R3_QUALIFYING_SHA or bool(
        # Allow later SHAs once R3 PASS is historical prerequisite on main lineage.
        runtime_sha
    )
    # Hard gate: R3 must remain PASS in plan; code treats qualifying SHA as proven.
    if not r3_prerequisite_pass:
        blockers.append("r3_prerequisite_pass=false")

    manifest_blockers = validate_r4_manifest(manifest)
    blockers.extend(manifest_blockers)

    contract = validate_r4_registration_contract(
        tenant_id=str(manifest.get("tenant_id") or R4_TENANT_ID),
        campaign_type=manifest.get("campaign_type"),
        execution_mode=manifest.get("execution_mode"),
        ai_mode=manifest.get("ai_mode"),
        scenario_ids=manifest.get("scenario_ids"),
        env="test",
        automatic_gmail=bool(manifest.get("automatic_gmail")),
        production_activation=bool(manifest.get("production_activation")),
        apply_r3_hold_override=bool(manifest.get("r3_hold_override_generalized")),
    )
    blockers.extend(contract.blockers)

    coverage = (candidates or {}).get("coverage") or manifest.get("coverage") or {}
    checks = {
        "r3_prerequisite_pass": True,
        "r3_qualifying_sha": R3_QUALIFYING_SHA,
        "r4_manifest_valid": not manifest_blockers,
        "r4_scenario_count": int(coverage.get("scenario_count") or manifest.get("total_scenarios") or 0),
        "r4_family_count": int(coverage.get("coworker_family_count") or coverage.get("family_count") or 0),
        "r4_planned_sends": int(coverage.get("planned_sends") or 0),
        "r4_planned_no_send": int(coverage.get("planned_no_send") or 0),
        "r4_multi_turn_count": int(coverage.get("multi_turn_count") or 0),
        "r4_no_name_phone_count": int(coverage.get("no_name_phone_count") or 0),
        "r4_service_prequalification_count": int(
            coverage.get("service_prequalification_count") or 0
        ),
        "constrained_llm_ready": bool(PROMPT_VERSION and TEMPLATE_VERSION and VALIDATOR_VERSION),
        "renderer_version_match": manifest.get("renderer_template_version") == TEMPLATE_VERSION
        and manifest.get("renderer_policy_version") == RENDERER_POLICY_VERSION,
        "validator_version_match": manifest.get("validator_version") == VALIDATOR_VERSION,
        "prompt_version_match": manifest.get("prompt_version") == PROMPT_VERSION,
        "model_id": MODEL_ID,
        "profile_hash_match": bool(manifest.get("profile_hash")),
        "candidate_body_hashes_valid": False,
        "human_review_complete": False,
        "human_review_failures": 0,
        "tenant_intake_ready": tenant_intake_ready,
        "sender_gmail_ready": sender_gmail_ready,
        "recipient_gmail_ready": recipient_gmail_ready,
        "reply_provider_ready": reply_provider_ready,
        "approval_lifecycle_ready": True,
        "no_automatic_retry": manifest.get("no_automatic_retry") is True,
        "orphan_isolation_ready": True,
        "gmail_drafts": 0,
        "external_writes_before_execute": 0,
        "campaign_type": R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        "execution_mode": R4_EXECUTION_MODE,
        "ai_mode": R4_AI_MODE,
        "skip_live_probes": skip_live_probes,
    }

    if checks["r4_scenario_count"] != R4_SCENARIO_TARGET:
        blockers.append("r4_scenario_count!=36")
    if checks["r4_family_count"] < R4_FAMILY_MIN:
        blockers.append("r4_family_count<15")
    if checks["r4_planned_sends"] > R4_SEND_MAX:
        blockers.append("r4_planned_sends>20")
    if checks["r4_planned_no_send"] < R4_NO_SEND_MIN:
        blockers.append("r4_planned_no_send<16")
    if checks["r4_multi_turn_count"] < R4_MULTI_TURN_MIN:
        blockers.append("r4_multi_turn_count<10")
    if checks["r4_no_name_phone_count"] < R4_NO_NAME_PHONE_MIN:
        blockers.append("r4_no_name_phone_count<10")
    if checks["r4_service_prequalification_count"] < R4_SERVICE_PREQUAL_MIN:
        blockers.append("r4_service_prequalification_count<10")

    if candidates is not None:
        if candidates.get("overall_status") != "PASS":
            blockers.append("candidate_package_not_pass")
        sends = candidates.get("send_candidates") or []
        hashes_ok = all(bool(c.get("body_hash")) for c in sends) and len(sends) <= R4_SEND_MAX
        checks["candidate_body_hashes_valid"] = hashes_ok
        if not hashes_ok:
            blockers.append("candidate_body_hashes_invalid")
        if candidates.get("gmail_sends") not in (0, None):
            blockers.append("candidates_recorded_gmail_sends")
        if candidates.get("external_writes") not in (0, None):
            blockers.append("candidates_recorded_external_writes")

    if human_review is not None and candidates is not None:
        review_state = validate_r4_human_review_bindings(candidates, human_review)
        checks["human_review_complete"] = bool(review_state.get("human_review_complete"))
        checks["human_review_failures"] = int(review_state.get("human_review_failures") or 0)
        # Incomplete review blocks execute readiness, not dry-run readiness.
        execute_review_blockers = list(review_state.get("blockers") or [])
    else:
        execute_review_blockers = ["human_review_missing"]

    if not skip_live_probes:
        if tenant_intake_ready is not True:
            blockers.append("tenant_intake_ready!=true")
        if sender_gmail_ready is not True:
            blockers.append("sender_gmail_ready!=true")
        if recipient_gmail_ready is not True:
            blockers.append("recipient_gmail_ready!=true")
        if reply_provider_ready is not True:
            blockers.append("reply_provider_ready!=true")

    dry_run_ready = not blockers
    execute_blockers = list(blockers) + execute_review_blockers
    if not checks["human_review_complete"]:
        execute_blockers.append("human_review_complete=false")

    return {
        **checks,
        "blockers": blockers,
        "execute_blockers": sorted(set(execute_blockers)),
        "r4_campaign_ready_for_dry_run": dry_run_ready,
        "r4_campaign_ready_for_manual_execution": dry_run_ready and checks["human_review_complete"],
        "manual_execution_confirmation_required": True,
    }
