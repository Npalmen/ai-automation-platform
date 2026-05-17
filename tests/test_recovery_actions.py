"""
Tests for admin recovery actions (Slice 1 — Replay & Recovery Console).

Covers:
- Each action returns correct {status, action, job_id, tenant_id, message, details} shape
- 404-equivalent for unknown or wrong-tenant job
- Tenant isolation: action returns failure when job does not belong to tenant
- Admin auth required on HTTP endpoints (401 without key)
- retry_job resets state and calls pipeline
- replay_dispatch calls ControlledDispatchEngine and respects idempotency result
- reclassify strips all history and reruns pipeline
- re_extract preserves classification but strips downstream state
- resend_approval finds pending approval and clears delivery metadata
- reprocess_gmail_source requires gmail source metadata
- Audit events emitted for initiated/success/failed paths
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call
import pytest

from app.admin.recovery_actions import (
    retry_job,
    replay_dispatch,
    reclassify,
    re_extract,
    resend_approval,
    reprocess_gmail_source,
)
from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(
    job_id: str = "job-1",
    tenant_id: str = "T_TEST",
    status: JobStatus = JobStatus.FAILED,
    job_type: JobType = JobType.LEAD,
    processor_history: list | None = None,
    input_data: dict | None = None,
) -> Job:
    return Job(
        job_id=job_id,
        tenant_id=tenant_id,
        job_type=job_type,
        status=status,
        input_data=input_data or {},
        result=None,
        processor_history=processor_history or [],
    )


def _mock_db():
    db = MagicMock()
    return db


def _classification_history_entry(detected: str = "lead") -> dict:
    return {
        "processor": "classification_processor",
        "result": {"payload": {"detected_job_type": detected}},
    }


def _intake_history_entry() -> dict:
    return {"processor": "intake_processor", "result": {"payload": {}}}


# ---------------------------------------------------------------------------
# Action result shape validation
# ---------------------------------------------------------------------------

def _assert_result_shape(result: dict, expected_status: str, action_name: str) -> None:
    assert result["status"] == expected_status, f"Expected status={expected_status}, got {result}"
    assert result["action"] == action_name
    assert "job_id" in result
    assert "tenant_id" in result
    assert "message" in result
    assert "details" in result


# ---------------------------------------------------------------------------
# retry_job
# ---------------------------------------------------------------------------

class TestRetryJob:
    def test_missing_job_returns_failure(self):
        db = _mock_db()
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
            result = retry_job(db, "T_TEST", "missing-job")
        _assert_result_shape(result, "failed", "retry_job")
        assert "not found" in result["message"].lower()

    def test_non_failed_job_rejected(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.COMPLETED)
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job):
            result = retry_job(db, "T_TEST", "job-1")
        _assert_result_shape(result, "failed", "retry_job")
        assert "failed" in result["message"].lower() or "status" in result["message"].lower()

    def test_successful_retry_calls_pipeline(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED)
        updated_job = _make_job(status=JobStatus.COMPLETED)

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event"), \
             patch("app.admin.recovery_actions.run_pipeline", return_value=updated_job) as mock_pipe:
            result = retry_job(db, "T_TEST", "job-1", actor="support-user")

        _assert_result_shape(result, "success", "retry_job")
        assert mock_pipe.called
        assert result["details"]["new_status"] is not None

    def test_audit_event_emitted_on_success(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED)
        updated_job = _make_job(status=JobStatus.COMPLETED)
        audit_calls = []

        def capture_audit(**kwargs):
            audit_calls.append(kwargs)

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event", side_effect=lambda **kw: audit_calls.append(kw)), \
             patch("app.admin.recovery_actions.run_pipeline", return_value=updated_job):
            retry_job(db, "T_TEST", "job-1")

        categories = [c.get("category") for c in audit_calls]
        assert "recovery" in categories

    def test_pipeline_exception_returns_failure(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED)

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event"), \
             patch("app.admin.recovery_actions.run_pipeline", side_effect=RuntimeError("boom")):
            result = retry_job(db, "T_TEST", "job-1")

        _assert_result_shape(result, "failed", "retry_job")

    def test_manual_review_job_is_retryable(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.MANUAL_REVIEW)
        updated_job = _make_job(status=JobStatus.COMPLETED)

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event"), \
             patch("app.admin.recovery_actions.run_pipeline", return_value=updated_job):
            result = retry_job(db, "T_TEST", "job-1")

        _assert_result_shape(result, "success", "retry_job")


# ---------------------------------------------------------------------------
# replay_dispatch
# ---------------------------------------------------------------------------

class TestReplayDispatch:
    def test_missing_job_returns_failure(self):
        db = _mock_db()
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
            result = replay_dispatch(db, "T_TEST", "missing")
        _assert_result_shape(result, "failed", "replay_dispatch")

    def test_successful_dispatch_replay(self):
        from app.workflows.dispatchers.base import DispatchResult
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED)
        dispatch_result = DispatchResult(status="success", system="monday", job_type="lead", message="Dispatched")

        # Mock record query
        mock_record = MagicMock()
        mock_record.job_type = "lead"
        db.query.return_value.filter.return_value.first.return_value = mock_record

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event"), \
             patch("app.admin.recovery_actions.get_settings", return_value=MagicMock()), \
             patch("app.admin.recovery_actions.get_tenant_config", return_value={"settings": {"memory": {}}}), \
             patch("app.admin.recovery_actions.ControlledDispatchEngine") as MockEngine:
            mock_instance = MockEngine.return_value
            mock_instance.run.return_value = dispatch_result
            result = replay_dispatch(db, "T_TEST", "job-1")

        _assert_result_shape(result, "success", "replay_dispatch")

    def test_dispatch_failure_propagated(self):
        from app.workflows.dispatchers.base import DispatchResult
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED)
        dispatch_result = DispatchResult(status="failed", system="monday", job_type="lead", message="No hint")

        mock_record = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_record

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event"), \
             patch("app.admin.recovery_actions.get_settings", return_value=MagicMock()), \
             patch("app.admin.recovery_actions.get_tenant_config", return_value={"settings": {"memory": {}}}), \
             patch("app.admin.recovery_actions.ControlledDispatchEngine") as MockEngine:
            mock_instance = MockEngine.return_value
            mock_instance.run.return_value = dispatch_result
            result = replay_dispatch(db, "T_TEST", "job-1")

        _assert_result_shape(result, "failed", "replay_dispatch")

    def test_idempotent_skipped_treated_as_ok(self):
        from app.workflows.dispatchers.base import DispatchResult
        db = _mock_db()
        job = _make_job(status=JobStatus.COMPLETED)
        dispatch_result = DispatchResult(status="skipped", system="monday", job_type="lead", message="Already dispatched")

        mock_record = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = mock_record

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event"), \
             patch("app.admin.recovery_actions.get_settings", return_value=MagicMock()), \
             patch("app.admin.recovery_actions.get_tenant_config", return_value={"settings": {"memory": {}}}), \
             patch("app.admin.recovery_actions.ControlledDispatchEngine") as MockEngine:
            mock_instance = MockEngine.return_value
            mock_instance.run.return_value = dispatch_result
            result = replay_dispatch(db, "T_TEST", "job-1")

        _assert_result_shape(result, "success", "replay_dispatch")


# ---------------------------------------------------------------------------
# reclassify
# ---------------------------------------------------------------------------

class TestReclassify:
    def test_missing_job(self):
        db = _mock_db()
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
            result = reclassify(db, "T_TEST", "x")
        _assert_result_shape(result, "failed", "reclassify")

    def test_reclassify_reruns_pipeline_and_returns_detected_type(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED, processor_history=[
            _classification_history_entry("invoice"),
        ])
        updated = _make_job(status=JobStatus.COMPLETED, processor_history=[
            _classification_history_entry("lead"),
        ])

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event"), \
             patch("app.admin.recovery_actions.run_pipeline", return_value=updated):
            result = reclassify(db, "T_TEST", "job-1")

        _assert_result_shape(result, "success", "reclassify")
        assert result["details"]["detected_job_type"] == "lead"

    def test_audit_category_is_recovery(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED)
        updated = _make_job(status=JobStatus.COMPLETED)
        audit_calls = []

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event", side_effect=lambda **kw: audit_calls.append(kw)), \
             patch("app.admin.recovery_actions.run_pipeline", return_value=updated):
            reclassify(db, "T_TEST", "job-1")

        assert all(c["category"] == "recovery" for c in audit_calls)


# ---------------------------------------------------------------------------
# re_extract
# ---------------------------------------------------------------------------

class TestReExtract:
    def test_missing_job(self):
        db = _mock_db()
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
            result = re_extract(db, "T_TEST", "x")
        _assert_result_shape(result, "failed", "re_extract")

    def test_no_classification_blocks_re_extract(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED, processor_history=[])
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job):
            result = re_extract(db, "T_TEST", "job-1")
        _assert_result_shape(result, "failed", "re_extract")
        assert "classification" in result["message"].lower()

    def test_re_extract_preserves_classification(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED, processor_history=[
            _intake_history_entry(),
            _classification_history_entry("lead"),
            {"processor": "entity_extraction_processor", "result": {"payload": {}}},
        ])
        updated = _make_job(status=JobStatus.COMPLETED, processor_history=[
            _intake_history_entry(),
            _classification_history_entry("lead"),
        ])

        captured_jobs = []

        def capture_pipeline(j, db_arg):
            captured_jobs.append(j)
            return updated

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event"), \
             patch("app.admin.recovery_actions.run_pipeline", side_effect=capture_pipeline):
            result = re_extract(db, "T_TEST", "job-1")

        _assert_result_shape(result, "success", "re_extract")
        # classification should be in the history passed to pipeline
        submitted = captured_jobs[0]
        assert any(e.get("processor") == "classification_processor" for e in submitted.processor_history)
        # entity_extraction should have been stripped
        assert not any(e.get("processor") == "entity_extraction_processor" for e in submitted.processor_history)


# ---------------------------------------------------------------------------
# resend_approval
# ---------------------------------------------------------------------------

class TestResendApproval:
    def test_missing_job(self):
        db = _mock_db()
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
            result = resend_approval(db, "T_TEST", "x")
        _assert_result_shape(result, "failed", "resend_approval")

    def test_no_pending_approval_returns_failure(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.AWAITING_APPROVAL)

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.ApprovalRequestRepository.get_latest_for_job", return_value=None):
            result = resend_approval(db, "T_TEST", "job-1")

        _assert_result_shape(result, "failed", "resend_approval")
        assert "no pending" in result["message"].lower()

    def test_rejected_approval_not_resent(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED)
        mock_approval = MagicMock()
        mock_approval.state = "rejected"
        mock_approval.approval_id = "appr-1"

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.ApprovalRequestRepository.get_latest_for_job", return_value=mock_approval):
            result = resend_approval(db, "T_TEST", "job-1")

        _assert_result_shape(result, "failed", "resend_approval")

    def test_pending_approval_clears_delivery_and_redispatches(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.AWAITING_APPROVAL, processor_history=[
            {
                "processor": "approval_dispatcher",
                "result": {"payload": {"approval_delivery": {"status": "sent"}}},
            }
        ])
        mock_approval = MagicMock()
        mock_approval.state = "pending"
        mock_approval.approval_id = "appr-1"
        updated_job = _make_job(status=JobStatus.AWAITING_APPROVAL)

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.ApprovalRequestRepository.get_latest_for_job", return_value=mock_approval), \
             patch("app.admin.recovery_actions.JobRepository.update_job", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event"), \
             patch("app.admin.recovery_actions.dispatch_approval_request", return_value=updated_job) as mock_dispatch:
            result = resend_approval(db, "T_TEST", "job-1")

        _assert_result_shape(result, "success", "resend_approval")
        assert mock_dispatch.called

    def test_delivery_metadata_is_cleared_before_dispatch(self):
        """Confirm the approval_delivery key is removed so re-dispatch actually fires."""
        db = _mock_db()
        job = _make_job(status=JobStatus.AWAITING_APPROVAL, processor_history=[
            {
                "processor": "approval_dispatcher",
                "result": {
                    "payload": {
                        "approval_request": {"approval_id": "appr-1"},
                        "approval_delivery": {"status": "sent", "channel": "dashboard"},
                    }
                },
            }
        ])
        mock_approval = MagicMock()
        mock_approval.state = "pending"
        mock_approval.approval_id = "appr-1"
        updated_job = _make_job(status=JobStatus.AWAITING_APPROVAL)

        captured_jobs = []

        def capture_update(db_arg, j):
            captured_jobs.append(j)
            return j

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.ApprovalRequestRepository.get_latest_for_job", return_value=mock_approval), \
             patch("app.admin.recovery_actions.JobRepository.update_job", side_effect=capture_update), \
             patch("app.admin.recovery_actions.create_audit_event"), \
             patch("app.admin.recovery_actions.dispatch_approval_request", return_value=updated_job):
            resend_approval(db, "T_TEST", "job-1")

        submitted = captured_jobs[0]
        dispatcher_entry = next(
            (e for e in submitted.processor_history if e.get("processor") == "approval_dispatcher"),
            None,
        )
        assert dispatcher_entry is not None
        payload = (dispatcher_entry.get("result") or {}).get("payload") or {}
        assert "approval_delivery" not in payload


# ---------------------------------------------------------------------------
# reprocess_gmail_source
# ---------------------------------------------------------------------------

class TestReprocessGmailSource:
    def test_missing_job(self):
        db = _mock_db()
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
            result = reprocess_gmail_source(db, "T_TEST", "x")
        _assert_result_shape(result, "failed", "reprocess_gmail_source")

    def test_non_gmail_job_rejected(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED, input_data={"source": {"system": "manual"}})
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job):
            result = reprocess_gmail_source(db, "T_TEST", "job-1")
        _assert_result_shape(result, "failed", "reprocess_gmail_source")
        assert "gmail" in result["message"].lower()

    def test_missing_message_id_rejected(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED, input_data={"source": {"system": "gmail"}})
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job):
            result = reprocess_gmail_source(db, "T_TEST", "job-1")
        _assert_result_shape(result, "failed", "reprocess_gmail_source")

    def test_gmail_fetch_error_returns_failure(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED, input_data={
            "source": {"system": "gmail", "message_id": "msg-123"}
        })
        mock_adapter = MagicMock()
        mock_adapter.execute_action.side_effect = RuntimeError("403 forbidden")

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event"), \
             patch("app.admin.recovery_actions.get_settings", return_value=MagicMock()), \
             patch("app.admin.recovery_actions.get_integration_connection_config", return_value={}), \
             patch("app.admin.recovery_actions.GoogleMailAdapter", return_value=mock_adapter):
            result = reprocess_gmail_source(db, "T_TEST", "job-1")

        _assert_result_shape(result, "failed", "reprocess_gmail_source")

    def test_successful_reprocess_calls_pipeline(self):
        db = _mock_db()
        job = _make_job(status=JobStatus.FAILED, input_data={
            "source": {"system": "gmail", "message_id": "msg-123"}
        })
        updated = _make_job(status=JobStatus.COMPLETED)
        mock_adapter = MagicMock()
        mock_adapter.execute_action.return_value = {
            "body_text": "Hello world",
            "from": "sender@example.com",
            "subject": "Test",
            "received_at": "2026-05-17T10:00:00Z",
        }

        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=job), \
             patch("app.admin.recovery_actions.create_audit_event"), \
             patch("app.admin.recovery_actions.get_settings", return_value=MagicMock()), \
             patch("app.admin.recovery_actions.get_integration_connection_config", return_value={}), \
             patch("app.admin.recovery_actions.GoogleMailAdapter", return_value=mock_adapter), \
             patch("app.admin.recovery_actions.run_pipeline", return_value=updated) as mock_pipe:
            result = reprocess_gmail_source(db, "T_TEST", "job-1")

        _assert_result_shape(result, "success", "reprocess_gmail_source")
        assert mock_pipe.called
        assert result["details"]["message_id"] == "msg-123"


# ---------------------------------------------------------------------------
# Tenant isolation tests
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    """Verify that each action cannot touch jobs from another tenant."""

    def test_retry_wrong_tenant_fails(self):
        """JobRepository returns None for wrong tenant — action must return failure."""
        db = _mock_db()
        # Repo will correctly return None when tenant doesn't match (by design)
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
            result = retry_job(db, "T_WRONG", "job-from-T_RIGHT")
        assert result["status"] == "failed"
        assert result["tenant_id"] == "T_WRONG"

    def test_reclassify_wrong_tenant_fails(self):
        db = _mock_db()
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
            result = reclassify(db, "T_WRONG", "job-from-T_RIGHT")
        assert result["status"] == "failed"

    def test_resend_approval_wrong_tenant_fails(self):
        db = _mock_db()
        with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
            result = resend_approval(db, "T_WRONG", "job-from-T_RIGHT")
        assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# HTTP endpoint auth tests (using TestClient)
# ---------------------------------------------------------------------------

class TestRecoveryEndpointAuth:
    """Test that admin recovery endpoints return 401 without X-Admin-API-Key."""

    def setup_method(self):
        import os
        os.environ.setdefault("ADMIN_API_KEY", "test-admin-key")

    def _client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_retry_requires_admin_key(self):
        client = self._client()
        resp = client.post(
            "/admin/recovery/job-1/retry",
            headers={"X-Tenant-ID": "T_TEST"},
            json={},
        )
        assert resp.status_code == 401

    def test_replay_dispatch_requires_admin_key(self):
        client = self._client()
        resp = client.post(
            "/admin/recovery/job-1/replay-dispatch",
            headers={"X-Tenant-ID": "T_TEST"},
            json={},
        )
        assert resp.status_code == 401

    def test_reclassify_requires_admin_key(self):
        client = self._client()
        resp = client.post(
            "/admin/recovery/job-1/reclassify",
            headers={"X-Tenant-ID": "T_TEST"},
            json={},
        )
        assert resp.status_code == 401

    def test_re_extract_requires_admin_key(self):
        client = self._client()
        resp = client.post(
            "/admin/recovery/job-1/re-extract",
            headers={"X-Tenant-ID": "T_TEST"},
            json={},
        )
        assert resp.status_code == 401

    def test_resend_approval_requires_admin_key(self):
        client = self._client()
        resp = client.post(
            "/admin/recovery/job-1/resend-approval",
            headers={"X-Tenant-ID": "T_TEST"},
            json={},
        )
        assert resp.status_code == 401

    def test_reprocess_gmail_requires_admin_key(self):
        client = self._client()
        resp = client.post(
            "/admin/recovery/job-1/reprocess-gmail",
            headers={"X-Tenant-ID": "T_TEST"},
            json={},
        )
        assert resp.status_code == 401

    def test_retry_with_valid_admin_key_passes_auth(self):
        """With valid admin key the endpoint processes the request (may return 404/failure for missing job)."""
        import os
        key = "test-admin-key-for-test"
        with patch.dict(os.environ, {"ADMIN_API_KEY": key}):
            from app.core import settings as _settings_mod
            # Force settings reload with new env value
            with patch("app.core.admin_auth.get_settings") as mock_gs:
                mock_gs.return_value.ADMIN_API_KEY = key
                with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
                    client = self._client()
                    resp = client.post(
                        "/admin/recovery/job-1/retry",
                        headers={"X-Admin-API-Key": key, "X-Tenant-ID": "T_TEST"},
                        json={},
                    )
        # Should not be 401 — auth passed, job not found → 200 with {status: failed}
        assert resp.status_code != 401
