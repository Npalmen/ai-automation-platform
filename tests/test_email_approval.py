"""
Tests for email approval gating in action_dispatch_processor.

Covers:
- auto_actions["lead"] = False → email actions get _needs_approval flag
- auto_actions["lead"] = True / "full_auto" → email actions execute immediately
- auto_actions missing → emails execute immediately (default)
- process_action_dispatch_job with db: creates approval records for email actions
- Monday item always executes regardless of auto_actions
- _email_needs_approval helper
- _resolve_email_approval (approve → send; reject → no send)
- Full approve/reject flow via main.py endpoints
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.domain.workflows.models import Job
from app.domain.workflows.enums import JobType
from app.domain.workflows.statuses import JobStatus
from app.workflows.processors.action_dispatch_processor import (
    _email_needs_approval,
    _build_email_approval_action,
    _build_lead_default_actions,
    _build_inquiry_default_actions,
    process_action_dispatch_job,
    _EMAIL_ACTION_TYPES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(job_type=JobType.LEAD, tenant_id="TENANT_TEST") -> Job:
    return Job(
        job_id=f"job_{uuid.uuid4().hex[:8]}",
        tenant_id=tenant_id,
        job_type=job_type,
        status=JobStatus.PROCESSING,
        input_data={
            "subject": "Hej, jag vill ha offert",
            "message_text": "Jag är intresserad av era tjänster.",
            "sender_name": "Anna Svensson",
            "sender_email": "anna@example.com",
        },
    )


def _settings_with_auto_actions(value) -> dict:
    return {"auto_actions": {"lead": value, "customer_inquiry": value}}


# ---------------------------------------------------------------------------
# _email_needs_approval
# ---------------------------------------------------------------------------

class TestEmailNeedsApproval:
    def test_false_requires_approval(self):
        assert _email_needs_approval("lead", {"auto_actions": {"lead": False}}) is True

    def test_manual_string_requires_approval(self):
        assert _email_needs_approval("lead", {"auto_actions": {"lead": "manual"}}) is True

    def test_missing_key_requires_approval(self):
        assert _email_needs_approval("lead", {"auto_actions": {}}) is True

    def test_missing_auto_actions_requires_approval(self):
        assert _email_needs_approval("lead", {}) is True

    def test_true_does_not_require_approval(self):
        assert _email_needs_approval("lead", {"auto_actions": {"lead": True}}) is False

    def test_full_auto_does_not_require_approval(self):
        assert _email_needs_approval("lead", {"auto_actions": {"lead": "full_auto"}}) is False

    def test_semi_requires_approval(self):
        assert _email_needs_approval("lead", {"auto_actions": {"lead": "semi"}}) is True

    def test_auto_string_does_not_require_approval(self):
        assert _email_needs_approval("lead", {"auto_actions": {"lead": "auto"}}) is False

    def test_different_job_type_respected(self):
        settings = {"auto_actions": {"lead": True, "customer_inquiry": False}}
        assert _email_needs_approval("customer_inquiry", settings) is True
        assert _email_needs_approval("lead", settings) is False


# ---------------------------------------------------------------------------
# _EMAIL_ACTION_TYPES constant
# ---------------------------------------------------------------------------

class TestEmailActionTypes:
    def test_contains_send_email(self):
        assert "send_email" in _EMAIL_ACTION_TYPES

    def test_contains_send_customer_auto_reply(self):
        assert "send_customer_auto_reply" in _EMAIL_ACTION_TYPES

    def test_contains_send_internal_handoff(self):
        assert "send_internal_handoff" in _EMAIL_ACTION_TYPES

    def test_does_not_contain_monday(self):
        assert "create_monday_item" not in _EMAIL_ACTION_TYPES


# ---------------------------------------------------------------------------
# _build_lead_default_actions with auto_actions gate
# ---------------------------------------------------------------------------

class TestLeadActionsEmailGate:
    def _lead_job(self):
        return _make_job(JobType.LEAD)

    def test_auto_false_wraps_email_actions_as_needs_approval(self):
        job = self._lead_job()
        settings = _settings_with_auto_actions(False)
        actions = _build_lead_default_actions(job, settings)
        email_actions = [a for a in actions if a.get("type") in _EMAIL_ACTION_TYPES and not a.get("_skip")]
        assert all(a.get("_needs_approval") for a in email_actions), \
            "All non-skipped email actions should be marked _needs_approval"

    def test_auto_false_monday_not_wrapped(self):
        job = self._lead_job()
        settings = _settings_with_auto_actions(False)
        actions = _build_lead_default_actions(job, settings)
        monday_actions = [a for a in actions if a.get("type") == "create_monday_item"]
        assert monday_actions, "Monday action must still be present"
        assert not any(a.get("_needs_approval") for a in monday_actions)

    def test_auto_true_no_approval_flag(self):
        job = self._lead_job()
        settings = _settings_with_auto_actions(True)
        actions = _build_lead_default_actions(job, settings)
        assert not any(a.get("_needs_approval") for a in actions), \
            "No action should have _needs_approval when auto=True"

    def test_auto_missing_no_approval_flag(self):
        job = self._lead_job()
        actions = _build_lead_default_actions(job, {})
        # missing auto_actions → default requires approval
        email_actions = [a for a in actions if a.get("type") in _EMAIL_ACTION_TYPES and not a.get("_skip")]
        assert all(a.get("_needs_approval") for a in email_actions)

    def test_manual_string_wraps_email_actions(self):
        job = self._lead_job()
        settings = _settings_with_auto_actions("manual")
        actions = _build_lead_default_actions(job, settings)
        email_actions = [a for a in actions if a.get("type") in _EMAIL_ACTION_TYPES and not a.get("_skip")]
        assert all(a.get("_needs_approval") for a in email_actions)

    def test_full_auto_string_does_not_wrap(self):
        job = self._lead_job()
        settings = _settings_with_auto_actions("full_auto")
        actions = _build_lead_default_actions(job, settings)
        assert not any(a.get("_needs_approval") for a in actions)

    def test_semi_wraps_email_actions(self):
        job = self._lead_job()
        settings = _settings_with_auto_actions("semi")
        actions = _build_lead_default_actions(job, settings)
        email_actions = [a for a in actions if a.get("type") in _EMAIL_ACTION_TYPES and not a.get("_skip")]
        assert all(a.get("_needs_approval") for a in email_actions)

    def test_skipped_actions_not_wrapped(self):
        """Skipped sentinel actions (no sender_email) must not get _needs_approval."""
        job = _make_job(JobType.LEAD)
        job.input_data["sender_email"] = ""  # force skip
        settings = _settings_with_auto_actions(False)
        actions = _build_lead_default_actions(job, settings)
        skipped = [a for a in actions if a.get("_skip")]
        assert not any(a.get("_needs_approval") for a in skipped)


# ---------------------------------------------------------------------------
# _build_inquiry_default_actions with auto_actions gate
# ---------------------------------------------------------------------------

class TestInquiryActionsEmailGate:
    def _inquiry_job(self):
        return _make_job(JobType.CUSTOMER_INQUIRY)

    def test_auto_false_wraps_email_actions(self):
        job = self._inquiry_job()
        settings = {"auto_actions": {"customer_inquiry": False}}
        actions = _build_inquiry_default_actions(job, settings)
        email_actions = [a for a in actions if a.get("type") in _EMAIL_ACTION_TYPES and not a.get("_skip")]
        assert all(a.get("_needs_approval") for a in email_actions)

    def test_auto_false_monday_not_wrapped(self):
        job = self._inquiry_job()
        settings = {"auto_actions": {"customer_inquiry": False}}
        actions = _build_inquiry_default_actions(job, settings)
        monday_actions = [a for a in actions if a.get("type") == "create_monday_item"]
        assert monday_actions
        assert not any(a.get("_needs_approval") for a in monday_actions)

    def test_auto_true_no_approval_flag(self):
        job = self._inquiry_job()
        settings = {"auto_actions": {"customer_inquiry": True}}
        actions = _build_inquiry_default_actions(job, settings)
        assert not any(a.get("_needs_approval") for a in actions)

    def test_semi_wraps_email_actions(self):
        job = self._inquiry_job()
        settings = {"auto_actions": {"customer_inquiry": "semi"}}
        actions = _build_inquiry_default_actions(job, settings)
        email_actions = [a for a in actions if a.get("type") in _EMAIL_ACTION_TYPES and not a.get("_skip")]
        assert all(a.get("_needs_approval") for a in email_actions)


# ---------------------------------------------------------------------------
# process_action_dispatch_job — approval creation path
# ---------------------------------------------------------------------------

class TestProcessActionDispatchEmailApproval:
    def _db_with_auto_false(self):
        """Return a mock db whose tenant config has auto_actions.lead = False."""
        db = MagicMock()
        mock_record = MagicMock()
        mock_record.auto_actions = {"lead": False, "customer_inquiry": False}
        mock_record.settings = {}

        from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
        with patch.object(TenantConfigRepository, "get_settings", return_value={}):
            pass  # just to verify import
        return db, mock_record

    def test_email_actions_not_executed_when_auto_false(self):
        job = _make_job(JobType.LEAD)
        db = MagicMock()

        with (
            patch("app.workflows.processors.action_dispatch_processor._read_automation_settings",
                  return_value={"followups_enabled": True, "leads_enabled": True,
                                "support_enabled": True, "support_email": "",
                                "auto_actions": {"lead": False}}),
            patch("app.workflows.processors.action_dispatch_processor.execute_action") as mock_exec,
            patch("app.workflows.processors.action_dispatch_processor._create_email_approval_record",
                  return_value={"approval_id": "eml_test", "status": "pending_approval"}),
        ):
            result_job = process_action_dispatch_job(job, db)

        # execute_action must not have been called for any email
        for call in mock_exec.call_args_list:
            action_arg = call[0][0] if call[0] else call[1].get("action", {})
            assert action_arg.get("type") not in _EMAIL_ACTION_TYPES, \
                "execute_action must not be called for email types when approval required"

    def test_monday_executed_when_auto_false(self):
        job = _make_job(JobType.LEAD)
        db = MagicMock()

        executed_types = []

        def fake_execute(action, db=None):
            executed_types.append(action.get("type"))
            return {"type": action["type"], "status": "completed"}

        with (
            patch("app.workflows.processors.action_dispatch_processor._read_automation_settings",
                  return_value={"followups_enabled": True, "leads_enabled": True,
                                "support_enabled": True, "support_email": "",
                                "auto_actions": {"lead": False}}),
            patch("app.workflows.processors.action_dispatch_processor.execute_action", side_effect=fake_execute),
            patch("app.workflows.processors.action_dispatch_processor._create_email_approval_record",
                  return_value={"approval_id": "eml_test", "status": "pending_approval"}),
        ):
            process_action_dispatch_job(job, db)

        assert "create_monday_item" in executed_types, "Monday must execute even when email approvals required"

    def test_pending_approvals_in_result_payload(self):
        job = _make_job(JobType.LEAD)
        db = MagicMock()

        with (
            patch("app.workflows.processors.action_dispatch_processor._read_automation_settings",
                  return_value={"followups_enabled": True, "leads_enabled": True,
                                "support_enabled": True, "support_email": "",
                                "auto_actions": {"lead": False}}),
            patch("app.workflows.processors.action_dispatch_processor.execute_action",
                  return_value={"type": "create_monday_item", "status": "completed"}),
            patch("app.workflows.processors.action_dispatch_processor._create_email_approval_record",
                  return_value={"approval_id": "eml_abc", "status": "pending_approval"}),
        ):
            result_job = process_action_dispatch_job(job, db)

        from app.workflows.processors.ai_processor_utils import get_latest_processor_payload
        payload = get_latest_processor_payload(result_job, "action_dispatch_processor")
        assert "pending_approval_count" in payload
        assert payload["pending_approval_count"] > 0
        assert "actions_pending_approval" in payload
        assert "ai_reply_suggestions" in payload
        assert payload["ai_reply_suggestions"], "Lead flow should expose at least one AI reply suggestion"
        assert "lead_sla" in payload
        assert payload["lead_sla"]["enabled"] is True

    def test_no_approval_when_auto_true(self):
        job = _make_job(JobType.LEAD)
        db = MagicMock()

        created_approvals = []

        with (
            patch("app.workflows.processors.action_dispatch_processor._read_automation_settings",
                  return_value={"followups_enabled": True, "leads_enabled": True,
                                "support_enabled": True, "support_email": "",
                                "auto_actions": {"lead": True}}),
            patch("app.workflows.processors.action_dispatch_processor.execute_action",
                  return_value={"type": "send_customer_auto_reply", "status": "completed"}),
            patch("app.workflows.processors.action_dispatch_processor._create_email_approval_record",
                  side_effect=lambda *a, **kw: created_approvals.append(True) or {}),
        ):
            process_action_dispatch_job(job, db)

        assert not created_approvals, "No approval records when auto_actions=True"


# ---------------------------------------------------------------------------
# _resolve_email_approval helper
# ---------------------------------------------------------------------------

_EXEC = "app.workflows.action_executor.execute_action"
_UPSERT = "app.repositories.postgres.approval_repository.ApprovalRequestRepository.upsert_from_payload"
_FINALIZE = "app.workflows.email_approval_resolution.finalize_email_approval_resolution"


class TestResolveEmailApproval:
    def _make_approval_record(self, state="pending"):
        record = MagicMock()
        record.approval_id = "eml_test123"
        record.tenant_id = "TENANT_TEST"
        record.job_id = "job_abc"
        record.job_type = "lead"
        record.state = state
        record.request_payload = {
            "approval_id": "eml_test123",
            "state": state,
            "next_on_approve": "email_send",
        }
        record.delivery_payload = {
            "type": "send_customer_auto_reply",
            "to": "customer@example.com",
            "subject": "Tack för din förfrågan",
            "body": "Vi återkommer snart.",
        }
        record.resolution_note = None
        return record

    def test_approve_calls_execute_action(self):
        from app.main import _resolve_email_approval
        db = MagicMock()
        approval = self._make_approval_record()

        with (
            patch(_EXEC, return_value={"status": "sent"}) as mock_exec,
            patch(_UPSERT),
            patch(_FINALIZE),
        ):
            result = _resolve_email_approval(db, approval, approved=True, actor="operator")

        mock_exec.assert_called_once()
        call_payload = mock_exec.call_args[0][0]
        assert call_payload["to"] == "customer@example.com"
        assert result["status"] == "approved"

    def test_approve_returns_send_result(self):
        from app.main import _resolve_email_approval
        db = MagicMock()
        approval = self._make_approval_record()

        with (
            patch(_EXEC, return_value={"status": "sent", "message_id": "msg123"}),
            patch(_UPSERT),
            patch(_FINALIZE),
        ):
            result = _resolve_email_approval(db, approval, approved=True)

        assert result["send_result"]["message_id"] == "msg123"
        assert result["send_error"] is None

    def test_reject_does_not_call_execute_action(self):
        from app.main import _resolve_email_approval
        db = MagicMock()
        approval = self._make_approval_record()

        with (
            patch(_EXEC) as mock_exec,
            patch(_UPSERT),
            patch(_FINALIZE),
        ):
            result = _resolve_email_approval(db, approval, approved=False, actor="operator")

        mock_exec.assert_not_called()
        assert result["status"] == "rejected"
        assert result["send_result"] is None

    def test_approve_send_failure_captured_in_response(self):
        from app.main import _resolve_email_approval
        db = MagicMock()
        approval = self._make_approval_record()

        with (
            patch(_EXEC, side_effect=RuntimeError("Gmail unavailable")),
            patch(_UPSERT),
            patch(_FINALIZE),
        ):
            result = _resolve_email_approval(db, approval, approved=True)

        # Should NOT raise — failure is captured
        assert result["status"] == "approved"
        assert "Gmail unavailable" in result["send_error"]
        assert result["send_result"] is None

    def test_approved_state_persisted(self):
        from app.main import _resolve_email_approval
        db = MagicMock()
        approval = self._make_approval_record()

        upserted_payloads = []

        with (
            patch(_EXEC, return_value={"status": "sent"}),
            patch(_UPSERT, side_effect=lambda **kw: upserted_payloads.append(kw["approval_request"])),
            patch(_FINALIZE),
        ):
            _resolve_email_approval(db, approval, approved=True, actor="anna", note="Ser bra ut")

        assert upserted_payloads
        saved = upserted_payloads[0]
        assert saved["state"] == "approved"
        assert saved["resolved_by"] == "anna"
        assert saved["resolution_note"] == "Ser bra ut"

    def test_rejected_state_persisted(self):
        from app.main import _resolve_email_approval
        db = MagicMock()
        approval = self._make_approval_record()

        upserted_payloads = []

        with (
            patch(_EXEC),
            patch(_UPSERT, side_effect=lambda **kw: upserted_payloads.append(kw["approval_request"])),
            patch(_FINALIZE),
        ):
            _resolve_email_approval(db, approval, approved=False)

        saved = upserted_payloads[0]
        assert saved["state"] == "rejected"

    def test_approve_without_delivery_payload_does_not_crash(self):
        from app.main import _resolve_email_approval
        db = MagicMock()
        approval = self._make_approval_record()
        approval.delivery_payload = None

        with (
            patch(_EXEC) as mock_exec,
            patch(_UPSERT),
            patch(_FINALIZE),
        ):
            result = _resolve_email_approval(db, approval, approved=True)

        mock_exec.assert_not_called()
        assert result["status"] == "approved"


# ---------------------------------------------------------------------------
# approve/reject endpoint routing (next_on_approve == email_send)
# ---------------------------------------------------------------------------

class TestApproveRejectEndpointRouting:
    def _make_approval_record(self, next_on_approve):
        record = MagicMock()
        record.approval_id = "eml_endpoint_test"
        record.tenant_id = "TENANT_TEST"
        record.job_id = "job_xyz"
        record.job_type = "lead"
        record.state = "pending"
        record.next_on_approve = next_on_approve
        record.request_payload = {"approval_id": "eml_endpoint_test", "state": "pending",
                                   "next_on_approve": next_on_approve}
        record.delivery_payload = {"type": "send_customer_auto_reply", "to": "t@e.com",
                                   "subject": "Test", "body": "Body"}
        record.resolution_note = None
        return record

    def test_approve_routes_to_resolve_email_approval_for_email_send(self):
        from app.main import approve_request, ApprovalDecisionRequest
        db = MagicMock()
        approval = self._make_approval_record("email_send")

        with (
            patch("app.main.ApprovalRequestRepository.get_by_approval_id", return_value=approval),
            patch("app.main._resolve_email_approval", return_value={"status": "approved"}) as mock_resolve,
        ):
            result = approve_request(
                approval_id="eml_endpoint_test",
                request=ApprovalDecisionRequest(actor="test"),
                db=db,
                tenant_id="TENANT_TEST",
            )

        mock_resolve.assert_called_once()
        assert result["status"] == "approved"

    def test_reject_routes_to_resolve_email_approval_for_email_send(self):
        from app.main import reject_request, ApprovalDecisionRequest
        db = MagicMock()
        approval = self._make_approval_record("email_send")

        with (
            patch("app.main.ApprovalRequestRepository.get_by_approval_id", return_value=approval),
            patch("app.main._resolve_email_approval", return_value={"status": "rejected"}) as mock_resolve,
        ):
            result = reject_request(
                approval_id="eml_endpoint_test",
                request=ApprovalDecisionRequest(actor="test"),
                db=db,
                tenant_id="TENANT_TEST",
            )

        mock_resolve.assert_called_once()
        assert result["status"] == "rejected"

    def test_approve_does_not_route_to_email_for_pipeline_approval(self):
        from app.main import approve_request, ApprovalDecisionRequest
        db = MagicMock()
        approval = self._make_approval_record("action_dispatch")

        from datetime import datetime
        fake_job = MagicMock()
        fake_job.model_dump.return_value = {
            "job_id": "job_xyz",
            "tenant_id": "TENANT_TEST",
            "job_type": "lead",
            "status": "completed",
            "input_data": {},
            "result": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }

        with (
            patch("app.main.ApprovalRequestRepository.get_by_approval_id", return_value=approval),
            patch("app.main._resolve_email_approval") as mock_email,
            patch("app.main.resolve_approval", return_value=fake_job),
            patch(
                "app.repositories.postgres.approval_repository.ApprovalRequestRepository.count_pending_for_job",
                return_value=0,
            ),
        ):
            approve_request(
                approval_id="eml_endpoint_test",
                request=ApprovalDecisionRequest(actor="test"),
                db=db,
                tenant_id="TENANT_TEST",
            )

        mock_email.assert_not_called()


# ---------------------------------------------------------------------------
# Tenant isolation: approval only visible to owner tenant
# ---------------------------------------------------------------------------

class TestEmailApprovalTenantIsolation:
    def test_wrong_tenant_gets_404(self):
        from app.main import approve_request, ApprovalDecisionRequest
        from fastapi import HTTPException
        db = MagicMock()

        with patch("app.main.ApprovalRequestRepository.get_by_approval_id", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                approve_request(
                    approval_id="eml_other",
                    request=ApprovalDecisionRequest(actor="hacker"),
                    db=db,
                    tenant_id="TENANT_WRONG",
                )
        assert exc_info.value.status_code == 404
