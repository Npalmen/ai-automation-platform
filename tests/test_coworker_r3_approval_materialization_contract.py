"""Focused tests for R3 frozen approval materialization contract (no Gmail send)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.profile_testbot.qualification.coworker_r3_approval_materialization_contract import (
    ORPHANED_ATTEMPT_7_CAMPAIGN_ID,
    ORPHANED_ATTEMPT_7_EVALUATION_RUN_IDS,
    ORPHANED_ATTEMPT_7_ORPHAN_GROUP_ID,
    ORPHANED_ATTEMPT_7_SCENARIO_RUNS,
    R3_HOLD_OVERRIDE_CANONICAL_HASHES,
    R3_OVERRIDE_CONTRACT_ID,
    apply_r3_hold_override_to_action,
    probe_orphaned_attempt_7_campaign,
    resolve_r3_frozen_approval_materialization,
    run_r3_approval_materialization_readiness,
    should_materialize_r3_action_dispatch_despite_hold,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
    ORPHANED_R3_INBOUND_TRIGGERS,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_mutation_contract import (
    R3_ORPHAN_ATTEMPT_EVALUATION_RUN_IDS,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (
    R3_APPROVED_SEND_BODY_HASHES,
)
from app.workflows.action_authorization import ActionAuthorization, authorize_action
from app.workflows.decision_contract import (
    DecisionRecommendation,
    PolicyAuthorization,
    resolve_policy_authorization,
)
from app.workflows.decision_record import ALLOWED_METADATA_KEYS


HASH_0088 = R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0088"]
RUNTIME_SHA = "a" * 40
MANIFEST_HASH = "b" * 64


def _artifact(**overrides):
    payload = {
        "runtime_sha": RUNTIME_SHA,
        "manifest_hash": MANIFEST_HASH,
        "manual_execution_approved": True,
        "body_hashes_approved": True,
        "campaign_type": "coworker_r3_frozen_live_canary",
        "execution_mode": "r3_frozen_approved_body",
        "attempt_number": 8,
    }
    payload.update(overrides)
    return payload


def _base_reasons():
    return [
        "risk:complaint",
        "customer_inquiry_low_confidence",
        "llm_unavailable",
        "missing_identity",
        "missing_requested_service",
        "inquiry_missing_identity",
        "content_risk_detected",
    ]


def _resolve(**overrides):
    kwargs = {
        "db": None,
        "job": None,
        "action": {
            "type": "send_customer_auto_reply",
            "tenant_id": "TENANT_LIVE_EVAL",
            "to": "ni@sol-f.se",
        },
        "scenario_id": "PTB-DCQ-0088",
        "base_policy_authorization": "hold_for_review",
        "base_policy_reasons": _base_reasons(),
        "classification": {
            "ticket_type": "complaint",
            "business_intent": "support_complaint",
            "low_confidence": True,
            "llm_unavailable": True,
            "used_fallback": True,
        },
        "frozen_body_hash": HASH_0088,
        "manifest_hash": MANIFEST_HASH,
        "runner_sha": RUNTIME_SHA,
        "manual_approval_artifact": _artifact(),
        "base_risk_tags": ["complaint"],
        "tenant_id": "TENANT_LIVE_EVAL",
        "campaign_type": "coworker_r3_frozen_live_canary",
        "execution_mode": "r3_frozen_approved_body",
    }
    kwargs.update(overrides)
    return resolve_r3_frozen_approval_materialization(**kwargs)


def test_ordinary_complaint_policy_remains_hold_for_review():
    result = resolve_policy_authorization(
        detected_job_type="customer_inquiry",
        recommendation=DecisionRecommendation.AUTO_ROUTE,
        recommendation_raw="auto_route",
        auto_actions={"customer_inquiry": "semi"},
        low_confidence=False,
        used_fallback=False,
        risk_detected=True,
    )
    assert result.authorization == PolicyAuthorization.HOLD_FOR_REVIEW


def test_ordinary_low_confidence_policy_remains_hold():
    result = resolve_policy_authorization(
        detected_job_type="customer_inquiry",
        recommendation=DecisionRecommendation.AUTO_ROUTE,
        recommendation_raw="auto_route",
        auto_actions={"customer_inquiry": "semi"},
        low_confidence=True,
        used_fallback=False,
        risk_detected=False,
    )
    assert result.authorization == PolicyAuthorization.HOLD_FOR_REVIEW


def test_ordinary_llm_fallback_policy_remains_hold():
    result = resolve_policy_authorization(
        detected_job_type="customer_inquiry",
        recommendation=DecisionRecommendation.AUTO_ROUTE,
        recommendation_raw="auto_route",
        auto_actions={"customer_inquiry": "semi"},
        low_confidence=False,
        used_fallback=True,
        risk_detected=False,
    )
    assert result.authorization == PolicyAuthorization.HOLD_FOR_REVIEW


def test_authorize_action_still_blocks_hold_for_review():
    auth = authorize_action(
        "send_customer_auto_reply",
        job_type="customer_inquiry",
        auto_actions={"customer_inquiry": "semi"},
        risk_detected=True,
        policy_decision="hold_for_review",
        reply_safety_passed=True,
    )
    assert auth == ActionAuthorization.BLOCKED


def test_r3_0088_exact_contract_maps_hold_to_approval_required():
    res = _resolve()
    assert res.override_eligible is True
    assert res.override_applied is True
    assert res.r3_override_authorization == ActionAuthorization.APPROVAL_REQUIRED.value
    assert res.execution_allowed is False
    assert res.expected_approval_state == "pending"
    assert res.base_policy_authorization == "hold_for_review"


def test_override_never_returns_execution_allowed():
    res = _resolve()
    assert res.execution_allowed is False
    assert res.to_dict()["execution_allowed"] is False


def test_override_creates_pending_materialization_flags():
    res = _resolve()
    assert res.materialize_pending_approval is True
    assert res.r3_override_contract == R3_OVERRIDE_CONTRACT_ID


def test_frozen_body_hash_required_and_matched():
    bad = _resolve(frozen_body_hash="0" * 64)
    assert bad.override_eligible is False
    assert any("hash" in b for b in bad.blockers)


def test_wrong_scenario_blocks():
    res = _resolve(scenario_id="PTB-DCQ-0000")
    assert res.override_required is False
    assert res.override_applied is False


def test_scenario_outside_send_registry_blocks():
    res = _resolve(scenario_id="PTB-DCQ-9999")
    assert res.override_eligible is False
    assert any("registry" in b for b in res.blockers)


def test_no_send_scenario_cannot_get_override():
    res = _resolve(scenario_id="PTB-DCQ-0032")
    assert res.override_eligible is False
    assert any("no-send" in b for b in res.blockers)


def test_wrong_manifest_hash_blocks():
    res = _resolve(
        manifest_hash="c" * 64,
        manual_approval_artifact=_artifact(manifest_hash=MANIFEST_HASH),
    )
    assert res.override_eligible is False


def test_wrong_runner_sha_blocks():
    res = _resolve(
        runner_sha="d" * 40,
        manual_approval_artifact=_artifact(runtime_sha=RUNTIME_SHA),
    )
    assert res.override_eligible is False


def test_wrong_tenant_blocks():
    res = _resolve(tenant_id="TENANT_OTHER")
    assert res.active is False or res.override_eligible is False


def test_wrong_campaign_type_blocks():
    res = _resolve(campaign_type="other_campaign")
    assert res.override_eligible is False


def test_wrong_execution_mode_blocks():
    res = _resolve(execution_mode="live_llm")
    assert res.override_eligible is False


def test_missing_manual_approval_artifact_blocks():
    res = _resolve(manual_approval_artifact=None, probe_only=False)
    assert res.override_eligible is False
    assert any("approval artifact" in b for b in res.blockers)


def test_old_sha_approval_artifact_blocks():
    res = _resolve(manual_approval_artifact=_artifact(runtime_sha="e" * 40))
    assert res.override_eligible is False


def test_recipient_mismatch_blocks():
    snap = SimpleNamespace(
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="PTB-DCQ-0088",
        ai_mode="r3_frozen_approved_body",
        expected_sender="ni@sol-f.se",
        evaluation_run_id="new-run-id",
    )
    res = _resolve(
        live_eval_snapshot=snap,
        action={
            "type": "send_customer_auto_reply",
            "tenant_id": "TENANT_LIVE_EVAL",
            "to": "other@example.com",
        },
    )
    assert res.override_eligible is False
    assert any("recipient" in b for b in res.blockers)


def test_prompt_injection_risk_blocks():
    res = _resolve(
        base_policy_reasons=_base_reasons() + ["prompt_injection"],
        base_risk_tags=["complaint", "prompt_injection"],
    )
    assert res.override_eligible is False


def test_critical_high_risk_blocks():
    res = _resolve(
        base_policy_reasons=_base_reasons() + ["critical_security"],
        base_risk_tags=["complaint", "critical_security"],
    )
    assert res.override_eligible is False


def test_unknown_risk_tag_blocks():
    res = _resolve(base_risk_tags=["complaint", "brand_new_risk_tag"])
    assert res.override_eligible is False


def test_unknown_base_policy_reason_blocks():
    res = _resolve(base_policy_reasons=_base_reasons() + ["totally_new_reason"])
    assert res.override_eligible is False


def test_complaint_plus_exact_body_gives_pending():
    res = _resolve()
    assert res.expected_approval_state == "pending"
    assert res.frozen_body_hash == HASH_0088 == R3_HOLD_OVERRIDE_CANONICAL_HASHES["PTB-DCQ-0088"]


def test_base_policy_provenance_preserved():
    res = _resolve()
    prov = res.provenance()
    assert prov["base_policy_authorization"] == "hold_for_review"
    assert "risk:complaint" in prov["base_policy_reasons"]
    assert prov["r3_override_applied"] is True


def test_override_provenance_stored_separately():
    res = _resolve()
    prov = res.provenance()
    assert prov["r3_override_contract"] == R3_OVERRIDE_CONTRACT_ID
    assert prov["r3_override_authorization"] == "approval_required"
    assert prov["r3_override_reason"] == "frozen_body_preapproved_for_r3_canary"
    assert "base_policy_authorization" in ALLOWED_METADATA_KEYS
    assert "r3_override_applied" in ALLOWED_METADATA_KEYS


def test_aborted_attempt7_job_ids_blocked():
    job = SimpleNamespace(
        job_id="62a3e06a-4bff-4a07-a853-24e1cddb66f2",
        tenant_id="TENANT_LIVE_EVAL",
        input_data={},
    )
    res = _resolve(job=job)
    assert res.override_eligible is False
    assert any("attempt-7" in b for b in res.blockers)


def test_attempt7_approval_cannot_be_reused():
    res = _resolve(manual_approval_artifact=_artifact(attempt_number=7))
    assert res.override_eligible is False


def test_attempt7_campaign_id_cannot_be_reused():
    res = _resolve(
        manual_approval_artifact=_artifact(campaign_id=ORPHANED_ATTEMPT_7_CAMPAIGN_ID)
    )
    assert res.override_eligible is False


def test_attempt7_operation_ids_blocked():
    res = _resolve(
        live_eval_snapshot=SimpleNamespace(
            tenant_id="TENANT_LIVE_EVAL",
            scenario_id="PTB-DCQ-0088",
            ai_mode="r3_frozen_approved_body",
            expected_sender="ni@sol-f.se",
            evaluation_run_id="f1be25bc-aecb-4b94-bb65-46a0aae0bf01",
        )
    )
    assert res.override_eligible is False


def test_readiness_simulates_8_of_8_send_and_7_of_7_no_send():
    report = run_r3_approval_materialization_readiness(
        manifest={"manifest_hash": MANIFEST_HASH, "scenarios": []},
        approval_artifact=_artifact(),
        runtime_sha=RUNTIME_SHA,
    )
    assert report["approval_materialization_send_ready_count"] == 8
    assert report["approval_materialization_no_send_ready_count"] == 7
    assert report["approval_materialization_contract_valid"] is True
    assert report["PTB-DCQ-0088_base_policy_authorization"] == "hold_for_review"
    assert report["PTB-DCQ-0088_override_eligible"] is True
    assert report["PTB-DCQ-0088_expected_approval_state"] == "pending"
    assert report["gmail_sent"] is False
    assert report["gmail_drafts_created"] is False


def test_readiness_shows_0088_base_hold_override_pending():
    report = run_r3_approval_materialization_readiness(
        manifest={"manifest_hash": MANIFEST_HASH},
        approval_artifact=_artifact(),
        runtime_sha=RUNTIME_SHA,
    )
    row = next(r for r in report["scenarios"] if r["scenario_id"] == "PTB-DCQ-0088")
    assert row["base_policy_authorization"] == "hold_for_review"
    assert row["r3_override_required"] is True
    assert row["r3_override_eligible"] is True
    assert row["expected_approval_state"] == "pending"


def test_apply_override_annotates_action_as_pending_not_execute():
    job = SimpleNamespace(
        job_id="fresh-job",
        tenant_id="TENANT_LIVE_EVAL",
        input_data={
            "live_eval": {
                "evaluation_run_id": "11111111-1111-4111-8111-111111111111",
                "tenant_id": "TENANT_LIVE_EVAL",
                "scenario_id": "PTB-DCQ-0088",
                "attempt_id": 1,
                "transport_mode": "live_gmail",
                "ai_mode": "r3_frozen_approved_body",
                "config_hash": "cfg",
                "expected_sender": "ni@sol-f.se",
                "expected_recipient": "recipient@eval.test",
                "trusted": True,
            }
        },
    )
    action = {
        "type": "send_customer_auto_reply",
        "tenant_id": "TENANT_LIVE_EVAL",
        "to": "ni@sol-f.se",
        "subject": "Re: reklamation",
        "body": "placeholder",
        "_needs_approval": True,
    }
    policy = {
        "decision": "hold_for_review",
        "reasons": _base_reasons(),
        "risk_categories": ["complaint"],
        "detected_job_type": "customer_inquiry",
        "recommendation": "HOLD",
    }
    annotated, resolution = apply_r3_hold_override_to_action(
        job=job,
        action=action,
        policy_payload=policy,
        db=None,
    )
    assert annotated.get("_r3_override_applied") is True
    assert annotated.get("_needs_approval") is True
    assert annotated.get("_authorization") == "approval_required"
    assert annotated.get("_skip") is False
    assert resolution is not None
    assert resolution.execution_allowed is False


def test_orchestrator_hook_allows_dispatch_for_0088_hold():
    job = SimpleNamespace(
        job_id="fresh-job",
        tenant_id="TENANT_LIVE_EVAL",
        input_data={
            "live_eval": {
                "evaluation_run_id": "22222222-2222-4222-8222-222222222222",
                "tenant_id": "TENANT_LIVE_EVAL",
                "scenario_id": "PTB-DCQ-0088",
                "attempt_id": 1,
                "transport_mode": "live_gmail",
                "ai_mode": "r3_frozen_approved_body",
                "config_hash": "cfg",
                "expected_sender": "ni@sol-f.se",
                "expected_recipient": "recipient@eval.test",
                "trusted": True,
            }
        },
    )
    assert should_materialize_r3_action_dispatch_despite_hold(
        job=job,
        db=None,
        policy_payload={
            "decision": "hold_for_review",
            "reasons": _base_reasons(),
            "risk_categories": ["complaint"],
            "detected_job_type": "customer_inquiry",
        },
    )


def test_orchestrator_hook_denies_non_r3_hold():
    job = SimpleNamespace(
        job_id="prod-job",
        tenant_id="TENANT_PRODUCTION_PILOT_01",
        input_data={},
    )
    assert not should_materialize_r3_action_dispatch_despite_hold(
        job=job,
        db=None,
        policy_payload={"decision": "hold_for_review", "reasons": ["risk:complaint"]},
    )


def test_attempt7_orphans_registered_and_excluded_from_pass_counts():
    assert ORPHANED_ATTEMPT_7_ORPHAN_GROUP_ID == "orphaned_attempt_7"
    assert len(ORPHANED_ATTEMPT_7_SCENARIO_RUNS) == 8
    assert len(ORPHANED_ATTEMPT_7_EVALUATION_RUN_IDS) == 8
    assert ORPHANED_ATTEMPT_7_EVALUATION_RUN_IDS <= R3_ORPHAN_ATTEMPT_EVALUATION_RUN_IDS
    attempt7 = [o for o in ORPHANED_R3_INBOUND_TRIGGERS if o.get("attempt") == 7]
    assert len(attempt7) == 8
    sent = [o for o in attempt7 if o.get("approved_reply_sent")]
    blocked = [o for o in attempt7 if not o.get("approved_reply_sent")]
    assert len(sent) == 7
    assert len(blocked) == 1
    assert all(o.get("exclude_from_approved_reply_count") for o in attempt7)
    assert all(o.get("reuse_blocked") for o in attempt7)
    assert all(o.get("never_retry") for o in attempt7)


def test_frozen_body_hashes_unchanged():
    assert HASH_0088 == "0748626a0aa6767b2b9bf427e2d68fe33d9fd0ab0f81a5e6e8a6b4fdef939338"
    assert R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0000"].startswith("0ac564e1")


def test_probe_attempt7_campaign_read_only(monkeypatch):
    class _Row:
        def __init__(self, status="aborted"):
            self.status = status

    def _get_run(_db, rid, tenant_id=None):
        if rid in ORPHANED_ATTEMPT_7_EVALUATION_RUN_IDS:
            return _Row("aborted")
        return None

    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r3_approval_materialization_contract.LiveEvalRunRepository.get_run",
        _get_run,
    )
    result = probe_orphaned_attempt_7_campaign(MagicMock())
    assert result["orphaned_attempt_7_campaign_verified"] is True
    assert result["attempt_7_real_replies_verified"] == 7
    assert result["attempt_7_blocked_without_reply_verified"] == 1
    assert result["attempt_7_unknown_outcomes"] == 0
    assert result["attempt_7_reuse_blocked"] is True
    assert result["automatic_retry"] is False
