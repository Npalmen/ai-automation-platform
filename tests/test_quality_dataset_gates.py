"""Tests for quality dataset and gates (Todos H-I)."""

from __future__ import annotations

from app.evaluation.profile_testbot.generator.profile_generator import generate_semi_auto_campaign
from app.evaluation.profile_testbot.oracles.quality_result import (
    ORACLE_STATUSES,
    aggregate_quality_score,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.quality_dataset import (
    QUALITY_SCENARIO_TARGET,
    build_quality_manifest,
    generate_quality_dataset,
    validate_quality_dataset_gates,
)
from app.evaluation.profile_testbot.quality_gates import run_quality_campaign
from app.evaluation.profile_testbot.quality_dataset.constants import QUALITY_FAMILY_TARGET


class TestQualityDataset:
    def test_generates_96_scenarios(self):
        profile = load_customer_profile("pilot-service-company-v1")
        scenarios = generate_quality_dataset(profile, seed=0)
        assert len(scenarios) == QUALITY_SCENARIO_TARGET

    def test_family_distribution_balanced(self):
        profile = load_customer_profile("pilot-service-company-v1")
        scenarios = generate_quality_dataset(profile, seed=0)
        gate = validate_quality_dataset_gates(scenarios)
        assert gate.passed, gate.failures
        manifest = build_quality_manifest(scenarios)
        assert manifest.family_count == QUALITY_FAMILY_TARGET
        assert all(count == 6 for count in manifest.family_distribution.values())

    def test_manifest_determinism(self):
        profile = load_customer_profile("pilot-service-company-v1")
        m1 = build_quality_manifest(generate_quality_dataset(profile, seed=0))
        m2 = build_quality_manifest(generate_quality_dataset(profile, seed=0))
        assert m1.manifest_hash == m2.manifest_hash

    def test_transport_metadata_not_text_markers(self):
        profile = load_customer_profile("pilot-service-company-v1")
        scenarios = generate_quality_dataset(profile, seed=0)
        for scenario in scenarios:
            assert "[duplicate]" not in scenario.input.message_text
            assert "[continuation]" not in scenario.input.message_text
            if scenario.family == "thread_continuation_duplicate":
                assert scenario.thread_setup.get("gmail_message_id")

    def test_ptb_sem_0024_family_present(self):
        profile = load_customer_profile("niklas-demo-live-eval-v1")
        semi = generate_semi_auto_campaign(profile, seed=0)
        phishing = [s for s in semi if s.scenario_id == "PTB-SEM-0024"]
        assert phishing
        assert phishing[0].intent == "spam_phishing"


class TestQualityOracles:
    def test_oracle_statuses_defined(self):
        assert "not_applicable" in ORACLE_STATUSES
        assert "advisory" in ORACLE_STATUSES
        assert "unresolved" in ORACLE_STATUSES

    def test_not_applicable_excluded_from_scoring(self):
        from app.evaluation.profile_testbot.oracles.quality_result import QualityOracleResult

        score = aggregate_quality_score([
            QualityOracleResult("a", "pass", "decision_quality", "", blocker=True),
            QualityOracleResult("b", "fail", "decision_quality", "", blocker=False),
            QualityOracleResult("c", "not_applicable", "reply_quality", "", blocker=True),
        ])
        assert score["applicable_count"] == 2
        assert score["overall_pass"] is True

    def test_quality_campaign_passes(self):
        result = run_quality_campaign(profile_id="pilot-service-company-v1", seed=0)
        assert result.scenario_count == QUALITY_SCENARIO_TARGET
        assert result.overall_status == "PASS"
