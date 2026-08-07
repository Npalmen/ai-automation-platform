"""Focused tests for authoritative R4 exact registration payloads."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.evaluation.profile_testbot.qualification.coworker_r4_live_backend import (
    _register_r4_live_run,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_live_probes import collect_r4_live_probes
from app.evaluation.profile_testbot.qualification.coworker_r4_registration_payload import (
    build_r4_live_eval_register_request,
    build_r4_registration_context,
    evaluate_exact_r4_registration_payload_matrix,
    r4_registration_campaign_bindings,
    send_registration_fields_from_candidate,
    send_registration_fields_from_snapshot,
    validate_exact_r4_registration_payload,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registration_readiness import (
    evaluate_r4_registration_readiness,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
    R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    R4_NO_SEND_SCENARIO_IDS,
    R4_SEND_SCENARIO_IDS,
    R4_TENANT_ID,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_reviewed_snapshot import (
    R4ReviewedBodySnapshot,
)
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario, ProfileScenarioInput

EXEC = "08e19967666b204b7280dde0378c1988e2cca174"
SENDER = "qvarsken@gmail.com"
RECIPIENT = "niklas.palm@sol-f.se"
WORKTREE = Path(r"C:\ai_automation_platform-r4-mig026-af7e49c")
CAND = Path("storage/status/digital-coworker-r4-candidates-b7fd95e.json")
REV = Path("storage/status/digital-coworker-r4-human-review-scored-b7fd95e.json")
MAN = Path("storage/status/digital-coworker-r4-manifest-b7fd95e.json")


def _artifact_path(local: Path) -> Path:
    if local.is_file():
        return local
    fallback = WORKTREE / local
    return fallback if fallback.is_file() else local


@pytest.fixture
def r4_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", R4_TENANT_ID)
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", SENDER)
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", RECIPIENT)
    monkeypatch.setenv("BUILD_GIT_SHA", EXEC)
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def _synthetic_locked_artifacts() -> tuple[dict, dict]:
    sends = []
    reviews = []
    for sid in R4_SEND_SCENARIO_IDS:
        body = f"{sid.lower()}-body-hash".ljust(64, "0")[:64]
        sends.append(
            {
                "scenario_id": sid,
                "plan_hash": f"plan-{sid}",
                "body_hash": body,
                "renderer_type": "constrained_llm_v1",
                "model_id": "gpt-4o-mini-2024-07-18",
                "prompt_version": "coworker_constrained_llm_v5",
            }
        )
        reviews.append(
            {
                "scenario_id": sid,
                "review_status": "PASS",
                "body_hash": body,
                "bound_body_hash": body,
            }
        )
    candidates = {
        "send_candidates": sends,
        "manifest_semantic_hash": R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        "candidate_package_semantic_hash": R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
    }
    human_review = {"reviews": reviews}
    return candidates, human_review


def _bindings(campaign_id: str | None = None):
    return r4_registration_campaign_bindings(
        campaign_id=campaign_id or str(uuid4()),
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXEC,
        expected_sender=SENDER,
        expected_recipient=RECIPIENT,
    )


def test_e1_send_payload_builder_includes_registration_context(r4_env):
    bindings = _bindings()
    fields = send_registration_fields_from_candidate(
        {
            "plan_hash": "plan-0000",
            "body_hash": "a" * 64,
            "renderer_type": "constrained_llm_v1",
            "model_id": "gpt-4o-mini-2024-07-18",
            "prompt_version": "coworker_constrained_llm_v5",
        },
        {"review_status": "PASS"},
    )
    request = build_r4_live_eval_register_request(
        bindings,
        scenario_id="PTB-DCQ-0000",
        evaluation_run_id=str(uuid4()),
        planned_gmail_send=True,
        send_fields=fields,
    )
    row = validate_exact_r4_registration_payload(request)
    assert row["registration_context_present"] is True
    assert row["planned_gmail_send"] is True
    assert row["passed"] is True


def test_e2_no_send_payload_omits_send_fields(r4_env):
    bindings = _bindings()
    request = build_r4_live_eval_register_request(
        bindings,
        scenario_id=R4_NO_SEND_SCENARIO_IDS[0],
        evaluation_run_id=str(uuid4()),
        planned_gmail_send=False,
    )
    ctx = request.registration_context
    assert ctx is not None
    assert ctx.planned_gmail_send is False
    assert ctx.reviewed_body_hash is None
    row = validate_exact_r4_registration_payload(request)
    assert row["passed"] is True


def test_e3_exact_matrix_20_20_and_16_16(r4_env):
    candidates, human_review = _synthetic_locked_artifacts()
    matrix = evaluate_exact_r4_registration_payload_matrix(
        bindings=_bindings(),
        candidates=candidates,
        human_review=human_review,
    )
    assert matrix["exact_send_registration_payload_ready"] == "20/20"
    assert matrix["exact_no_send_registration_payload_ready"] == "16/16"
    assert matrix["passed"] is True


def test_e4_sequential_0000_and_0002_payloads_both_pass(r4_env):
    candidates, human_review = _synthetic_locked_artifacts()
    bindings = _bindings()
    cand_by_id = {c["scenario_id"]: c for c in candidates["send_candidates"]}
    review_by_id = {r["scenario_id"]: r for r in human_review["reviews"]}
    for sid in ("PTB-DCQ-0000", "PTB-DCQ-0002"):
        fields = send_registration_fields_from_candidate(
            cand_by_id[sid],
            review_by_id[sid],
        )
        request = build_r4_live_eval_register_request(
            bindings,
            scenario_id=sid,
            evaluation_run_id=str(uuid4()),
            planned_gmail_send=True,
            send_fields=fields,
        )
        assert validate_exact_r4_registration_payload(request)["passed"] is True


def test_e5_no_send_registration_uses_planned_gmail_send_false(r4_env, monkeypatch):
    backend = MagicMock()
    backend.config = __import__(
        "app.evaluation.live.config", fromlist=["get_live_eval_config"]
    ).get_live_eval_config()
    backend.observer = MagicMock()
    scenario = ProfileScenario(
        scenario_id=R4_NO_SEND_SCENARIO_IDS[0],
        profile_id="niklas-demo-live-eval-v1",
        profile_snapshot_hash="hash",
        family="solar",
        intent="reply",
        risk_class="low",
        input=ProfileScenarioInput(
            subject="test",
            message_text="body",
            sender_name="Test",
            sender_email=SENDER,
        ),
        expected_classification={},
        expected_route={},
        expected_authorization={},
        expected_send_behavior="no_reply",
    )
    _register_r4_live_run(
        backend,
        campaign_bindings=_bindings(),
        scenario=scenario,
        evaluation_run_id=str(uuid4()),
        attempt_id=1,
        planned_gmail_send=False,
    )
    payload = backend.observer.register_run.call_args[0][0]
    assert payload["registration_context"]["planned_gmail_send"] is False


def test_e6_sender_allowlist_binding_blocks_mismatch(r4_env):
    bindings = r4_registration_campaign_bindings(
        campaign_id=str(uuid4()),
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXEC,
        expected_sender="not-in-allowlist@example.com",
        expected_recipient=RECIPIENT,
    )
    request = build_r4_live_eval_register_request(
        bindings,
        scenario_id=R4_NO_SEND_SCENARIO_IDS[0],
        evaluation_run_id=str(uuid4()),
        planned_gmail_send=False,
    )
    row = validate_exact_r4_registration_payload(request)
    assert row["sender_allowlisted"] is False
    assert row["passed"] is False


def test_e7_jit_and_probes_require_exact_matrix_not_manifest_only(r4_env, monkeypatch):
    candidates, human_review = _synthetic_locked_artifacts()
    manifest = {
        "campaign_type": "coworker_r4_live_quality_campaign",
        "execution_mode": "r4_reviewed_live_candidate",
        "tenant_id": R4_TENANT_ID,
        "manifest_semantic_hash": R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    }

    with patch(
        "app.evaluation.profile_testbot.qualification.coworker_r4_live_probes.run_sender_readiness_read_only",
        return_value=MagicMock(ready=True, issues=[], profile_email=SENDER),
    ), patch(
        "app.evaluation.profile_testbot.qualification.coworker_r4_live_probes.run_recipient_gmail_readiness",
        return_value=MagicMock(
            ready=True,
            blockers=[],
            delivery_observation_path_ready=True,
            recipient_credential_source="live_eval_recipient_env",
            to_dict=lambda: {},
        ),
    ), patch(
        "app.evaluation.profile_testbot.qualification.coworker_r4_live_probes.run_r3_live_reply_provider_readiness",
        return_value={
            "reply_provider_ready": True,
            "reply_provider_source": "live_eval_recipient_env",
            "stub_fallback_possible": False,
        },
    ), patch(
        "app.repositories.postgres.database.SessionLocal"
    ) as session_local, patch(
        "app.evaluation.profile_testbot.qualification.coworker_r4_live_probes.run_r3_tenant_intake_readiness",
        return_value=MagicMock(tenant_intake_ready=True, blockers=[], to_dict=lambda: {}),
    ), patch(
        "app.evaluation.profile_testbot.qualification.coworker_r4_live_probes.evaluate_eval_stack_runtime_sha",
        return_value={
            "api_runtime_sha": EXEC,
            "worker_runtime_sha": EXEC,
            "blocking_failures": [],
            "live_execution_blockers": [],
        },
    ):
        session_local.return_value.__enter__ = lambda s: MagicMock()
        session_local.return_value.__exit__ = lambda s, *a: None
        probes = collect_r4_live_probes(
            executor_runtime_sha=EXEC,
            manifest=manifest,
            candidates=candidates,
            human_review=human_review,
        )
        assert probes["exact_registration_payload_ready"] is True
        assert probes["registration_contract_ready"] is True

    readiness = evaluate_r4_registration_readiness(
        executor_runtime_sha=EXEC,
        candidates=candidates,
        human_review=human_review,
    )
    assert readiness["exact_registration_payload_ready"] == "36/36"
    assert readiness["passed"] is True


@pytest.mark.skipif(
    not _artifact_path(CAND).is_file()
    or not _artifact_path(REV).is_file()
    or not _artifact_path(MAN).is_file(),
    reason="locked R4 artifacts required",
)
def test_locked_artifacts_exact_matrix_passes(r4_env):
    candidates = json.loads(_artifact_path(CAND).read_text(encoding="utf-8"))
    human_review = json.loads(_artifact_path(REV).read_text(encoding="utf-8"))
    matrix = evaluate_exact_r4_registration_payload_matrix(
        bindings=_bindings(),
        candidates=candidates,
        human_review=human_review,
    )
    assert matrix["passed"] is True


def test_snapshot_fields_match_execute_registration(r4_env):
    snapshot = R4ReviewedBodySnapshot(
        campaign_type="coworker_r4_live_quality_campaign",
        execution_mode="r4_reviewed_live_candidate",
        scenario_id="PTB-DCQ-0000",
        candidate_runtime_sha=R4_LOCKED_CANDIDATE_RUNTIME_SHA,
        executor_runtime_sha=EXEC,
        manifest_semantic_hash=R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_artifact_hash="7" * 64,
        plan_hash="plan-0000",
        reviewed_body="hello",
        reviewed_body_hash="a" * 64,
        review_status="PASS",
        renderer_type="constrained_llm_v1",
        model_id="gpt-4o-mini-2024-07-18",
        prompt_version="coworker_constrained_llm_v5",
        recipient=RECIPIENT,
        campaign_id="camp",
        evaluation_run_id="run",
    )
    fields = send_registration_fields_from_snapshot(snapshot)
    ctx = build_r4_registration_context(
        _bindings(),
        scenario_id="PTB-DCQ-0000",
        planned_gmail_send=True,
        send_fields=fields,
    )
    assert ctx.reviewed_body_hash == snapshot.reviewed_body_hash
    assert ctx.plan_hash == snapshot.plan_hash
