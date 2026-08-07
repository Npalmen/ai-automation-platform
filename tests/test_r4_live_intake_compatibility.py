"""Regression tests for R4 live-trigger intake compatibility (35/35)."""

from __future__ import annotations

from app.evaluation.live.intake_classification_input import (
    evaluate_gmail_intake_classification_gate,
    normalize_intake_classification_inputs,
)
from app.evaluation.profile_testbot.campaign.send_payload import (
    build_profile_testbot_message_body,
    build_profile_testbot_subject,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.coworker_r4_live_intake_compatibility import (
    ATTEMPT9_CAMPAIGN_ID,
    ATTEMPT9_FAILING_EVAL_RUN_ID,
    TERMINAL_AUTHORITATIVE_EXPECTED_SUPPRESSION,
    TERMINAL_PIPELINE_INTAKE_EXPECTED,
    evaluate_r4_live_intake_compatibility_matrix,
    evaluate_r4_live_intake_compatibility_row,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_PROFILE_ID,
    R4_SEND_SCENARIO_IDS,
    resolve_r4_scenarios,
)
from app.workflows.processors.classification_processor import classify_email_type


def _scenario(scenario_id: str):
    profile = load_customer_profile(R4_PROFILE_ID)
    return next(s for s in resolve_r4_scenarios(profile, seed=42) if s.scenario_id == scenario_id)


class TestIntakeClassificationTransportStripping:
    def test_b2b_uuid_in_eval_token_does_not_classify_as_partnership(self):
        scenario = _scenario("PTB-DCQ-0007")
        subject = build_profile_testbot_subject(
            scenario=scenario,
            evaluation_run_id=ATTEMPT9_FAILING_EVAL_RUN_ID,
        )
        body = build_profile_testbot_message_body(
            scenario=scenario,
            evaluation_run_id=ATTEMPT9_FAILING_EVAL_RUN_ID,
            campaign_id=ATTEMPT9_CAMPAIGN_ID,
        )
        assert "b2b" in ATTEMPT9_FAILING_EVAL_RUN_ID
        assert classify_email_type(subject, body) == "partnership"
        gate = evaluate_gmail_intake_classification_gate(subject, body)
        assert gate["proceeds"] is True
        assert gate["inferred_type"] == "lead"

    def test_actual_partnership_message_still_suppressed(self):
        gate = evaluate_gmail_intake_classification_gate(
            "Samarbetsförslag",
            "Vi vill diskutera ett potentiellt samarbete.",
        )
        assert gate["proceeds"] is False
        assert gate["skip_reason"] == "partnership_disabled"

    def test_newsletter_still_suppressed(self):
        gate = evaluate_gmail_intake_classification_gate(
            "Nyhetsbrev",
            "Denna månads kampanjer — avregistrera dig här.",
        )
        assert gate["proceeds"] is False
        assert gate["skip_reason"] == "newsletter_disabled"

    def test_normalize_strips_eval_markers(self):
        subject, body = normalize_intake_classification_inputs(
            "KROWOLF-EVAL/uuid/PTB-DCQ-0007/1 | Solceller fortsättning",
            "<!-- KROWOLF_EVAL:evaluation_run_id=uuid -->\nHej igen, följer upp vår förfrågan om solceller.",
        )
        assert subject == "Solceller fortsättning"
        assert "KROWOLF" not in body


class TestR4LiveIntakeCompatibilityMatrix:
    def test_full_matrix_35_35(self):
        report = evaluate_r4_live_intake_compatibility_matrix()
        assert report["passed"] is True
        assert report["r4_live_intake_compatibility"] == "35/35"
        assert report["blockers"] == []

    def test_ptb_dcq_0007_attempt9_regression(self):
        report = evaluate_r4_live_intake_compatibility_matrix()
        row = report["ptb_dcq_0007_attempt9_regression"]
        assert row["passed"] is True
        assert row["actual_terminal"] == TERMINAL_PIPELINE_INTAKE_EXPECTED

    def test_all_send_scenarios_pipeline_intake_expected(self):
        report = evaluate_r4_live_intake_compatibility_matrix()
        by_id = {row["scenario_id"]: row for row in report["rows"]}
        for sid in R4_SEND_SCENARIO_IDS:
            assert by_id[sid]["actual_terminal"] == TERMINAL_PIPELINE_INTAKE_EXPECTED, sid

    def test_ptb_sem_0023_authoritative_suppression(self):
        report = evaluate_r4_live_intake_compatibility_matrix()
        row = next(r for r in report["rows"] if r["scenario_id"] == "PTB-SEM-0023")
        assert row["actual_terminal"] == TERMINAL_AUTHORITATIVE_EXPECTED_SUPPRESSION
        assert row["skip_reason"] == "newsletter_disabled"

    def test_ptb_dcq_0005_vs_0007_same_terminal(self):
        campaign = "compare-campaign"
        row5 = evaluate_r4_live_intake_compatibility_row(
            scenario=_scenario("PTB-DCQ-0005"),
            campaign_id=campaign,
            evaluation_run_id=ATTEMPT9_FAILING_EVAL_RUN_ID,
        )
        row7 = evaluate_r4_live_intake_compatibility_row(
            scenario=_scenario("PTB-DCQ-0007"),
            campaign_id=campaign,
            evaluation_run_id=ATTEMPT9_FAILING_EVAL_RUN_ID,
        )
        assert row5["actual_terminal"] == TERMINAL_PIPELINE_INTAKE_EXPECTED
        assert row7["actual_terminal"] == TERMINAL_PIPELINE_INTAKE_EXPECTED
