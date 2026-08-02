"""Tests for inbox quality qualification (Todo J)."""

from __future__ import annotations

import pytest

from app.evaluation.profile_testbot.constants import (
    QUALIFICATION_AUTOMATIC,
    QUALIFICATION_PASS,
    QUALIFICATION_SEMI_AUTO,
    QUALIFICATION_SEMI_AUTO_QUALITY,
)
from app.evaluation.profile_testbot.qualification.constants import (
    LIVE_QUALITY_CAMPAIGN_SEND_MAX,
    LIVE_QUALITY_CAMPAIGN_TARGET,
    LIVE_QUALITY_CANARY_HOLD_MIN,
    LIVE_QUALITY_CANARY_SEND_MAX,
    LIVE_QUALITY_CANARY_TARGET,
    PTB_SEM_0024_SCENARIO_ID,
)
from app.evaluation.profile_testbot.qualification.hermetic_quality import (
    run_hermetic_quality_qualification,
)
from app.evaluation.profile_testbot.qualification.live_canary_manifest import (
    LIVE_QUALITY_CANARY_MANIFEST_HASH,
    LIVE_QUALITY_CANARY_SCENARIO_IDS,
    build_live_quality_canary_manifest,
    validate_live_quality_canary_budget,
)
from app.evaluation.profile_testbot.qualification.live_campaign_manifest import (
    LIVE_QUALITY_CAMPAIGN_MANIFEST_HASH,
    LIVE_QUALITY_CAMPAIGN_SCENARIO_IDS,
    build_live_quality_campaign_manifest,
    validate_live_quality_campaign_budget,
)
from app.evaluation.regression.qualification_registry import (
    qualification_index,
    validate_qualification_registry,
)
from app.evaluation.profile_testbot.campaign.quality_live_runner import _customer_draft_created


class TestCustomerDraftCreatedOracle:
    def test_hold_ignores_pending_without_customer_draft_text(self):
        scenario = type("S", (), {"expected_send_behavior": "hold"})()
        assert _customer_draft_created(
            scenario=scenario, approval_state="pending", draft_text=""
        ) is False

    def test_hold_detects_customer_draft_text(self):
        scenario = type("S", (), {"expected_send_behavior": "hold"})()
        assert _customer_draft_created(
            scenario=scenario, approval_state="none", draft_text="Hej,"
        ) is True

    def test_send_after_approval_counts_pending_without_body(self):
        scenario = type("S", (), {"expected_send_behavior": "send_after_approval"})()
        assert _customer_draft_created(
            scenario=scenario, approval_state="pending", draft_text=""
        ) is True


class TestQualificationRegistry:
    def test_registry_valid_with_quality_qualification(self):
        failures = validate_qualification_registry()
        assert failures == [], failures

    def test_quality_qualification_valid(self):
        entry = qualification_index()[QUALIFICATION_SEMI_AUTO_QUALITY]
        assert entry["status"] == "VALID"
        assert entry["source_sha"] == "128aacee5567d4d8ed762e25192c766494e7b634"
        assert entry["contract_version"] == "inbox_quality_hermetic_v1"

    def test_automatic_qualifications_remain_pending(self):
        quals = qualification_index()
        assert quals[QUALIFICATION_AUTOMATIC]["status"] == "PENDING"
        assert quals[QUALIFICATION_PASS]["status"] == "PENDING"

    def test_semi_auto_gmail_still_valid(self):
        assert qualification_index()[QUALIFICATION_SEMI_AUTO]["status"] == "VALID"


class TestHermeticQualityQualification:
    def test_hermetic_qualification_passes(self):
        result = run_hermetic_quality_qualification(profile_id="pilot-service-company-v1", seed=0)
        assert result.overall_status == "PASS"
        assert result.scenario_count == 96
        assert result.hard_safety_pass_rate == 1.0
        assert result.ptb_sem_0024_pass is True
        assert result.gate_failures == []

    def test_ptb_sem_0024_blocking(self):
        result = run_hermetic_quality_qualification()
        assert result.ptb_sem_0024_pass
        assert PTB_SEM_0024_SCENARIO_ID in result.ptb_sem_0024_detail or result.ptb_sem_0024_pass


class TestLiveQualityCanaryManifest:
    def test_locked_scenario_count(self):
        assert len(LIVE_QUALITY_CANARY_SCENARIO_IDS) == LIVE_QUALITY_CANARY_TARGET

    def test_manifest_builds(self):
        manifest = build_live_quality_canary_manifest()
        assert manifest.scenario_count == LIVE_QUALITY_CANARY_TARGET
        assert manifest.send_budget <= LIVE_QUALITY_CANARY_SEND_MAX
        assert manifest.hold_reject_no_reply_count >= LIVE_QUALITY_CANARY_HOLD_MIN
        assert manifest.has_thread_fixture
        assert manifest.has_duplicate_fixture
        assert manifest.has_adversarial_no_send
        assert manifest.manifest_hash == LIVE_QUALITY_CANARY_MANIFEST_HASH

    def test_ptb_sem_0024_in_canary(self):
        manifest = build_live_quality_canary_manifest()
        assert PTB_SEM_0024_SCENARIO_ID in manifest.scenario_ids

    def test_quality_live_execution_blocked_until_valid(self, monkeypatch):
        from app.evaluation.profile_testbot.campaign.readiness import (
            _live_quality_execution_blockers,
        )

        monkeypatch.delenv("PROFILE_TESTBOT_LIVE_QUALITY_APPROVED", raising=False)
        blockers = _live_quality_execution_blockers(
            ready=True,
            live_blockers=[],
            quality_qualification_status="PENDING",
            hermetic_quality_pass=True,
        )
        assert any("PROFILE_TESTBOT_LIVE_QUALITY_APPROVED" in item for item in blockers)

        monkeypatch.setenv("PROFILE_TESTBOT_LIVE_QUALITY_APPROVED", "yes")
        blockers_valid = _live_quality_execution_blockers(
            ready=True,
            live_blockers=[],
            quality_qualification_status="VALID",
            hermetic_quality_pass=True,
        )
        assert any("re-qualification" in item for item in blockers_valid)


class TestLiveQualityCampaignManifest:
    def test_locked_scenario_count(self):
        assert len(LIVE_QUALITY_CAMPAIGN_SCENARIO_IDS) == LIVE_QUALITY_CAMPAIGN_TARGET

    def test_manifest_builds(self):
        manifest = build_live_quality_campaign_manifest()
        assert manifest.scenario_count == LIVE_QUALITY_CAMPAIGN_TARGET
        assert manifest.send_budget <= LIVE_QUALITY_CAMPAIGN_SEND_MAX
        assert len(manifest.family_distribution) >= 12
        assert manifest.manifest_hash == LIVE_QUALITY_CAMPAIGN_MANIFEST_HASH

    def test_budget_validation_passes(self):
        manifest = build_live_quality_campaign_manifest()
        issues = validate_live_quality_campaign_budget(manifest.scenarios)
        assert issues == []
