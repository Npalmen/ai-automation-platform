"""
MVP flow critical-path tests.

Covers:
- policy_processor: lead send_for_approval / auto_execute / force_approval_test
- human_handoff_processor: approval request creation / no-op path
- approval_service: has_pending_approval / get_pending_approval / build_approval_request
- action_executor: send_email routes to GOOGLE_MAIL (not a missing EMAIL type)
- is_integration_configured: token-based integrations are recognised
- orchestrator._should_skip_step: ACTION_DISPATCH skipped on approval/review decisions

All tests run without a database connection by avoiding module-level DB imports.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lead_job(*, decisioning_decision: str = "send_for_approval") -> Job:
    job = Job(
        tenant_id="TENANT_1001",
        job_type=JobType.POLICY,
        input_data={
            "subject": "Offertförfrågan",
            "message_text": "Hej, vill ha pris.",
            "sender": {"name": "Test User", "email": "test@example.com"},
        },
    )
    job.processor_history = [
        {
            "processor": "classification_processor",
            "result": {
                "payload": {
                    "detected_job_type": "lead",
                    "confidence": 0.9,
                    "reasons": ["request_for_price"],
                }
            },
        },
        {
            "processor": "entity_extraction_processor",
            "result": {
                "payload": {
                    "entities": {"customer_name": "Test User", "email": "test@example.com"},
                    "confidence": 0.85,
                    "validation": {"is_valid": True, "issues": []},
                }
            },
        },
        {
            "processor": "lead_processor",
            "result": {
                "payload": {
                    "lead_score": 75,
                    "priority": "high",
                    "routing": "sales_queue",
                    "confidence": 0.85,
                    "low_confidence": False,
                }
            },
        },
        {
            "processor": "decisioning_processor",
            "result": {
                "payload": {
                    "decision": decisioning_decision,
                    "target_queue": "sales_queue",
                    "actions": [],
                    "confidence": 0.85,
                    "low_confidence": False,
                    "approval_route": (
                        "approval_required"
                        if decisioning_decision == "send_for_approval"
                        else None
                    ),
                }
            },
        },
    ]
    return job


def _job_with_policy(*, decision: str) -> Job:
    job = _lead_job(decisioning_decision=decision)
    job.processor_history.append(
        {
            "processor": "policy_processor",
            "result": {
                "payload": {
                    "decision": decision,
                    "reasons": ["test_reason"],
                    "recommended_next_step": (
                        "awaiting_approval" if decision == "send_for_approval" else "action_dispatch"
                    ),
                    "detected_job_type": "lead",
                }
            },
        }
    )
    job.result = job.processor_history[-1]["result"]
    return job


# ---------------------------------------------------------------------------
# policy_processor
# ---------------------------------------------------------------------------

class TestPolicyProcessor:
    def test_lead_send_for_approval(self):
        from app.workflows.processors.policy_processor import process_policy_job

        job = _lead_job(decisioning_decision="send_for_approval")
        result = process_policy_job(job)
        payload = result.result["payload"]

        assert payload["decision"] == "send_for_approval"
        assert payload["recommended_next_step"] == "awaiting_approval"
        assert result.result["requires_human_review"] is False

    def test_lead_auto_execute(self):
        from app.workflows.processors.policy_processor import process_policy_job

        job = _lead_job(decisioning_decision="auto_execute")
        result = process_policy_job(job)
        payload = result.result["payload"]

        assert payload["decision"] == "auto_execute"
        assert payload["recommended_next_step"] == "action_dispatch"
        assert result.result["requires_human_review"] is False

    def test_force_approval_test_flag(self):
        from app.workflows.processors.policy_processor import process_policy_job

        job = _lead_job()
        job.input_data["force_approval_test"] = True
        result = process_policy_job(job)
        payload = result.result["payload"]

        assert payload["decision"] == "send_for_approval"
        assert payload["recommended_next_step"] == "awaiting_approval"
        assert "forced_approval_test" in payload["reasons"]


# ---------------------------------------------------------------------------
# human_handoff_processor
# ---------------------------------------------------------------------------

class TestHumanHandoffProcessor:
    def test_creates_approval_request_when_send_for_approval(self):
        from app.workflows.processors.human_handoff_processor import process_human_handoff_job

        job = _job_with_policy(decision="send_for_approval")
        result = process_human_handoff_job(job)
        payload = result.result["payload"]

        assert payload["handoff_created"] is True
        assert payload["handoff_type"] == "approval_request"
        assert "approval_request" in payload
        assert payload["approval_request"]["state"] == "pending"
        assert payload["approval_request"]["job_id"] == job.job_id

    def test_no_handoff_when_not_required(self):
        from app.workflows.processors.human_handoff_processor import process_human_handoff_job

        job = _job_with_policy(decision="auto_execute")
        job.result = {"requires_human_review": False, "payload": {}}
        result = process_human_handoff_job(job)
        payload = result.result["payload"]

        assert payload["handoff_created"] is False
        assert payload["handoff_type"] is None


# ---------------------------------------------------------------------------
# approval_service helpers (no DB)
# ---------------------------------------------------------------------------

class TestApprovalServiceHelpers:
    def _approval_request_dict(self, job: Job) -> dict:
        from app.workflows.approval_service import build_approval_request
        return build_approval_request(job)

    def test_build_approval_request_fields(self):
        job = _lead_job()
        approval = self._approval_request_dict(job)

        assert approval["job_id"] == job.job_id
        assert approval["tenant_id"] == job.tenant_id
        assert approval["state"] == "pending"
        assert approval["next_on_approve"] == "action_dispatch"
        assert approval["next_on_reject"] == "manual_review"
        assert "approval_id" in approval

    def test_has_pending_approval_true(self):
        from app.workflows.approval_service import has_pending_approval

        job = _lead_job()
        approval = self._approval_request_dict(job)
        job.result = {
            "status": "completed",
            "requires_human_review": False,
            "payload": {
                "processor_name": "human_handoff_processor",
                "approval_request": approval,
            },
        }
        assert has_pending_approval(job) is True

    def test_has_pending_approval_false_when_no_approval(self):
        from app.workflows.approval_service import has_pending_approval

        job = _lead_job()
        job.result = {"status": "completed", "payload": {}}
        assert has_pending_approval(job) is False

    def test_get_pending_approval_none_when_resolved(self):
        from app.workflows.approval_service import get_pending_approval

        job = _lead_job()
        approval = self._approval_request_dict(job)
        approval["state"] = "approved"
        job.result = {
            "status": "completed",
            "requires_human_review": False,
            "payload": {"approval_request": approval},
        }
        assert get_pending_approval(job) is None


# ---------------------------------------------------------------------------
# orchestrator._should_skip_step (no DB)
# ---------------------------------------------------------------------------

class TestOrchestratorSkipStep:
    def _orchestrator(self):
        from app.workflows.orchestrator import WorkflowOrchestrator
        return WorkflowOrchestrator(db=None)

    def test_skips_action_dispatch_on_send_for_approval(self):
        orch = self._orchestrator()
        job = _job_with_policy(decision="send_for_approval")
        assert orch._should_skip_step(job, JobType.ACTION_DISPATCH) is True

    def test_skips_action_dispatch_on_hold_for_review(self):
        orch = self._orchestrator()
        job = _job_with_policy(decision="hold_for_review")
        assert orch._should_skip_step(job, JobType.ACTION_DISPATCH) is True

    def test_does_not_skip_action_dispatch_on_auto_execute(self):
        orch = self._orchestrator()
        job = _job_with_policy(decision="auto_execute")
        assert orch._should_skip_step(job, JobType.ACTION_DISPATCH) is False

    def test_never_skips_other_steps(self):
        orch = self._orchestrator()
        job = _job_with_policy(decision="send_for_approval")
        for step in [JobType.POLICY, JobType.HUMAN_HANDOFF, JobType.LEAD]:
            assert orch._should_skip_step(job, step) is False


# ---------------------------------------------------------------------------
# is_integration_configured (no DB)
# ---------------------------------------------------------------------------

class TestIsIntegrationConfigured:
    def test_google_mail_configured_when_token_and_url_present(self):
        from app.integrations.service import is_integration_configured

        config = {
            "access_token": "ya29.sometoken",
            "api_url": "https://gmail.googleapis.com",
            "user_id": "me",
        }
        assert is_integration_configured(config) is True

    def test_not_configured_when_token_missing(self):
        from app.integrations.service import is_integration_configured

        assert is_integration_configured({"access_token": "", "api_url": "https://x.com"}) is False

    def test_not_configured_when_url_missing(self):
        from app.integrations.service import is_integration_configured

        assert is_integration_configured({"access_token": "tok", "api_url": ""}) is False

    def test_smtp_configured(self):
        from app.integrations.service import is_integration_configured

        config = {"provider": "smtp", "host": "smtp.x.com", "port": 587, "from_email": "a@b.com"}
        assert is_integration_configured(config) is True

    def test_smtp_missing_host(self):
        from app.integrations.service import is_integration_configured

        config = {"provider": "smtp", "port": 587, "from_email": "a@b.com"}
        assert is_integration_configured(config) is False

    def test_webhook_configured(self):
        from app.integrations.service import is_integration_configured

        config = {"provider": "webhook", "webhook_url": "https://hooks.slack.com/x"}
        assert is_integration_configured(config) is True

    def test_empty_config_not_configured(self):
        from app.integrations.service import is_integration_configured

        assert is_integration_configured({}) is False


# ---------------------------------------------------------------------------
# action_executor: send_email uses GOOGLE_MAIL integration type (no DB, no network)
# ---------------------------------------------------------------------------

class TestActionExecutorEmailRouting:
    def test_send_email_resolves_google_mail_type(self):
        """
        send_email must call get_integration_connection_config with GOOGLE_MAIL.
        Before the patch this used IntegrationType.EMAIL which doesn't exist.
        """
        from app.integrations.enums import IntegrationType
        from app.workflows import action_executor

        captured: dict = {}

        def fake_get_config(tenant_id, integration_type):
            captured["integration_type"] = integration_type
            return {}  # unconfigured → falls to stub, no network call

        with patch.object(action_executor, "get_integration_connection_config", fake_get_config):
            result = action_executor.execute_action({
                "type": "send_email",
                "tenant_id": "TENANT_1001",
                "to": "r@example.com",
                "subject": "Test",
                "body": "Hello",
            })

        assert captured.get("integration_type") == IntegrationType.GOOGLE_MAIL
        assert result["type"] == "send_email"
        assert result["status"] == "executed"

    def test_send_email_stub_fallback_when_unconfigured(self):
        from app.workflows import action_executor

        with patch.object(
            action_executor,
            "get_integration_connection_config",
            return_value={},
        ):
            result = action_executor.execute_action({
                "type": "send_email",
                "tenant_id": "TENANT_1001",
                "to": "a@b.com",
                "subject": "S",
                "body": "B",
            })

        assert result["status"] == "executed"
        assert result["provider"] == "internal_stub"

    def test_unsupported_action_type_raises(self):
        from app.workflows.action_executor import execute_action

        with pytest.raises(ValueError, match="Unsupported action type"):
            execute_action({"type": "unknown_action"})
