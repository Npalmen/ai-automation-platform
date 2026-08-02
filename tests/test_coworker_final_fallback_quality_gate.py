"""Final fallback quality gate: complaint/warranty deterministic fallback closure."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.profile_testbot.coworker_quality_oracles import evaluate_coworker_reply_oracles
from app.evaluation.profile_testbot.coworker_reply_dataset import generate_coworker_reply_dataset
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.coworker_package_precheck import evaluate_package_precheck
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import _render_scenario_reply
from app.workflows.reply_quality.final_text_validation import validate_stage
from app.workflows.reply_quality.llm_renderer import compose_constrained_reply_hermetic
from app.workflows.reply_quality.post_render_validator import validate_post_render_reply
from app.workflows.reply_quality.question_surface_composition import compose_customer_question_block
from app.workflows.reply_quality.renderer import render_coworker_reply_with_validation
from tests.test_coworker_fallback_regressions import _plan_for

BAD_9B041F0_FALLBACK = (
    "Kan du skicka orderreferens eller ursprungligt ärende, "
    "bilder eller dokument som stödjer ärendet och om felet kan påverka säkerheten?"
)

BLOCKER_SCENARIOS = ("PTB-DCQ-0088", "PTB-DCQ-0090")


def _scenario(scenario_id: str):
    profile = load_customer_profile("niklas-demo-live-eval-v1")
    scenarios = generate_coworker_reply_dataset(profile, seed=0)
    return next(s for s in scenarios if s.scenario_id == scenario_id)


@pytest.mark.parametrize("scenario_id", BLOCKER_SCENARIOS)
def test_9b041f0_bad_fallback_fails_validator(scenario_id: str):
    plan = _plan_for(scenario_id)
    validation = validate_post_render_reply(plan=plan, body=f"Hej,\n\n{plan.acknowledgement_statement}\n\n{BAD_9B041F0_FALLBACK}\n\n{plan.next_step_statement}")
    assert not validation["passed"]
    grammar = [i for i in validation["issues"] if i.startswith("grammatical_question_composition:")]
    assert grammar


def test_9b041f0_bad_fallback_fails_final_gate_oracle():
    plan = _plan_for("PTB-DCQ-0088")
    body = f"Hej,\n\n{plan.acknowledgement_statement}\n\n{BAD_9B041F0_FALLBACK}\n\n{plan.next_step_statement}"
    final = validate_stage(plan=plan, body=body, validation_stage="final_customer_text")
    scenario = _scenario("PTB-DCQ-0088")
    results = evaluate_coworker_reply_oracles(
        scenario=scenario,
        reply_body=body,
        plan_v2=plan,
        provenance=None,
        render_validation={"final_customer_text_validation": final},
    )
    by_name = {r.name: r for r in results}
    assert by_name["final_customer_text_validation"].status == "fail"
    assert by_name["grammatical_question_composition"].status == "fail"
    assert by_name["natural_surface_text"].status == "fail"


def test_safety_relevance_is_separate_question():
    block = compose_customer_question_block(
        ("original_case", "evidence", "safety_relevance"),
        (
            "orderreferens eller ursprungligt ärende",
            "bilder eller dokument som stödjer ärendet",
            "om felet kan påverka säkerheten",
        ),
        language="sv",
        register="du",
    )
    assert "skicka" in block.lower()
    assert "meddela också om felet kan påverka säkerheten" in block.lower()
    assert "och om felet" not in block.lower()


@pytest.mark.parametrize("scenario_id", BLOCKER_SCENARIOS)
def test_deterministic_fallback_passes_validator(scenario_id: str):
    plan = _plan_for(scenario_id)
    body = compose_constrained_reply_hermetic(plan)
    validation = validate_post_render_reply(plan=plan, body=body)
    assert validation["passed"], validation["issues"]
    assert "och om felet" not in body.lower()


@pytest.mark.parametrize("scenario_id", BLOCKER_SCENARIOS)
def test_raw_llm_fail_then_fallback_passes(scenario_id: str, monkeypatch):
    monkeypatch.setenv("DIGITAL_COWORKER_LLM_RENDER", "live")
    plan = _plan_for(scenario_id)
    bad_llm = (
        "Hej,\n\nTack för att du kontaktar oss om reklamationen. "
        "För att vi ska kunna hjälpa dig behöver vi vilken typ av fastighet det gäller?\n\n"
        "När vi har underlaget gör vi en teknisk bedömning.\n\nVänliga hälsningar\nNiklas"
    )
    with patch("app.ai.llm.client.get_llm_client") as mock_get:
        mock_get.return_value.generate_json_detailed.return_value = MagicMock(
            output={"reply_body": bad_llm},
            returned_model="gpt-4o-mini",
            usage={},
            finish_reason="stop",
        )
        result = render_coworker_reply_with_validation(plan)
    assert result.provenance.use_fallback is True
    assert result.validation["final_customer_text_validation"]["passed"] is True
    assert "och om felet" not in result.body.lower()
    assert result.body


def test_invalid_final_body_fails_package_precheck():
    kwargs = dict(
        scenario_pass=[True, False],
        bodies=["good body", BAD_9B041F0_FALLBACK],
        families=["complaint_warranty", "complaint_warranty"],
        thread_states=["new_thread", "new_thread"],
        use_fallback=[False, True],
        llm_used=[True, False],
        invocation_attempted=[True, True],
        provider_outcomes=["success", "success"],
        live_validation_outcomes=["pass", "fail"],
        aggregation_consistent=[True, True],
        final_customer_text_pass=[True, False],
        final_customer_text_validator_failures=1,
    )
    result = evaluate_package_precheck(**kwargs)
    assert result.package_precheck_pass is False
    assert result.final_customer_text_validator_failures == 1


def test_valid_final_body_passes_package_precheck_despite_fallback():
    kwargs = dict(
        scenario_pass=[True] * 40,
        bodies=[f"unique complaint reply {i}" for i in range(40)],
        families=[f"family_{i % 8}" for i in range(40)],
        thread_states=["new_thread"] * 40,
        use_fallback=[False] * 35 + [True] * 5,
        llm_used=[True] * 35 + [False] * 5,
        invocation_attempted=[True] * 40,
        provider_outcomes=["success"] * 40,
        live_validation_outcomes=(["pass"] * 35 + ["fail"] * 5),
        aggregation_consistent=[True] * 40,
        final_customer_text_pass=[True] * 40,
        raw_llm_validator_failures=5,
        deterministic_fallback_count=5,
        fallback_validator_failures=0,
        final_customer_text_validator_failures=0,
    )
    result = evaluate_package_precheck(**kwargs)
    assert result.final_customer_text_pass is True
    assert result.fallback_rate_pass is True
