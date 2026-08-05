"""Focused tests for R4 live-backend wiring (mocked Gmail; no real writes)."""

from __future__ import annotations

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
from app.evaluation.profile_testbot.qualification.coworker_r4_live_backend import (
    R4_LIVE_BACKEND_TYPE,
    build_r4_live_executor,
    describe_r4_live_backend_wiring,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_EXECUTE_AI_MODE,
    R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    R4_NO_SEND_SCENARIO_IDS,
    R4_SEND_SCENARIO_IDS,
)

CAND = Path("storage/status/digital-coworker-r4-candidates-b7fd95e.json")
REV = Path("storage/status/digital-coworker-r4-human-review-scored-b7fd95e.json")
MAN = Path("storage/status/digital-coworker-r4-manifest-b7fd95e.json")
EXECUTOR = "9fd262fe068d565709991f9958de76d280637dcc"
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


def _write_valid_approval(tmp_path: Path, locked: dict, *, recipient: str = RECIPIENT) -> Path:
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
    example["ai_mode"] = R4_EXECUTE_AI_MODE
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(example), encoding="utf-8")
    return path


@pytest.fixture
def live_cfg(monkeypatch):
    cfg = MagicMock()
    cfg.sender_emails = {"qvarsken@gmail.com"}
    cfg.recipient_emails = {RECIPIENT}
    cfg.enabled = True
    cfg.gmail_enabled = True
    monkeypatch.setattr(
        "app.evaluation.live.config.get_live_eval_config",
        lambda: cfg,
    )
    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.get_live_eval_config",
        lambda: cfg,
        raising=False,
    )
    return cfg


def test_describe_wiring_without_gmail():
    wiring = describe_r4_live_backend_wiring()
    assert wiring["backend_wired"] is True
    assert wiring["execute_backend_type"] == R4_LIVE_BACKEND_TYPE
    assert wiring["execute_callback_available"] is True
    assert wiring["gmail_client_new"] is False


def test_dry_run_does_not_invoke_factory(tmp_path, locked, monkeypatch):
    calls = {"n": 0}

    def boom(**kwargs):
        calls["n"] += 1
        raise AssertionError("factory must not run in dry-run")

    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.build_r4_live_executor",
        boom,
        raising=False,
    )
    result = run_r4_live_campaign(
        mode="dry_run",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        status_dir=tmp_path,
        live_executor_factory=boom,
    )
    assert calls["n"] == 0
    assert result["overall_status"] == "PASS"
    assert result["backend_wired"] is True
    assert result["gmail_sends"] == 0


def test_full_jit_does_not_invoke_factory(tmp_path, locked, monkeypatch):
    calls = {"n": 0}

    def boom(**kwargs):
        calls["n"] += 1
        raise AssertionError("factory must not run in full-jit")

    jit_flags = dict(
        tenant_intake_ready=True,
        sender_gmail_ready=True,
        recipient_gmail_ready=True,
        reply_provider_ready=True,
        delivery_observation_ready=True,
        exact_message_ready=True,
        registration_contract_ready=True,
        mutation_contract_ready=True,
    )
    result = run_r4_live_campaign(
        mode="full_jit",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        status_dir=tmp_path,
        live_executor_factory=boom,
        **jit_flags,
    )
    assert calls["n"] == 0
    assert result.get("backend_invoked") in (None, False)


def test_missing_approval_does_not_call_factory(tmp_path, locked):
    calls = {"n": 0}

    def boom(**kwargs):
        calls["n"] += 1
        raise AssertionError("factory must not run")

    result = run_r4_live_campaign(
        mode="execute",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        status_dir=tmp_path,
        live_executor_factory=boom,
    )
    assert calls["n"] == 0
    assert result["overall_status"] == "STOPPED"
    assert result["gmail_sends"] == 0


