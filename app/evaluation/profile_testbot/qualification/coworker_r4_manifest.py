"""R4 campaign manifest builder and semantic hash."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.constants import (
    NO_SEND_BEHAVIORS,
    SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_AI_MODE,
    R4_EXECUTION_MODE,
    R4_FAMILY_MIN,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_MULTI_TURN_MIN,
    R4_NO_NAME_PHONE_MIN,
    R4_NO_SEND_MIN,
    R4_NO_SEND_SCENARIO_IDS,
    R4_PROFILE_ID,
    R4_SCENARIO_IDS,
    R4_SCENARIO_TARGET,
    R4_SEND_MAX,
    R4_SEND_SCENARIO_IDS,
    R4_SERVICE_PREQUAL_MIN,
    R4_TENANT_ID,
    coverage_summary,
    resolve_r4_scenarios,
    scenario_tags,
    validate_r4_scenario_coverage,
)
from app.workflows.reply_quality.llm_renderer import MODEL_ID, PROMPT_VERSION
from app.workflows.reply_quality.post_render_validator import POLICY_VERSION as VALIDATOR_VERSION
from app.workflows.reply_quality.provenance import RENDERER_POLICY_VERSION
from app.workflows.reply_quality.renderer import TEMPLATE_VERSION

R4_PLAYBOOK_CONTRACT_VERSION = "service_playbook_contract_v1"
R4_PLAN_POLICY_VERSION = "customer_reply_plan_v3"
R4_APPROVED_RECIPIENT_DOMAIN = "sol-f.se"
R4_APPROVED_RECIPIENT_LOCAL_PREFIX = "ni"


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_r4_semantic_manifest_hash(semantic_payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(semantic_payload).encode("utf-8")).hexdigest()


def build_r4_semantic_payload(
    *,
    profile_id: str,
    profile_hash: str,
    scenario_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Behavior-affecting fields only (no run/campaign IDs, timestamps, paths, telemetry)."""
    return {
        "campaign_type": R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        "execution_mode": R4_EXECUTION_MODE,
        "ai_mode": R4_AI_MODE,
        "tenant_id": R4_TENANT_ID,
        "profile_id": profile_id,
        "profile_hash": profile_hash,
        "scenario_ids": list(R4_SCENARIO_IDS),
        "send_scenario_ids": list(R4_SEND_SCENARIO_IDS),
        "no_send_scenario_ids": list(R4_NO_SEND_SCENARIO_IDS),
        "scenario_rows": scenario_rows,
        "budgets": {
            "total_scenarios": R4_SCENARIO_TARGET,
            "maximum_gmail_sends": R4_SEND_MAX,
            "minimum_no_send": R4_NO_SEND_MIN,
            "minimum_families": R4_FAMILY_MIN,
            "minimum_multi_turn": R4_MULTI_TURN_MIN,
            "minimum_no_name_phone": R4_NO_NAME_PHONE_MIN,
            "minimum_service_prequalification": R4_SERVICE_PREQUAL_MIN,
        },
        "versions": {
            "prompt_version": PROMPT_VERSION,
            "model_id": MODEL_ID,
            "renderer_template_version": TEMPLATE_VERSION,
            "renderer_policy_version": RENDERER_POLICY_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "plan_policy_version": R4_PLAN_POLICY_VERSION,
            "playbook_contract_version": R4_PLAYBOOK_CONTRACT_VERSION,
        },
        "policy_flags": {
            "automatic_gmail": False,
            "production_activation": False,
            "no_automatic_retry": True,
            "no_drafts": True,
            "r3_hold_override_generalized": False,
            "external_write_allowlist": ["gmail_reply"],
            "recipient_domain": R4_APPROVED_RECIPIENT_DOMAIN,
            "recipient_local_prefix": R4_APPROVED_RECIPIENT_LOCAL_PREFIX,
        },
    }


