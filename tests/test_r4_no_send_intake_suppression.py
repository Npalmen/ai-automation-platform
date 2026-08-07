"""Regression tests for R4 PTB-SEM-0023 expected intake suppression."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.qualification.coworker_r4_live_backend import _execute_no_send
from app.evaluation.profile_testbot.qualification.coworker_r4_no_send_intake_suppression import (
    R4_NO_SEND_INTAKE_SUPPRESSION_REASON,
    R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID,
    apply_r4_expected_intake_suppression_result,
    parse_intake_skip_reason_from_error,
    resolve_r4_no_send_intake_suppression,
    scenario_local_gmail_sends,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import R4_NO_SEND_SCENARIO_IDS
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario, ProfileScenarioInput


def _scenario(
    scenario_id: str,
    *,
    expected_send_behavior: str = "no_reply",
) -> ProfileScenario:
    return ProfileScenario(
        scenario_id=scenario_id,
        profile_id="niklas-demo-live-eval-v1",
        profile_snapshot_hash="hash",
        family="spam",
        intent="no_reply",
        risk_class="low",
        input=ProfileScenarioInput(
            subject="Nyhetsbrev",
            message_text="Avregistrera dig här.",
            sender_name="Test",
            sender_email="sender@eval.test",
            language="sv",
        ),
        expected_classification={},
        expected_route={},
        expected_authorization={},
        expected_send_behavior=expected_send_behavior,
    )


class TestR4NoSendIntakeSuppressionContract:
    def test_ptb_sem_0023_newsletter_disabled_positive(self):
        res = resolve_r4_no_send_intake_suppression(
            scenario_id=R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID,
            expected_send_behavior="no_reply",
            intake_skip_reason=R4_NO_SEND_INTAKE_SUPPRESSION_REASON,
            inbound_delivery_observed=True,
        )
        assert res.eligible is True
        assert res.blockers == []

    def test_wrong_suppression_reason_fails(self):
        res = resolve_r4_no_send_intake_suppression(
            scenario_id=R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID,
            expected_send_behavior="no_reply",
            intake_skip_reason="spam_disabled",
            inbound_delivery_observed=True,
        )
        assert res.eligible is False
        assert any("mismatch" in b for b in res.blockers)

    def test_wrong_scenario_with_newsletter_disabled_fails(self):
        res = resolve_r4_no_send_intake_suppression(
            scenario_id="PTB-SEM-0021",
            expected_send_behavior="no_reply",
            intake_skip_reason=R4_NO_SEND_INTAKE_SUPPRESSION_REASON,
            inbound_delivery_observed=True,
        )
        assert res.eligible is False

    def test_timeout_not_treated_as_suppression(self):
        assert parse_intake_skip_reason_from_error(LiveEvalSafetyError("intake_timeout: poll")) is None

    def test_ambiguous_or_side_effects_fail(self):
        res = resolve_r4_no_send_intake_suppression(
            scenario_id=R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID,
            expected_send_behavior="no_reply",
            intake_skip_reason=R4_NO_SEND_INTAKE_SUPPRESSION_REASON,
            inbound_delivery_observed=True,
            job_id="job-1",
        )
        assert res.eligible is False
        res2 = resolve_r4_no_send_intake_suppression(
            scenario_id=R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID,
            expected_send_behavior="no_reply",
            intake_skip_reason=R4_NO_SEND_INTAKE_SUPPRESSION_REASON,
            inbound_delivery_observed=True,
            gmail_sends=1,
        )
        assert res2.eligible is False

    def test_apply_result_exposes_evidence_fields(self):
        res = resolve_r4_no_send_intake_suppression(
            scenario_id=R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID,
            expected_send_behavior="no_reply",
            intake_skip_reason=R4_NO_SEND_INTAKE_SUPPRESSION_REASON,
            inbound_delivery_observed=True,
        )
        out = apply_r4_expected_intake_suppression_result(
            {"scenario_id": R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID, "status": "failed"},
            resolution=res,
            intake_skip_reason=R4_NO_SEND_INTAKE_SUPPRESSION_REASON,
        )
        assert out["status"] == "passed"
        assert out["intake_suppressed"] is True
        assert out["intake_suppression_reason"] == "newsletter_disabled"
        assert out["job_created"] is False
        assert out["approval_count"] == 0
        assert out["gmail_sends"] == 0
        assert out["gmail_drafts"] == 0
        assert out["external_executions"] == 0


class TestExecuteNoSendIntakeSuppressionPath:
    def test_execute_no_send_passes_expected_suppression_for_0023(self):
        backend = MagicMock()
        backend.gmail_sends = 0
        backend.sent_keys = set()
        backend.runs = {}
        bindings = SimpleNamespace(
            campaign_id="camp",
            tenant_id="TENANT_LIVE_EVAL",
            candidate_runtime_sha="b7fd95e",
            executor_runtime_sha="cdee2c0",
            manifest_semantic_hash="m",
            candidate_package_semantic_hash="p",
            human_review_sha256="h",
            expected_sender="s@example.com",
            expected_recipient="r@example.com",
        )
        scenario = _scenario(R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID)

        with (
            patch(
                "app.evaluation.profile_testbot.qualification.coworker_r4_live_backend._register_r4_live_run"
            ),
            patch(
                "app.evaluation.profile_testbot.qualification.coworker_r4_live_backend._send_inbound_trigger_for_scenario"
            ),
            patch.object(
                backend,
                "observe_intake",
                side_effect=LiveEvalSafetyError("intake_skipped: newsletter_disabled"),
            ),
        ):
            result = _execute_no_send(
                backend=backend,
                scenario=scenario,
                evaluation_run_id="run-1",
                campaign_id="camp",
                campaign_bindings=bindings,
            )

        assert result["status"] == "passed"
        assert result["intake_suppressed"] is True
        assert result["intake_suppression_reason"] == "newsletter_disabled"
        assert result["job_created"] is False

    def test_execute_no_send_still_fails_wrong_reason_for_0023(self):
        backend = MagicMock()
        backend.gmail_sends = 0
        backend.sent_keys = set()
        backend.runs = {}
        bindings = SimpleNamespace(
            campaign_id="camp",
            tenant_id="TENANT_LIVE_EVAL",
            candidate_runtime_sha="b7fd95e",
            executor_runtime_sha="cdee2c0",
            manifest_semantic_hash="m",
            candidate_package_semantic_hash="p",
            human_review_sha256="h",
            expected_sender="s@example.com",
            expected_recipient="r@example.com",
        )
        scenario = _scenario(R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID)

        with (
            patch(
                "app.evaluation.profile_testbot.qualification.coworker_r4_live_backend._register_r4_live_run"
            ),
            patch(
                "app.evaluation.profile_testbot.qualification.coworker_r4_live_backend._send_inbound_trigger_for_scenario"
            ),
            patch.object(
                backend,
                "observe_intake",
                side_effect=LiveEvalSafetyError("intake_skipped: spam_disabled"),
            ),
        ):
            result = _execute_no_send(
                backend=backend,
                scenario=scenario,
                evaluation_run_id="run-1",
                campaign_id="camp",
                campaign_bindings=bindings,
            )

        assert result["status"] == "failed"
        assert result["failure_stage"] == "no_send_verification"

    def test_ptb_sem_0024_local_quarantine_unchanged(self):
        from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
            PTB_SEM_0024_SCENARIO_ID,
        )

        backend = MagicMock()
        scenario = _scenario(PTB_SEM_0024_SCENARIO_ID, expected_send_behavior="reject")
        bindings = SimpleNamespace()
        result = _execute_no_send(
            backend=backend,
            scenario=scenario,
            evaluation_run_id="run-1",
            campaign_id="camp",
            campaign_bindings=bindings,
        )
        assert result["status"] == "passed"
        backend.observe_intake.assert_not_called()

    def test_other_no_send_scenarios_remain_in_registry(self):
        assert R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID in R4_NO_SEND_SCENARIO_IDS
        assert len(R4_NO_SEND_SCENARIO_IDS) == 16

    def test_scenario_local_delta_after_20_prior_campaign_sends(self):
        assert (
            scenario_local_gmail_sends(
                campaign_gmail_sends_before=20,
                campaign_gmail_sends_after=20,
            )
            == 0
        )
        res = resolve_r4_no_send_intake_suppression(
            scenario_id=R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID,
            expected_send_behavior="no_reply",
            intake_skip_reason=R4_NO_SEND_INTAKE_SUPPRESSION_REASON,
            inbound_delivery_observed=True,
            gmail_sends=scenario_local_gmail_sends(
                campaign_gmail_sends_before=20,
                campaign_gmail_sends_after=20,
            ),
        )
        assert res.eligible is True
        assert res.blockers == []

    def test_scenario_local_delta_positive_fails(self):
        res = resolve_r4_no_send_intake_suppression(
            scenario_id=R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID,
            expected_send_behavior="no_reply",
            intake_skip_reason=R4_NO_SEND_INTAKE_SUPPRESSION_REASON,
            inbound_delivery_observed=True,
            gmail_sends=scenario_local_gmail_sends(
                campaign_gmail_sends_before=20,
                campaign_gmail_sends_after=21,
            ),
        )
        assert res.eligible is False
        assert "gmail_send_observed" in res.blockers

    def test_execute_no_send_passes_0023_after_20_prior_campaign_sends(self):
        backend = MagicMock()
        backend.gmail_sends = 20
        backend.sent_keys = set()
        backend.runs = {}
        bindings = SimpleNamespace(
            campaign_id="camp",
            tenant_id="TENANT_LIVE_EVAL",
            candidate_runtime_sha="b7fd95e",
            executor_runtime_sha="6465938",
            manifest_semantic_hash="m",
            candidate_package_semantic_hash="p",
            human_review_sha256="h",
            expected_sender="s@example.com",
            expected_recipient="r@example.com",
        )
        scenario = _scenario(R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID)

        with (
            patch(
                "app.evaluation.profile_testbot.qualification.coworker_r4_live_backend._register_r4_live_run"
            ),
            patch(
                "app.evaluation.profile_testbot.qualification.coworker_r4_live_backend._send_inbound_trigger_for_scenario"
            ),
            patch.object(
                backend,
                "observe_intake",
                side_effect=LiveEvalSafetyError("intake_skipped: newsletter_disabled"),
            ),
        ):
            result = _execute_no_send(
                backend=backend,
                scenario=scenario,
                evaluation_run_id="run-1",
                campaign_id="camp",
                campaign_bindings=bindings,
            )

        assert result["status"] == "passed"
        assert result["intake_suppressed"] is True
        assert result["intake_suppression_reason"] == "newsletter_disabled"
        assert result["job_created"] is False
        assert result["approval_count"] == 0
        assert result["gmail_sends"] == 0
        assert result["gmail_drafts"] == 0
        assert result["external_executions"] == 0
        assert backend.gmail_sends == 20

    def test_execute_no_send_fails_0023_when_scenario_increments_send_counter(self):
        backend = MagicMock()
        backend.gmail_sends = 20
        backend.sent_keys = set()
        backend.runs = {}

        def _increment_and_skip(*_args, **_kwargs):
            backend.gmail_sends = 21
            raise LiveEvalSafetyError("intake_skipped: newsletter_disabled")

        bindings = SimpleNamespace(
            campaign_id="camp",
            tenant_id="TENANT_LIVE_EVAL",
            candidate_runtime_sha="b7fd95e",
            executor_runtime_sha="6465938",
            manifest_semantic_hash="m",
            candidate_package_semantic_hash="p",
            human_review_sha256="h",
            expected_sender="s@example.com",
            expected_recipient="r@example.com",
        )
        scenario = _scenario(R4_NO_SEND_INTAKE_SUPPRESSION_SCENARIO_ID)

        with (
            patch(
                "app.evaluation.profile_testbot.qualification.coworker_r4_live_backend._register_r4_live_run"
            ),
            patch(
                "app.evaluation.profile_testbot.qualification.coworker_r4_live_backend._send_inbound_trigger_for_scenario"
            ),
            patch.object(backend, "observe_intake", side_effect=_increment_and_skip),
        ):
            result = _execute_no_send(
                backend=backend,
                scenario=scenario,
                evaluation_run_id="run-1",
                campaign_id="camp",
                campaign_bindings=bindings,
            )

        assert result["status"] == "failed"
        assert result["failure_stage"] == "no_send_verification"
        assert backend.gmail_sends == 21