def test_invalid_approval_does_not_call_factory(tmp_path, locked, live_cfg):
    calls = {"n": 0}

    def boom(**kwargs):
        calls["n"] += 1
        raise AssertionError("factory must not run")

    ap = _write_valid_approval(tmp_path, locked)
    payload = json.loads(ap.read_text(encoding="utf-8"))
    payload["ai_mode"] = "wrong"
    ap.write_text(json.dumps(payload), encoding="utf-8")
    result = run_r4_live_campaign(
        mode="execute",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        approval_path=ap,
        status_dir=tmp_path,
        recipient=RECIPIENT,
        live_executor_factory=boom,
        tenant_intake_ready=True,
        sender_gmail_ready=True,
        recipient_gmail_ready=True,
        reply_provider_ready=True,
        delivery_observation_ready=True,
        exact_message_ready=True,
        registration_contract_ready=True,
        mutation_contract_ready=True,
    )
    assert calls["n"] == 0
    assert result["failure_stage"] == "approval_validation"
    assert result.get("backend_invoked") is False


def test_failed_jit_does_not_call_factory(tmp_path, locked, live_cfg, monkeypatch):
    calls = {"n": 0}

    def boom(**kwargs):
        calls["n"] += 1
        raise AssertionError("factory must not run after JIT fail")

    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.run_r4_full_live_jit",
        lambda **kwargs: {"passed": False, "blockers": ["forced"], "full_live_jit": True},
    )
    ap = _write_valid_approval(tmp_path, locked)
    result = run_r4_live_campaign(
        mode="execute",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        approval_path=ap,
        status_dir=tmp_path,
        recipient=RECIPIENT,
        live_executor_factory=boom,
    )
    assert calls["n"] == 0
    assert result["failure_stage"] == "full_live_jit"
    assert result.get("backend_invoked") is False


def test_execute_wires_factory_after_gates(tmp_path, locked, live_cfg, monkeypatch):
    factory_calls = {"n": 0}
    exec_calls = {"n": 0}

    def factory(**kwargs):
        factory_calls["n"] += 1
        assert kwargs["campaign_id"]
        assert kwargs["approval_artifact"].artifact_hash

        def executor(**kw):
            exec_calls["n"] += 1
            if kw.get("planned_gmail_send") is False or "snapshot" not in kw:
                return {
                    "scenario_id": kw["scenario_id"],
                    "status": "passed",
                    "gmail_sends": 0,
                    "gmail_drafts": 0,
                    "r4_reviewed_body_applied": False,
                }
            return {
                "scenario_id": kw["scenario_id"],
                "status": "passed",
                "gmail_sends": 1,
                "gmail_drafts": 0,
                "adapter_provider": "google_mail",
                "reply_provider_message_id_redacted": "abcd…wxyz",
                "reply_delivery_observed": True,
                "recipient_match": True,
                "thread_match": True,
                "body_hash_match": True,
                "duplicate_count": 0,
                "unknown_outcome": False,
                "approval_executed": True,
            }

        return executor

    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.run_r4_full_live_jit",
        lambda **kwargs: {
            "passed": True,
            "blockers": [],
            "full_live_jit": True,
            "live_probes_collected": True,
        },
    )
    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.build_r4_mailbox_baseline",
        lambda **kwargs: {"passed": True, "blockers": [], "mutations_performed": False},
    )
    ap = _write_valid_approval(tmp_path, locked)
    result = run_r4_live_campaign(
        mode="execute",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        approval_path=ap,
        status_dir=tmp_path,
        recipient=RECIPIENT,
        live_executor_factory=factory,
    )
    assert factory_calls["n"] == 1
    assert exec_calls["n"] == 36
    assert result["overall_status"] == "PASS"
    assert result["live_executor_wired_after_gates"] is True
    assert result["gmail_sends"] == 20
    assert result["gmail_drafts"] == 0
    assert result["llm_calls"] == 0
    assert result["candidates_regenerated"] is False


def test_execute_without_backend_fail_closed(tmp_path, locked, live_cfg, monkeypatch):
    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.run_r4_full_live_jit",
        lambda **kwargs: {"passed": True, "blockers": [], "full_live_jit": True},
    )
    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.build_r4_mailbox_baseline",
        lambda **kwargs: {"passed": True, "blockers": [], "mutations_performed": False},
    )
    ap = _write_valid_approval(tmp_path, locked)
    result = run_r4_live_campaign(
        mode="execute",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        approval_path=ap,
        status_dir=tmp_path,
        recipient=RECIPIENT,
    )
    assert result["overall_status"] == "partial_campaign_stopped"
    assert result["scenario_outcomes"][0]["failure_stage"] == "live_executor_not_invoked"
    assert result["gmail_sends"] == 0