def build_r4_campaign_manifest(
    *,
    runtime_sha: str,
    profile_id: str = R4_PROFILE_ID,
    seed: int = 42,
) -> dict[str, Any]:
    profile = load_customer_profile(profile_id)
    scenarios = resolve_r4_scenarios(profile, seed=seed)
    coverage_issues = validate_r4_scenario_coverage(scenarios)
    if coverage_issues:
        raise ValueError("R4 coverage invalid: " + "; ".join(coverage_issues))

    scenario_rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        planned_send = scenario.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
        planned_no_send = scenario.expected_send_behavior in NO_SEND_BEHAVIORS
        scenario_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "family": scenario.family,
                "language": scenario.input.language if scenario.input else "sv",
                "expected_send_behavior": scenario.expected_send_behavior,
                "planned_gmail_send": planned_send,
                "planned_no_send": planned_no_send,
                "tags": scenario_tags(scenario),
            }
        )

    semantic = build_r4_semantic_payload(
        profile_id=profile_id,
        profile_hash=profile.profile_snapshot_hash,
        scenario_rows=scenario_rows,
    )
    manifest_hash = compute_r4_semantic_manifest_hash(semantic)
    summary = coverage_summary(scenarios)

    return {
        "campaign_type": R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        "execution_mode": R4_EXECUTION_MODE,
        "ai_mode": R4_AI_MODE,
        "tenant_id": R4_TENANT_ID,
        "profile_id": profile_id,
        "profile_hash": profile.profile_snapshot_hash,
        "runtime_sha": runtime_sha,
        "runner_sha": runtime_sha,
        "scenario_ids": list(R4_SCENARIO_IDS),
        "send_scenario_ids": list(R4_SEND_SCENARIO_IDS),
        "no_send_scenario_ids": list(R4_NO_SEND_SCENARIO_IDS),
        "scenario_rows": scenario_rows,
        "total_scenarios": R4_SCENARIO_TARGET,
        "maximum_gmail_sends": R4_SEND_MAX,
        "minimum_no_send": R4_NO_SEND_MIN,
        "required_coverage": {
            "families_min": R4_FAMILY_MIN,
            "multi_turn_min": R4_MULTI_TURN_MIN,
            "no_name_phone_min": R4_NO_NAME_PHONE_MIN,
            "service_prequalification_min": R4_SERVICE_PREQUAL_MIN,
        },
        "coverage": summary,
        "prompt_version": PROMPT_VERSION,
        "model_id": MODEL_ID,
        "renderer_template_version": TEMPLATE_VERSION,
        "renderer_policy_version": RENDERER_POLICY_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "plan_policy_version": R4_PLAN_POLICY_VERSION,
        "playbook_contract_version": R4_PLAYBOOK_CONTRACT_VERSION,
        "automatic_gmail": False,
        "production_activation": False,
        "no_automatic_retry": True,
        "no_drafts": True,
        "external_write_allowlist": ["gmail_reply"],
        "recipient_allowlist": {
            "domain": R4_APPROVED_RECIPIENT_DOMAIN,
            "local_prefix": R4_APPROVED_RECIPIENT_LOCAL_PREFIX,
        },
        "r3_hold_override_generalized": False,
        "manifest_semantic_hash": manifest_hash,
        "semantic_payload": semantic,
    }


def validate_r4_manifest(manifest: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if manifest.get("campaign_type") != R4_LIVE_QUALITY_CAMPAIGN_TYPE:
        blockers.append("campaign_type mismatch")
    if manifest.get("execution_mode") != R4_EXECUTION_MODE:
        blockers.append("execution_mode mismatch")
    if manifest.get("ai_mode") != R4_AI_MODE:
        blockers.append("ai_mode mismatch")
    if manifest.get("campaign_type") in {
        "coworker_r3_frozen_live_canary",
        "coworker-reply-live-canary",
    }:
        blockers.append("R3 campaign_type is not allowed for R4")
    if manifest.get("execution_mode") == "r3_frozen_approved_body":
        blockers.append("R3 frozen execution_mode is not allowed for R4")
    if manifest.get("ai_mode") in {"fixture_ai", "r3_frozen_approved_body"}:
        blockers.append("fixture/frozen ai_mode is not allowed for R4")
    if manifest.get("total_scenarios") != R4_SCENARIO_TARGET:
        blockers.append("total_scenarios != 36")
    if int(manifest.get("maximum_gmail_sends") or 0) > R4_SEND_MAX:
        blockers.append("maximum_gmail_sends > 20")
    if int(manifest.get("minimum_no_send") or 0) < R4_NO_SEND_MIN:
        blockers.append("minimum_no_send < 16")
    if manifest.get("automatic_gmail") is not False:
        blockers.append("automatic_gmail must be false")
    if manifest.get("production_activation") is not False:
        blockers.append("production_activation must be false")
    if manifest.get("no_automatic_retry") is not True:
        blockers.append("no_automatic_retry must be true")
    if manifest.get("no_drafts") is not True:
        blockers.append("no_drafts must be true")
    if manifest.get("r3_hold_override_generalized") is not False:
        blockers.append("R3 hold override must not be generalized")

    semantic = manifest.get("semantic_payload")
    expected_hash = manifest.get("manifest_semantic_hash")
    if not isinstance(semantic, dict) or not expected_hash:
        blockers.append("missing semantic payload/hash")
    else:
        actual = compute_r4_semantic_manifest_hash(semantic)
        if actual != expected_hash:
            blockers.append("manifest_semantic_hash mismatch")

    if list(manifest.get("scenario_ids") or []) != list(R4_SCENARIO_IDS):
        blockers.append("scenario_ids do not match locked registry")

    return blockers
