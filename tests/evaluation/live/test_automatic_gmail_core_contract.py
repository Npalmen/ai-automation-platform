"""Automatic Gmail core campaign contract and membership tests."""

from __future__ import annotations

import pytest

from app.evaluation.live.campaign.automatic_action_contract import (
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS,
)
from app.evaluation.live.campaign.automatic_action_contract_core import (
    AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE,
    AUTOMATIC_GMAIL_CORE_HOLD_SCENARIO_IDS,
    AUTOMATIC_GMAIL_CORE_POSITIVE_SCENARIO_IDS,
    AUTOMATIC_GMAIL_CORE_SCENARIO_IDS,
    AUTOMATIC_GMAIL_CORE_WORKFLOW_CONFIRMATION,
    AutomaticCampaignNotQualified,
    validate_automatic_core_campaign_budgets,
    validate_automatic_core_campaign_qualification,
)
from app.evaluation.live.campaign.automatic_fixture_completeness import (
    validate_automatic_fixture_bundle_completeness,
)
from app.evaluation.live.campaign.registry import (
    clear_campaign_registry_cache,
    get_scenario_campaign_membership,
    scenario_belongs_to_campaign,
)
from app.evaluation.live.campaign.scenario_budget import build_selected_scenario_budget
from app.evaluation.live.errors import LiveEvalSafetyError
from app.workflows.action_authorization import ActionAuthorization, authorize_action
from app.workflows.intelligence_safety import assess_content_risk
from app.workflows.reply_candidate_safety import assess_reply_candidate_safety


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    clear_campaign_registry_cache()


def test_core_manifest_has_exact_eight_scenarios():
    assert AUTOMATIC_GMAIL_CORE_SCENARIO_IDS == (
        "TBA01_safe_lead_auto_reply",
        "TBA02_unknown_auto_hold",
        "TBA03_safe_general_inquiry_auto_reply",
        "TBA04_noisy_lead_auto_reply",
        "TBA05_invoice_auto_hold",
        "TBA06_support_complaint_auto_hold",
        "TBA07_price_booking_commitment_hold",
        "TBA08_sensitive_safety_hold",
    )


def test_positive_and_hold_sets():
    assert AUTOMATIC_GMAIL_CORE_POSITIVE_SCENARIO_IDS == frozenset({
        "TBA01_safe_lead_auto_reply",
        "TBA03_safe_general_inquiry_auto_reply",
        "TBA04_noisy_lead_auto_reply",
    })
    assert AUTOMATIC_GMAIL_CORE_HOLD_SCENARIO_IDS == frozenset({
        "TBA02_unknown_auto_hold",
        "TBA05_invoice_auto_hold",
        "TBA06_support_complaint_auto_hold",
        "TBA07_price_booking_commitment_hold",
        "TBA08_sensitive_safety_hold",
    })


def test_core_budget_is_8_3_0():
    issues, matrix = validate_automatic_core_campaign_budgets()
    assert issues == []
    assert matrix["inbound_send_budget"] == 8
    assert matrix["expected_reply_count"] == 3
    assert matrix["non_gmail_write_budget"] == 0


def test_tba01_tba02_belong_to_both_campaigns():
    for scenario_id in ("TBA01_safe_lead_auto_reply", "TBA02_unknown_auto_hold"):
        membership = get_scenario_campaign_membership(scenario_id)
        assert AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE in membership
        assert AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE in membership


def test_e1_budget_remains_2_1():
    budget = build_selected_scenario_budget(
        campaign_type=AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
        selected_scenario_ids=AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS,
    )
    assert budget.inbound_send_budget == 2
    assert budget.expected_reply_count == 1


def test_unregistered_campaign_rejects_scenario():
    with pytest.raises(LiveEvalSafetyError):
        build_selected_scenario_budget(
            campaign_type="observe-core",
            selected_scenario_ids=("TBA01_safe_lead_auto_reply",),
        )


def test_fixture_completeness_passes_for_core_manifest():
    issues, matrix = validate_automatic_fixture_bundle_completeness(
        campaign_type=AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE,
    )
    assert issues == []
    assert matrix["complete"] is True


def test_wrong_core_workflow_confirmation_raises():
    with pytest.raises(AutomaticCampaignNotQualified):
        validate_automatic_core_campaign_qualification(
            campaign_type=AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE,
            workflow_confirmation="RUN_AUTOMATIC_GMAIL_CANARY",
            scenario_ids=AUTOMATIC_GMAIL_CORE_SCENARIO_IDS,
        )


def test_tba06_complaint_inbound_risk_holds_despite_customer_inquiry_eligibility():
    risk = assess_content_risk({
        "subject": "Missnöjd",
        "message_text": "Jag är riktigt missnöjd med arbetet",
    })
    assert risk["risk_detected"] is True
    assert "complaint" in risk["categories"]


def test_tba07_commitment_inbound_risk_holds_despite_lead_eligibility():
    risk = assess_content_risk({
        "subject": "Offert",
        "message_text": "Vad kostar det och kan ni boka tid nästa vecka?",
    })
    assert risk["risk_detected"] is True
    assert "commitment_request" in risk["categories"]


def test_reply_safety_blocks_price_and_accepts_neutral_ack():
    unsafe = assess_reply_candidate_safety("Priset är 15000 kr inklusive installation.")
    assert unsafe["passed"] is False
    assert "concrete_price" in unsafe["violations"]

    safe = assess_reply_candidate_safety(
        "Hej,\n\nTack för ditt meddelande. Vi har mottagit din förfrågan och återkommer.\n"
    )
    assert safe["passed"] is True


def test_authorization_requires_reply_safety_pass_for_auto_execute():
    assert (
        authorize_action(
            "send_customer_auto_reply",
            job_type="lead",
            auto_actions={"lead": "auto"},
            risk_detected=False,
            policy_decision="auto_execute",
            reply_safety_passed=False,
        )
        == ActionAuthorization.BLOCKED
    )
    assert (
        authorize_action(
            "send_customer_auto_reply",
            job_type="lead",
            auto_actions={"lead": "auto"},
            risk_detected=False,
            policy_decision="auto_execute",
            reply_safety_passed=True,
        )
        == ActionAuthorization.EXECUTION_ALLOWED
    )


def test_scenario_belongs_to_core_only_for_registered_ids():
    assert scenario_belongs_to_campaign("TBA03_safe_general_inquiry_auto_reply", AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE)
    assert not scenario_belongs_to_campaign("TBS01_lead_observe", AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE)


def test_core_qualification_requires_exact_confirmation():
    assert validate_automatic_core_campaign_qualification(
        campaign_type=AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE,
        workflow_confirmation=AUTOMATIC_GMAIL_CORE_WORKFLOW_CONFIRMATION,
        scenario_ids=AUTOMATIC_GMAIL_CORE_SCENARIO_IDS,
        raise_on_failure=False,
    ) == []