def test_approval_ai_mode_and_recipient_and_approved_at(locked, live_cfg):
    body_hashes = {
        c["scenario_id"]: c["body_hash"] for c in locked["candidates"]["send_candidates"]
    }
    example = build_r4_approval_artifact_example(
        executor_runtime_sha=EXECUTOR,
        manifest_path=str(MAN.resolve()),
        candidate_package_path=str(CAND.resolve()),
        human_review_path=str(REV.resolve()),
        body_hashes=body_hashes,
        recipient_allowlist=[RECIPIENT],
    )
    example["manual_execution_approved"] = True
    example.pop("unsigned_example", None)
    example["approved_at"] = "2026-08-05T20:00:00Z"
    from app.evaluation.profile_testbot.qualification.coworker_r4_approval_artifact import (
        R4ApprovalArtifact,
    )
    from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
        R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        R4_LOCKED_REVIEW_ARTIFACT_SHA256,
    )

    art = R4ApprovalArtifact(path=Path("x"), payload=example, artifact_hash="h")
    ok = validate_r4_approval_artifact(
        art,
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXECUTOR,
        manifest_semantic_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_sha256=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        body_hashes=body_hashes,
        expected_recipient_allowlist=[RECIPIENT],
        live_eval_recipient_allowlist=[RECIPIENT],
        expected_manifest_path=MAN,
        expected_candidates_path=CAND,
        expected_human_review_path=REV,
    )
    assert ok.valid

    bad = dict(example)
    bad["ai_mode"] = "live_llm"
    art2 = R4ApprovalArtifact(path=Path("x"), payload=bad, artifact_hash="h")
    assert not validate_r4_approval_artifact(
        art2,
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXECUTOR,
        manifest_semantic_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_sha256=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        body_hashes=body_hashes,
        expected_recipient_allowlist=[RECIPIENT],
        live_eval_recipient_allowlist=[RECIPIENT],
    ).valid

    bad2 = dict(example)
    bad2["recipient_allowlist"] = [RECIPIENT, "extra@evil.test"]
    art3 = R4ApprovalArtifact(path=Path("x"), payload=bad2, artifact_hash="h")
    val3 = validate_r4_approval_artifact(
        art3,
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXECUTOR,
        manifest_semantic_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_sha256=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        body_hashes=body_hashes,
        expected_recipient_allowlist=[RECIPIENT],
        live_eval_recipient_allowlist=[RECIPIENT],
    )
    assert not val3.valid
    assert any("recipient" in b for b in val3.blockers)

    bad3 = dict(example)
    bad3["approved_at"] = None
    art4 = R4ApprovalArtifact(path=Path("x"), payload=bad3, artifact_hash="h")
    assert not validate_r4_approval_artifact(
        art4,
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXECUTOR,
        manifest_semantic_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_sha256=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        body_hashes=body_hashes,
        expected_recipient_allowlist=[RECIPIENT],
        live_eval_recipient_allowlist=[RECIPIENT],
    ).valid


def test_unknown_outcome_no_retry_flag(tmp_path, locked, live_cfg, monkeypatch):
    def factory(**kwargs):
        def executor(**kw):
            if "snapshot" not in kw:
                return {"scenario_id": kw["scenario_id"], "status": "passed", "gmail_sends": 0}
            return {
                "scenario_id": kw["scenario_id"],
                "status": "failed",
                "failure_stage": "reply_observation",
                "execution_outcome": "OUTCOME_UNKNOWN",
                "unknown_outcome": True,
                "retry_forbidden": True,
                "gmail_sends": 0,
                "gmail_drafts": 0,
            }

        return executor

    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.run_r4_full_live_jit",
        lambda **kwargs: {"passed": True, "blockers": [], "full_live_jit": True},
    )
    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.build_r4_mailbox_baseline",
        lambda **kwargs: {"passed": True, "blockers": [], "mutations_performed": False},
    )
    ap = _write_valid_approval(tmp_path, locked)
    result = run_r4_live_campaign(
        mode="execute",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        approval_path=ap,
        status_dir=tmp_path,
        recipient=RECIPIENT,
        live_executor_factory=factory,
    )
    assert result["overall_status"] == "partial_campaign_stopped"
    first = result["scenario_outcomes"][0]
    assert first.get("unknown_outcome") is True
    assert first.get("retry_forbidden") is True
    assert result["resume_forbidden"] is True


