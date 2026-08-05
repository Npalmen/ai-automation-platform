"""Focused tests for strict R4 constrained-LLM candidate generation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.profile_testbot.qualification.coworker_r4_candidates import (
    build_candidate_package_semantic_payload,
    compute_candidate_package_semantic_hash,
    generate_r4_candidates,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_execution import (
    run_r4_live_campaign,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_human_review import (
    build_r4_human_review_package,
    evaluate_r4_human_review_authorization,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_llm_readiness import (
    run_r4_constrained_llm_readiness,
)
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import (
    _render_scenario_reply,
)
from app.workflows.reply_quality.llm_renderer import (
    MODEL_ID,
    PROMPT_VERSION,
    RENDERER_POLICY_VERSION,
    compose_constrained_reply_hermetic,
)
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.provenance import DETERMINISTIC_RENDERER, LLM_RENDERER, hash_body
from app.workflows.reply_quality.renderer import render_coworker_reply_with_validation
from app.workflows.reply_quality.renderer_requirement import RendererRequirement
from app.workflows.reply_quality.thread_context import ThreadReplyContext


RUNTIME = "7a445ad582e5e2ebd060e55c890eb7fd402286fc"


def _minimal_plan(**overrides) -> CustomerReplyPlanV2:
    base = dict(
        response_objective="collect_missing_facts",
        acknowledgement_mode="safe_ack",
        service_family="lead",
        business_intent="lead",
        verified_facts=(),
        facts_not_allowed_to_repeat=(),
        selected_questions=("roof_type",),
        selected_question_labels=("taktyp",),
        next_step_statement="När vi har underlaget återkommer vi.",
        commitment_constraints=(),
        tone_profile="professional",
        language="sv",
        greeting="Hej,",
        signature_name="Niklas",
        salutation_strategy="ni",
        closing_strategy="vänliga",
        thread_context=ThreadReplyContext(
            thread_state="new_thread",
            is_first_contact=True,
            is_continuation=False,
            prior_operator_reply=False,
            prior_safe_ack=False,
            supplied_facts=(),
            summary="",
            policy_version="thread_context_v1",
        ),
        rendering_constraints=(),
        fallback_reason=None,
        evidence=(),
        playbook_id="lead_v1",
        policy_version="customer_reply_plan_v3",
        acknowledgement_statement="Tack för er förfrågan om solceller.",
        question_surface_labels=("taktyp",),
    )
    base.update(overrides)
    return CustomerReplyPlanV2(**base)


def _success_meta(plan: CustomerReplyPlanV2) -> dict:
    return {
        "prompt_version": PROMPT_VERSION,
        "model_id": MODEL_ID,
        "requested_model_id": MODEL_ID,
        "template_version": "digital_coworker_constrained_llm_v5",
        "renderer_policy_version": RENDERER_POLICY_VERSION,
        "invocation_attempted": True,
        "live_call": True,
        "provider_outcome": "success",
        "returned_model": "gpt-4o-mini-2024-07-18",
        "returned_model_id": "gpt-4o-mini-2024-07-18",
        "finish_reason": "stop",
        "prompt_tokens": 11,
        "completion_tokens": 22,
        "total_tokens": 33,
        "provider_attempt_count": 1,
        "prompt_payload_hash": "abc123",
        "payload_hash": "abc123",
        "require_live": True,
        "fallback_used": False,
        "fallback_tier": "none",
    }


def _mock_live_success(plan, **kwargs):
    body = compose_constrained_reply_hermetic(plan)
    return body, _success_meta(plan)


@pytest.fixture
def llm_ready_env(monkeypatch):
    monkeypatch.setenv("DIGITAL_COWORKER_LLM_RENDER", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")
    monkeypatch.setenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "2")


def test_require_live_llm_false_blocks_package(llm_ready_env):
    result = generate_r4_candidates(runtime_sha=RUNTIME, require_live_llm=False)
    assert result["overall_status"] == "BLOCKED"
    assert any("require_live_llm" in str(b) for b in result["blocking_failures"])
    assert result["provenance_audit_pass"] is False


def test_llm_render_disabled_blocks(monkeypatch):
    monkeypatch.delenv("DIGITAL_COWORKER_LLM_RENDER", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-real")
    result = generate_r4_candidates(runtime_sha=RUNTIME, require_live_llm=True)
    assert result["overall_status"] == "BLOCKED"
    assert result["llm_readiness"]["constrained_llm_ready"] is False


def test_readiness_fails_without_api_key(monkeypatch):
    monkeypatch.setenv("DIGITAL_COWORKER_LLM_RENDER", "true")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with patch(
        "app.evaluation.profile_testbot.qualification.coworker_r4_llm_readiness.get_settings",
        create=True,
    ):
        with patch("app.core.settings.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(LLM_API_KEY="", LLM_API_URL="https://x")
            ready = run_r4_constrained_llm_readiness()
    assert ready["constrained_llm_ready"] is False
    assert "LLM_API_KEY_not_configured" in ready["blockers"]
    assert ready["credentials_configured"] is False


def test_mocked_llm_success_provenance(llm_ready_env):
    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=_mock_live_success,
    ):
        result = render_coworker_reply_with_validation(
            _minimal_plan(),
            requirement=RendererRequirement.CONSTRAINED_LLM_REQUIRED,
        )
    assert result.provenance.renderer_type == LLM_RENDERER
    assert result.provenance.llm_used is True
    assert result.validation["llm_meta"]["invocation_attempted"] is True
    assert result.validation["llm_meta"]["live_call"] is True
    assert result.validation["llm_meta"]["requested_model_id"] == MODEL_ID
    assert result.validation["llm_meta"]["returned_model_id"]
    assert result.provenance.prompt_version == PROMPT_VERSION
    assert result.validation["llm_meta"]["total_tokens"] == 33
    assert result.provenance.body_hash == hash_body(result.body)
    assert result.provenance.plan_hash
    assert result.validation["passed"] is True
    assert result.validation["final_customer_text_validation"]["passed"] is True


def test_provider_failure_blocks_strict(llm_ready_env):
    def fail(plan, **kwargs):
        meta = _success_meta(plan)
        meta.update(
            {
                "provider_outcome": "failed",
                "live_call": True,
                "returned_model_id": None,
                "returned_model": None,
            }
        )
        return "", meta

    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=fail,
    ):
        result = render_coworker_reply_with_validation(
            _minimal_plan(),
            requirement=RendererRequirement.CONSTRAINED_LLM_REQUIRED,
        )
    assert result.body == ""
    assert result.provenance.llm_used is False
    assert result.validation["passed"] is False


def test_parse_failure_blocks_strict(llm_ready_env):
    def fail(plan, **kwargs):
        meta = _success_meta(plan)
        meta["provider_outcome"] = "parse_failed"
        return "", meta

    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=fail,
    ):
        result = render_coworker_reply_with_validation(
            _minimal_plan(),
            requirement=RendererRequirement.CONSTRAINED_LLM_REQUIRED,
        )
    assert result.body == ""
    assert "parse_failed" in str(result.validation.get("blockers"))


def test_post_render_failure_blocks_strict(llm_ready_env):
    def bad(plan, **kwargs):
        meta = _success_meta(plan)
        return "Hej,\n\nni and du mixed badly without next step", meta

    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=bad,
    ):
        result = render_coworker_reply_with_validation(
            _minimal_plan(),
            requirement=RendererRequirement.CONSTRAINED_LLM_REQUIRED,
        )
    assert result.body == ""
    assert result.validation["passed"] is False


def test_strict_rejects_deterministic_fallback(llm_ready_env, monkeypatch):
    monkeypatch.delenv("DIGITAL_COWORKER_LLM_RENDER", raising=False)

    def hermetic_only(plan, **kwargs):
        body = compose_constrained_reply_hermetic(plan)
        meta = _success_meta(plan)
        meta.update(
            {
                "provider_outcome": "skipped",
                "live_call": False,
                "invocation_attempted": False,
                "returned_model_id": None,
            }
        )
        return body, meta

    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=hermetic_only,
    ):
        result = render_coworker_reply_with_validation(
            _minimal_plan(),
            requirement=RendererRequirement.CONSTRAINED_LLM_REQUIRED,
        )
    assert result.body == ""
    assert result.provenance.renderer_type != LLM_RENDERER


def test_default_path_keeps_deterministic_fallback(monkeypatch):
    monkeypatch.delenv("DIGITAL_COWORKER_LLM_RENDER", raising=False)
    result = render_coworker_reply_with_validation(_minimal_plan())
    assert result.body
    assert result.provenance.renderer_type == DETERMINISTIC_RENDERER
    assert result.provenance.llm_used is False


def test_r1_hermetic_path_unchanged(monkeypatch):
    monkeypatch.delenv("DIGITAL_COWORKER_LLM_RENDER", raising=False)
    from app.evaluation.profile_testbot.coworker_reply_dataset import (
        generate_coworker_reply_dataset,
    )
    from app.evaluation.profile_testbot.profile_contract import load_customer_profile

    profile = load_customer_profile("niklas-demo-live-eval-v1")
    scenarios = generate_coworker_reply_dataset(profile, seed=0)
    body, plan, prov = _render_scenario_reply(scenarios[0])
    assert body
    assert plan is not None
    assert prov is not None
    assert prov.renderer_type == DETERMINISTIC_RENDERER


def test_package_pass_requires_20_constrained(llm_ready_env):
    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=_mock_live_success,
    ):
        result = generate_r4_candidates(runtime_sha=RUNTIME, require_live_llm=True)
    assert result["send_candidate_count"] == 20
    assert result["no_send_candidate_count"] == 16
    assert result["constrained_llm_candidate_count"] == 20
    assert result["deterministic_renderer_count"] == 0
    assert result["fallback_count"] == 0
    assert result["missing_model_id_count"] == 0
    assert result["missing_prompt_version_count"] == 0
    assert result["gmail_sends"] == 0
    assert result["gmail_drafts"] == 0
    assert result["gmail_triggers"] == 0
    assert result["external_writes"] == 0
    assert result["automatic_gmail"] is False
    assert result["production_activation"] is False
    assert result["overall_status"] == "PASS"
    assert result["provenance_audit_pass"] is True
    assert result["candidate_package_semantic_hash"]
    assert result["provider_call_count"] == 20
    for row in result["send_candidates"]:
        assert row["renderer_type"] == LLM_RENDERER
        assert row["llm_used"] is True
        assert row["invocation_attempted"] is True
        assert row["live_call"] is True
        assert row["requested_model_id"] == MODEL_ID
        assert row["returned_model_id"]
        assert row["prompt_version"] == PROMPT_VERSION
        assert row["body_hash"] == hash_body(row["rendered_body"])
        assert row["plan_hash"]
        assert row["post_render_validation_passed"] is True
        assert row["final_text_validation_passed"] is True
        assert row["fallback_used"] is False
    for row in result["no_send_candidates"]:
        assert row.get("llm_calls", 0) == 0
        assert not row.get("rendered_body")


def test_19_of_20_constrained_blocks_package(llm_ready_env):
    calls = {"n": 0}

    def mostly_ok(plan, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            meta = _success_meta(plan)
            meta["provider_outcome"] = "failed"
            return "", meta
        return _mock_live_success(plan, **kwargs)

    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=mostly_ok,
    ):
        result = generate_r4_candidates(runtime_sha=RUNTIME, require_live_llm=True)
    assert result["overall_status"] == "BLOCKED"
    assert result["constrained_llm_candidate_count"] == 19
    assert result["provenance_audit_pass"] is False


def test_missing_model_blocks(llm_ready_env):
    def no_model(plan, **kwargs):
        body, meta = _mock_live_success(plan)
        meta["returned_model_id"] = None
        meta["returned_model"] = None
        return body, meta

    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=no_model,
    ):
        result = generate_r4_candidates(runtime_sha=RUNTIME, require_live_llm=True)
    assert result["overall_status"] == "BLOCKED"
    assert result["missing_model_id_count"] == 20


def test_missing_prompt_version_blocks(llm_ready_env):
    def no_prompt(plan, **kwargs):
        body, meta = _mock_live_success(plan)
        meta["prompt_version"] = None
        return body, meta

    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=no_prompt,
    ):
        # Also force provenance prompt_version empty via failed strict checks
        result = generate_r4_candidates(runtime_sha=RUNTIME, require_live_llm=True)
    assert result["overall_status"] == "BLOCKED"


def test_semantic_hash_stable_and_sensitive(llm_ready_env):
    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=_mock_live_success,
    ):
        a = generate_r4_candidates(runtime_sha=RUNTIME, require_live_llm=True)
        b = generate_r4_candidates(runtime_sha=RUNTIME, require_live_llm=True)
    assert a["candidate_package_semantic_hash"] == b["candidate_package_semantic_hash"]
    # Timestamp must not affect semantic hash payload.
    payload = build_candidate_package_semantic_payload(
        runtime_sha=a["runtime_sha"],
        manifest_semantic_hash=a["manifest_semantic_hash"],
        profile_id=a["profile_id"],
        profile_hash=a["manifest"]["profile_hash"],
        send_candidates=a["send_candidates"],
    )
    assert "generated_at" not in payload
    h1 = compute_candidate_package_semantic_hash(payload)
    assert h1 == a["candidate_package_semantic_hash"]

    changed = list(a["send_candidates"])
    changed[0] = {**changed[0], "body_hash": "deadbeef" * 8}
    h_body = compute_candidate_package_semantic_hash(
        build_candidate_package_semantic_payload(
            runtime_sha=a["runtime_sha"],
            manifest_semantic_hash=a["manifest_semantic_hash"],
            profile_id=a["profile_id"],
            profile_hash=a["manifest"]["profile_hash"],
            send_candidates=changed,
        )
    )
    assert h_body != h1

    changed_model = list(a["send_candidates"])
    changed_model[0] = {**changed_model[0], "returned_model_id": "other-model"}
    h_model = compute_candidate_package_semantic_hash(
        build_candidate_package_semantic_payload(
            runtime_sha=a["runtime_sha"],
            manifest_semantic_hash=a["manifest_semantic_hash"],
            profile_id=a["profile_id"],
            profile_hash=a["manifest"]["profile_hash"],
            send_candidates=changed_model,
        )
    )
    assert h_model != h1


def test_review_package_rejects_non_qualifying(llm_ready_env, monkeypatch):
    monkeypatch.delenv("DIGITAL_COWORKER_LLM_RENDER", raising=False)
    candidates = generate_r4_candidates(runtime_sha=RUNTIME, require_live_llm=True)
    assert candidates["overall_status"] == "BLOCKED"
    auth = evaluate_r4_human_review_authorization(candidates)
    assert auth["human_review_authorized"] is False
    package = build_r4_human_review_package(candidates, runtime_sha=RUNTIME)
    assert package["human_review_authorized"] is False
    assert package["qualification_status"] == "NON_QUALIFYING"
    assert package["send_review_count"] == 0
    assert package["reviews"] == []


def test_review_package_authorized_on_pass(llm_ready_env):
    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=_mock_live_success,
    ):
        candidates = generate_r4_candidates(runtime_sha=RUNTIME, require_live_llm=True)
    package = build_r4_human_review_package(candidates, runtime_sha=RUNTIME)
    assert package["human_review_authorized"] is True
    assert package["send_review_count"] == 20
    assert all(r["review_status"] == "PENDING" for r in package["reviews"])
    assert package["candidate_package_semantic_hash"] == candidates[
        "candidate_package_semantic_hash"
    ]
    for row in package["reviews"]:
        assert row["renderer_provenance"]["renderer_type"] == LLM_RENDERER
        assert row["renderer_provenance"]["returned_model_id"]
        assert row["renderer_provenance"]["prompt_version"] == PROMPT_VERSION


def test_r4_execute_still_blocked_without_review(llm_ready_env, tmp_path):
    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=_mock_live_success,
    ):
        dry = run_r4_live_campaign(
            mode="dry_run",
            expected_runtime_sha=RUNTIME,
            status_dir=tmp_path,
        )
        stopped = run_r4_live_campaign(
            mode="execute",
            expected_runtime_sha=RUNTIME,
            status_dir=tmp_path,
        )
    assert dry["gmail_sends"] == 0
    assert dry["gmail_drafts"] == 0
    assert stopped["overall_status"] == "STOPPED"
    assert stopped["gmail_sends"] == 0



def test_cli_requires_require_live_llm_flag():
    from scripts.build_digital_coworker_r4_candidates import main
    import sys

    with patch.object(sys, "argv", ["prog", "--runtime-sha", RUNTIME]):
        assert main() == 1


def test_no_send_makes_zero_llm_calls(llm_ready_env):
    calls = {"n": 0}

    def counting(plan, **kwargs):
        calls["n"] += 1
        return _mock_live_success(plan, **kwargs)

    with patch(
        "app.workflows.reply_quality.renderer.render_constrained_llm_reply",
        side_effect=counting,
    ):
        result = generate_r4_candidates(runtime_sha=RUNTIME, require_live_llm=True)
    assert calls["n"] == 20
    assert result["provider_call_count"] == 20
    assert result["no_send_candidate_count"] == 16
