"""Focused tests for R4 reviewed-live campaign executor (mocked; no Gmail)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.evaluation.profile_testbot.qualification.coworker_r4_approval_artifact import (
    build_r4_approval_artifact_example,
    load_r4_approval_artifact,
    validate_r4_approval_artifact,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_execution import (
    run_r4_live_campaign,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_hold_materialization import (
    R4_0088_SCENARIO_ID,
    apply_r4_0088_hold_materialization_to_action,
    resolve_r4_0088_hold_materialization,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_live_jit import (
    run_r4_full_live_jit,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_mailbox_baseline import (
    build_r4_mailbox_baseline,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_mutation_contract import (
    validate_r4_mutation_operation,
    R4_MUTATION_PROCESS_DELIVERY,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_0088_REVIEWED_BODY_HASH,
    R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
    R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    R4_LOCKED_REVIEW_ARTIFACT_SHA256,
    R4_NO_SEND_SCENARIO_IDS,
    R4_SEND_SCENARIO_IDS,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_reviewed_snapshot import (
    R4ReviewedBodySnapshot,
    validate_r4_snapshot_for_reply,
)

CAND = Path("storage/status/digital-coworker-r4-candidates-b7fd95e.json")
REV = Path("storage/status/digital-coworker-r4-human-review-scored-b7fd95e.json")
MAN = Path("storage/status/digital-coworker-r4-manifest-b7fd95e.json")
EXECUTOR = "9c743968361cfa986017704167bf35342748bbca"
RECIPIENT = "niklas.palm@sol-f.se"


pytestmark = pytest.mark.skipif(
    not CAND.is_file() or not REV.is_file() or not MAN.is_file(),
    reason="locked R4 artifacts required",
)


@pytest.fixture
def locked():
    return {
        "candidates": json.loads(CAND.read_text(encoding="utf-8")),
        "review": json.loads(REV.read_text(encoding="utf-8")),
        "manifest": json.loads(MAN.read_text(encoding="utf-8")),
    }


def test_execute_missing_approval_blocks_before_gmail(tmp_path, locked):
    result = run_r4_live_campaign(
        mode="execute",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        status_dir=tmp_path,
    )
    assert result["overall_status"] == "STOPPED"
    assert "approval" in str(result.get("stop_reason")).lower() or result.get("failure_stage") == "approval_gate"
    assert result["gmail_sends"] == 0
    assert result["llm_calls"] == 0
    assert result["candidates_regenerated"] is False


def test_executor_sha_mismatch_blocks(tmp_path, locked):
    body_hashes = {
        c["scenario_id"]: c["body_hash"] for c in locked["candidates"]["send_candidates"]
    }
    example = build_r4_approval_artifact_example(
        executor_runtime_sha=EXECUTOR,
        manifest_path=str(MAN),
        candidate_package_path=str(CAND),
        human_review_path=str(REV),
        body_hashes=body_hashes,
        recipient_allowlist=["ni@sol-f.se"],
    )
    example["manual_execution_approved"] = True
    example["unsigned_example"] = False
    example["approved_at"] = "2026-08-05T20:00:00Z"
    example["executor_runtime_sha"] = "0" * 40
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(example), encoding="utf-8")
    art = load_r4_approval_artifact(path)
    val = validate_r4_approval_artifact(
        art,
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXECUTOR,
        manifest_semantic_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_sha256=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        body_hashes=body_hashes,
    )
    assert not val.valid
    assert any("executor_runtime_sha" in b for b in val.blockers)


def test_candidate_sha_and_hash_mismatches_block(locked):
    jit = run_r4_full_live_jit(
        candidate_runtime_sha="1" * 40,
        executor_runtime_sha=EXECUTOR,
        manifest=locked["manifest"],
        candidates=locked["candidates"],
        human_review=locked["review"],
        human_review_path=REV,
        run_live_probes=False,
    )
    assert jit["passed"] is False
    assert any("candidate_runtime_sha" in b for b in jit["blockers"])


def test_body_tamper_blocks_snapshot():
    snap = R4ReviewedBodySnapshot(
        campaign_type="coworker_r4_live_quality_campaign",
        execution_mode="r4_reviewed_live_candidate",
        scenario_id="PTB-DCQ-0000",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXECUTOR,
        manifest_semantic_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_artifact_hash=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        plan_hash="p",
        reviewed_body="x",
        reviewed_body_hash="deadbeef",
        review_status="PASS",
        renderer_type="constrained_llm_v1",
        model_id="gpt-4o-mini",
        prompt_version="coworker_constrained_llm_v5",
        recipient="ni@sol-f.se",
        campaign_id="c",
        evaluation_run_id="e",
    )
    blockers = validate_r4_snapshot_for_reply(
        snap,
        expected_body_hash="abcd",
        send_scenario_ids=set(R4_SEND_SCENARIO_IDS),
        recipient="ni@sol-f.se",
    )
    assert "body_hash_mismatch" in blockers


def test_fail_or_pending_or_blocking_note_rejected():
    snap = R4ReviewedBodySnapshot(
        campaign_type="coworker_r4_live_quality_campaign",
        execution_mode="r4_reviewed_live_candidate",
        scenario_id="PTB-DCQ-0000",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXECUTOR,
        manifest_semantic_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_artifact_hash=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        plan_hash="p",
        reviewed_body="x",
        reviewed_body_hash="h",
        review_status="FAIL",
        renderer_type="constrained_llm_v1",
        model_id="m",
        prompt_version="p",
        recipient="ni@sol-f.se",
        campaign_id="c",
        evaluation_run_id="e",
    )
    assert validate_r4_snapshot_for_reply(
        snap,
        expected_body_hash="h",
        send_scenario_ids=set(R4_SEND_SCENARIO_IDS),
        recipient="ni@sol-f.se",
        blocking_notes=["x"],
    )


def test_execute_never_regenerates_or_calls_llm(tmp_path, locked, monkeypatch):
    calls = {"gen": 0}

    def boom(*a, **k):
        calls["gen"] += 1
        raise AssertionError("generate_r4_candidates must not be called")

    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.generate_r4_candidates",
        boom,
    )
    result = run_r4_live_campaign(
        mode="execute",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        status_dir=tmp_path,
    )
    assert calls["gen"] == 0
    assert result["candidates_regenerated"] is False
    assert result["llm_calls"] == 0
    assert result["gmail_sends"] == 0


def test_locked_manifest_rehydrates_semantic_payload(tmp_path, locked):
    assert "semantic_payload" not in locked["manifest"] or not isinstance(
        locked["manifest"].get("semantic_payload"), dict
    )
    result = run_r4_live_campaign(
        mode="dry_run",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        status_dir=tmp_path,
    )
    assert result["overall_status"] == "PASS"
    assert result.get("manifest_blockers") == []
    assert result["gmail_sends"] == 0


def test_structural_dry_run_not_full_jit(tmp_path, locked):
    result = run_r4_live_campaign(
        mode="dry_run",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        status_dir=tmp_path,
    )
    assert result.get("full_live_jit") is False or result.get("jit_type") == "structural_dry_run"
    assert result["gmail_sends"] == 0


def test_full_jit_requires_live_probes(locked, monkeypatch):
    def fake_collect(**kwargs):
        return {
            "api_build_git_sha": EXECUTOR,
            "worker_build_git_sha": EXECUTOR,
            "runner_build_git_sha": EXECUTOR,
            "tenant_intake_ready": False,
            "sender_gmail_ready": False,
            "recipient_gmail_ready": False,
            "reply_provider_ready": False,
            "delivery_observation_ready": False,
            "exact_message_ready": False,
            "registration_contract_ready": False,
            "mutation_contract_ready": False,
            "orphan_isolation_ready": False,
            "probe_blockers": ["tenant_intake_ready!=true"],
        }

    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_live_jit.collect_r4_live_probes",
        fake_collect,
    )
    jit = run_r4_full_live_jit(
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXECUTOR,
        manifest=locked["manifest"],
        candidates=locked["candidates"],
        human_review=locked["review"],
        human_review_path=REV,
        run_live_probes=True,
        auto_collect_live_probes=True,
    )
    assert jit["full_live_jit"] is True
    assert jit["live_probes_collected"] is True
    assert jit["passed"] is False
    assert any("tenant_intake" in b or "sender_gmail" in b for b in jit["blockers"])


def test_full_jit_pass_with_probe_flags(locked):
    jit = run_r4_full_live_jit(
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXECUTOR,
        manifest=locked["manifest"],
        candidates=locked["candidates"],
        human_review=locked["review"],
        human_review_path=REV,
        api_build_git_sha=EXECUTOR,
        worker_build_git_sha=EXECUTOR,
        runner_build_git_sha=EXECUTOR,
        tenant_intake_ready=True,
        sender_gmail_ready=True,
        recipient_gmail_ready=True,
        reply_provider_ready=True,
        delivery_observation_ready=True,
        exact_message_ready=True,
        registration_contract_ready=True,
        mutation_contract_ready=True,
        orphan_isolation_ready=True,
        run_live_probes=True,
        auto_collect_live_probes=False,
        recipient_email=RECIPIENT,
    )
    assert jit["passed"] is True
    assert jit["gmail_sends"] == 0
    assert jit["live_probes_collected"] is False


def test_full_jit_auto_collect_invoked(locked, monkeypatch):
    calls = {"n": 0}

    def fake_collect(**kwargs):
        calls["n"] += 1
        return {
            "api_build_git_sha": EXECUTOR,
            "worker_build_git_sha": EXECUTOR,
            "runner_build_git_sha": EXECUTOR,
            "tenant_intake_ready": True,
            "sender_gmail_ready": True,
            "recipient_gmail_ready": True,
            "reply_provider_ready": True,
            "delivery_observation_ready": True,
            "exact_message_ready": True,
            "registration_contract_ready": True,
            "mutation_contract_ready": True,
            "orphan_isolation_ready": True,
            "probe_blockers": [],
        }

    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_live_jit.collect_r4_live_probes",
        fake_collect,
    )
    jit = run_r4_full_live_jit(
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXECUTOR,
        manifest=locked["manifest"],
        candidates=locked["candidates"],
        human_review=locked["review"],
        human_review_path=REV,
        run_live_probes=True,
        auto_collect_live_probes=True,
        recipient_email=RECIPIENT,
    )
    assert calls["n"] == 1
    assert jit["passed"] is True
    assert jit["live_probes_collected"] is True


def test_structural_dry_run_skips_live_probe_collection(tmp_path, locked, monkeypatch):
    calls = {"n": 0}

    def boom(**kwargs):
        calls["n"] += 1
        raise AssertionError("collect must not run in structural dry-run")

    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_live_jit.collect_r4_live_probes",
        boom,
    )
    result = run_r4_live_campaign(
        mode="dry_run",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        status_dir=tmp_path,
    )
    assert calls["n"] == 0
    assert result["jit_type"] == "structural_dry_run"
    assert result["full_live_jit"] is False


def test_r4_0088_preserves_hold_and_never_execution_allowed():
    ok = resolve_r4_0088_hold_materialization(
        scenario_id=R4_0088_SCENARIO_ID,
        base_authorization="hold_for_review",
        reviewed_body_hash=R4_0088_REVIEWED_BODY_HASH,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_artifact_hash=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
    )
    assert ok.eligible
    assert ok.authorization == "approval_required"
    assert ok.details["r3_override_reused"] is False
    action = apply_r4_0088_hold_materialization_to_action(
        {"type": "send_customer_auto_reply", "_authorization": "execution_allowed"},
        resolution=ok,
    )
    assert action["_authorization"] == "approval_required"
    assert action.get("_r4_0088_materialized") is True

    bad = resolve_r4_0088_hold_materialization(
        scenario_id=R4_0088_SCENARIO_ID,
        base_authorization="hold_for_review",
        reviewed_body_hash=R4_0088_REVIEWED_BODY_HASH,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_artifact_hash=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        risk_tags=["fraud"],
    )
    assert not bad.eligible


def test_r3_override_not_used_for_r4_0088():
    # Resolving with wrong package hash must fail; R3 path is not consulted.
    res = resolve_r4_0088_hold_materialization(
        scenario_id=R4_0088_SCENARIO_ID,
        base_authorization="hold_for_review",
        reviewed_body_hash=R4_0088_REVIEWED_BODY_HASH,
        candidate_package_semantic_hash="wrong",
        human_review_artifact_hash=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
    )
    assert not res.eligible


def test_partial_campaign_marks_not_run(tmp_path, locked, monkeypatch):
    def failing_executor(**kwargs):
        return {
            "scenario_id": kwargs["scenario_id"],
            "planned_gmail_send": True,
            "status": "failed",
            "failure_stage": "provider",
            "failure_reason": "provider_exception",
            "gmail_sends": 0,
            "gmail_drafts": 0,
            "evaluation_run_id": kwargs.get("evaluation_run_id"),
        }

    recipient = "niklas.palm@sol-f.se"
    cfg = MagicMock()
    cfg.sender_emails = {"qvarsken@gmail.com"}
    cfg.recipient_emails = {recipient}
    monkeypatch.setattr(
        "app.evaluation.live.config.get_live_eval_config",
        lambda: cfg,
    )
    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.run_r4_full_live_jit",
        lambda **kwargs: {"passed": True, "blockers": [], "full_live_jit": True},
    )
    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.build_r4_mailbox_baseline",
        lambda **kwargs: {"passed": True, "blockers": [], "mutations_performed": False},
    )
    body_hashes = {
        c["scenario_id"]: c["body_hash"] for c in locked["candidates"]["send_candidates"]
    }
    example = build_r4_approval_artifact_example(
        executor_runtime_sha=EXECUTOR,
        manifest_path=str(MAN.resolve()),
        candidate_package_path=str(CAND.resolve()),
        human_review_path=str(REV.resolve()),
        body_hashes=body_hashes,
        recipient_allowlist=[recipient],
    )
    example["manual_execution_approved"] = True
    example.pop("unsigned_example", None)
    example["approved_at"] = "2026-08-05T20:00:00Z"
    ap = tmp_path / "ok-approval.json"
    ap.write_text(json.dumps(example), encoding="utf-8")

    result = run_r4_live_campaign(
        mode="execute",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        approval_path=ap,
        status_dir=tmp_path,
        recipient=recipient,
        live_executor=failing_executor,
        tenant_intake_ready=True,
        sender_gmail_ready=True,
        recipient_gmail_ready=True,
        reply_provider_ready=True,
        delivery_observation_ready=True,
        exact_message_ready=True,
        registration_contract_ready=True,
        mutation_contract_ready=True,
    )
    assert result["overall_status"] == "partial_campaign_stopped"
    assert result.get("resume_forbidden") is True
    statuses = {o["scenario_id"]: o["status"] for o in result["scenario_outcomes"]}
    assert statuses[R4_SEND_SCENARIO_IDS[0]] == "failed"
    assert statuses[R4_SEND_SCENARIO_IDS[1]] == "not_run"
    assert result["gmail_sends"] == 0


def test_mailbox_baseline_excludes_r4_tokens():
    baseline = build_r4_mailbox_baseline(
        campaign_id="camp",
        existing_r4_subject_tokens=["KROWOLF-R4/old"],
    )
    assert baseline["passed"] is False
    assert baseline["mutations_performed"] is False


def test_mutation_contract_forbids_drafts_and_auto_gmail():
    ok = validate_r4_mutation_operation(
        operation=R4_MUTATION_PROCESS_DELIVERY,
        tenant_id="TENANT_LIVE_EVAL",
        campaign_type="coworker_r4_live_quality_campaign",
        execution_mode="r4_reviewed_live_candidate",
        ai_mode="reviewed_live_llm_body",
    )
    assert ok.allowed
    bad = validate_r4_mutation_operation(
        operation=R4_MUTATION_PROCESS_DELIVERY,
        tenant_id="TENANT_LIVE_EVAL",
        campaign_type="coworker_r4_live_quality_campaign",
        execution_mode="r4_reviewed_live_candidate",
        ai_mode="reviewed_live_llm_body",
        automatic_gmail=True,
        drafts_allowed=True,
    )
    assert not bad.allowed


def test_send_no_send_counts_locked():
    assert len(R4_SEND_SCENARIO_IDS) == 20
    assert len(R4_NO_SEND_SCENARIO_IDS) == 16


def test_review_artifact_hash_stable():
    digest = hashlib.sha256(REV.read_bytes()).hexdigest()
    assert digest == R4_LOCKED_REVIEW_ARTIFACT_SHA256