def test_r4_0088_provenance_in_mock_send(tmp_path, locked, live_cfg, monkeypatch):
    seen = {}

    def factory(**kwargs):
        def executor(**kw):
            if "snapshot" not in kw:
                return {"scenario_id": kw["scenario_id"], "status": "passed", "gmail_sends": 0}
            sid = kw["scenario_id"]
            row = {
                "scenario_id": sid,
                "status": "passed",
                "gmail_sends": 1,
                "gmail_drafts": 0,
                "adapter_provider": "google_mail",
                "reply_provider_message_id_redacted": "aaaa…bbbb",
                "reply_delivery_observed": True,
                "recipient_match": True,
                "thread_match": True,
                "body_hash_match": True,
                "duplicate_count": 0,
                "unknown_outcome": False,
                "approval_executed": True,
            }
            if sid == "PTB-DCQ-0088":
                row["r4_0088_provenance"] = {
                    "base_policy": "hold_for_review",
                    "authorization": "approval_required",
                    "r3_override_reused": False,
                    "stages": [
                        "base_policy_hold",
                        "r4_reviewed_body_materialization",
                        "pending_approval",
                        "explicit_approval",
                        "gmail_execution",
                    ],
                }
                seen["0088"] = row["r4_0088_provenance"]
            return row

        return executor

    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.run_r4_full_live_jit",
        lambda **kwargs: {"passed": True, "blockers": [], "full_live_jit": True},
    )
    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_execution.build_r4_mailbox_baseline",
        lambda **kwargs: {"passed": True, "blockers": [], "mutations_performed": False},
    )
    ap = _write_valid_approval(tmp_path, locked)
    result = run_r4_live_campaign(
        mode="execute",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        expected_executor_sha=EXECUTOR,
        candidates_path=CAND,
        human_review_path=REV,
        manifest_path=MAN,
        approval_path=ap,
        status_dir=tmp_path,
        recipient=RECIPIENT,
        live_executor_factory=factory,
    )
    assert result["overall_status"] == "PASS"
    assert seen["0088"]["r3_override_reused"] is False
    assert seen["0088"]["base_policy"] == "hold_for_review"


def test_build_r4_live_executor_callable_shape(locked, live_cfg, monkeypatch):
    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_live_backend.build_r4_live_backend",
        lambda **kwargs: MagicMock(campaign_id=kwargs["campaign_id"]),
    )
    monkeypatch.setattr(
        "app.evaluation.profile_testbot.qualification.coworker_r4_live_backend._load_scenario_map",
        lambda profile_id=None: {sid: MagicMock(scenario_id=sid, expected_send_behavior="send_after_approval") for sid in R4_SEND_SCENARIO_IDS}
        | {
            sid: MagicMock(scenario_id=sid, expected_send_behavior="no_reply")
            for sid in R4_NO_SEND_SCENARIO_IDS
        },
    )
    from app.evaluation.profile_testbot.qualification.coworker_r4_approval_artifact import (
        R4ApprovalArtifact,
    )

    art = R4ApprovalArtifact(path=Path("a"), payload={"x": 1}, artifact_hash="abc")
    cb = build_r4_live_executor(
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXECUTOR,
        campaign_id="camp",
        approval_artifact=art,
        manifest=locked["manifest"],
        candidates=locked["candidates"],
        human_review=locked["review"],
        recipient=RECIPIENT,
    )
    assert callable(cb)
    assert getattr(cb, "_r4_backend_type") == R4_LIVE_BACKEND_TYPE
