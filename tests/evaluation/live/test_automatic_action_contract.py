"""Automatic action contract qualification tests."""

from __future__ import annotations

import pytest

from app.evaluation.live.campaign.automatic_action_contract import (
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS,
    AUTOMATIC_GMAIL_CANARY_WORKFLOW_CONFIRMATION,
    AutomaticCampaignNotQualified,
    validate_automatic_campaign_qualification,
)


def test_valid_qualification_passes():
    assert validate_automatic_campaign_qualification(
        campaign_type=AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
        workflow_confirmation=AUTOMATIC_GMAIL_CANARY_WORKFLOW_CONFIRMATION,
        scenario_ids=AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS,
        raise_on_failure=False,
    ) == []


def test_wrong_campaign_type_raises():
    with pytest.raises(AutomaticCampaignNotQualified, match="automatic_campaign_type_not_qualified"):
        validate_automatic_campaign_qualification(
            campaign_type="semi-auto-core",
            workflow_confirmation=AUTOMATIC_GMAIL_CANARY_WORKFLOW_CONFIRMATION,
            scenario_ids=AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS,
        )


def test_wrong_scenarios_raises():
    with pytest.raises(AutomaticCampaignNotQualified, match="automatic_campaign_type_not_qualified"):
        validate_automatic_campaign_qualification(
            campaign_type=AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
            workflow_confirmation=AUTOMATIC_GMAIL_CANARY_WORKFLOW_CONFIRMATION,
            scenario_ids=("TBSM01_lead_approve_reply",),
        )
