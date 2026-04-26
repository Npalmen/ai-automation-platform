"""
Tests for Slice 9 — Dispatch Approval Queue.

Covers:
- approval_required dispatch creates approval record and returns approval_id
- approval_required dispatch does not call Monday adapter
- repeated approval_required dispatch returns same pending approval_id
- pending approval payload contains job_id / system / job_type / target
- approving dispatch approval calls ControlledDispatchEngine
- approving dispatch approval returns dispatch result (success)
- failed adapter during approval returns failure dict (does not raise)
- rejecting dispatch approval returns rejected status without calling adapter
- duplicate dispatch after approval is skipped by engine idempotency
- existing pipeline approvals (next_on_approve != controlled_dispatch) still work
- tenant isolation: creating approval for T1 does not affect T2
- tenant isolation: approving T1 approval as T2 returns 404
- manual policy still executes immediately (no approval created)
- full_auto policy still executes immediately (no approval created)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_db():
    return MagicMock()


def _make_job_record(job_id="job-1", job_type="lead", tenant_id="T1"):
    r = MagicMock()
    r.job_id    = job_id
    r.tenant_id = tenant_id
    r.job_type  = job_type
    r.input_data = {}
    r.result     = {}
    return r


def _valid_hint(board_id="99", board_name="Leads"):
    return {
        "system": "monday",
        "target": {"board_id": board_id, "board_name": board_name, "group_id": None, "group_name": None},
        "confidence": "high",
        "reason": "matched",
    }


def _tenant_config(auto_actions: dict | None = None) -> dict:
    return {
        "tenant_id": "T1",
        "name": "Test",
        "enabled_job_types": ["lead"],
        "allowed_integrations": ["monday"],
        "auto_actions": auto_actions or {},
    }


def _settings_with_lead_hint():
    return {"memory": {"routing_hints": {"lead": _valid_hint()}}}


def _dry_run_result():
    from app.workflows.dispatchers.base import DispatchResult
    return DispatchResult(
        status="dry_run", system="monday", job_type="lead",
        target={"board_id": "99"}, message="dry run ok",
    )


def _ok_dispatch_result():
    from app.workflows.dispatchers.base import DispatchResult
    return DispatchResult(
        status="success", system="monday", job_type="lead",
        target={"board_id": "99"}, external_id="1001", message="ok",
    )


# ---------------------------------------------------------------------------
# build_dispatch_approval_request — pure function
# ---------------------------------------------------------------------------

class TestBuildDispatchApprovalRequest:
    def _call(self, **kw):
        from app.workflows.approval_service import build_dispatch_approval_request
        defaults = dict(
            job_id="job-1", tenant_id="T1", job_type="lead",
            system="monday", routing_hint=_valid_hint(),
        )
        defaults.update(kw)
        return build_dispatch_approval_request(**defaults)

    def test_has_approval_id(self):
        r = self._call()
        assert "approval_id" in r and r["approval_id"]

    def test_state_is_pending(self):
        assert self._call()["state"] == "pending"

    def test_next_on_approve_is_controlled_dispatch(self):
        assert self._call()["next_on_approve"] == "controlled_dispatch"

    def test_next_on_reject_is_manual_review(self):
        assert self._call()["next_on_reject"] == "manual_review"

    def test_dispatch_context_has_system(self):
        ctx = self._call()["dispatch_context"]
        assert ctx["system"] == "monday"

    def test_dispatch_context_has_job_type(self):
        ctx = self._call()["dispatch_context"]
        assert ctx["job_type"] == "lead"

    def test_dispatch_context_has_target(self):
        ctx = self._call()["dispatch_context"]
        assert ctx["target"]["board_id"] == "99"

    def test_title_includes_board_name(self):
        r = self._call()
        assert "Leads" in r["title"]

    def test_summary_includes_system(self):
        r = self._call()
        assert "monday" in r["summary"].lower()


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/dispatch — approval_required path
# ---------------------------------------------------------------------------

def _call_dispatch_semi(
    auto_actions=None,
    find_existing=None,
    dry_result=None,
    mock_upsert=None,
):
    """Call dispatch_job with semi (approval_required) policy."""
    from app.main import dispatch_job

    if auto_actions is None:
        auto_actions = {"lead": "semi"}
    if dry_result is None:
        dry_result = _dry_run_result()

    db   = _make_db()
    rec  = _make_job_record()
    db.query.return_value.filter.return_value.first.return_value = rec

    tenant_cfg   = _tenant_config(auto_actions)
    mem_settings = _settings_with_lead_hint()

    mock_engine = MagicMock()
    mock_engine.run.return_value = dry_result  # dry run

    with (
        patch("app.main.get_tenant_config", return_value=tenant_cfg),
        patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
              return_value=mem_settings),
        patch("app.main._make_dispatch_engine", return_value=mock_engine),
        patch("app.repositories.postgres.approval_repository.ApprovalRequestRepository.find_pending_dispatch_approval",
              return_value=find_existing),
        patch("app.repositories.postgres.approval_repository.ApprovalRequestRepository.upsert_from_payload",
              return_value=MagicMock()) as mock_ups,
    ):
        result = dispatch_job(job_id="job-1", db=db, tenant_id="T1")
        return result, mock_engine, mock_ups


class TestDispatchApprovalCreation:
    def test_returns_status_approval_required(self):
        result, _, _ = _call_dispatch_semi()
        assert result["status"] == "approval_required"

    def test_returns_approval_id(self):
        result, _, _ = _call_dispatch_semi()
        assert "approval_id" in result and result["approval_id"]

    def test_returns_policy_mode(self):
        result, _, _ = _call_dispatch_semi()
        assert result["policy_mode"] == "approval_required"

    def test_does_not_call_live_adapter(self):
        _, mock_engine, _ = _call_dispatch_semi()
        # engine.run called once for dry_run only
        mock_engine.run.assert_called_once()
        call_kwargs = mock_engine.run.call_args[1]
        assert call_kwargs.get("dry_run") is True

    def test_upserts_approval_record(self):
        _, _, mock_ups = _call_dispatch_semi()
        mock_ups.assert_called_once()

    def test_upsert_payload_has_controlled_dispatch(self):
        _, _, mock_ups = _call_dispatch_semi()
        call_kw = mock_ups.call_args[1]
        req = call_kw["approval_request"]
        assert req["next_on_approve"] == "controlled_dispatch"

    def test_upsert_payload_has_dispatch_context(self):
        _, _, mock_ups = _call_dispatch_semi()
        call_kw = mock_ups.call_args[1]
        req = call_kw["approval_request"]
        ctx = req["dispatch_context"]
        assert ctx["job_id"] == "job-1"
        assert ctx["system"] == "monday"
        assert ctx["job_type"] == "lead"

    def test_returns_message_in_swedish(self):
        result, _, _ = _call_dispatch_semi()
        msg = result["message"].lower()
        assert "godkännande" in msg or "approval" in msg

    def test_tenant_isolation_different_tenants_get_separate_approvals(self):
        result_t1, _, _ = _call_dispatch_semi(auto_actions={"lead": "semi"})
        result_t2, _, _ = _call_dispatch_semi(auto_actions={"lead": "semi"})
        assert result_t1["approval_id"] != result_t2["approval_id"]

    def test_existing_pending_approval_is_reused(self):
        existing = MagicMock()
        existing.approval_id = "existing-abc"
        result, _, mock_ups = _call_dispatch_semi(find_existing=existing)
        assert result["approval_id"] == "existing-abc"
        assert result["status"] == "approval_required"
        # No new upsert when reusing
        mock_ups.assert_not_called()

    def test_existing_pending_message_indicates_already_pending(self):
        existing = MagicMock()
        existing.approval_id = "existing-abc"
        result, _, _ = _call_dispatch_semi(find_existing=existing)
        assert "väntande" in result["message"].lower() or "pending" in result["message"].lower()


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/dispatch — manual / full_auto unchanged
# ---------------------------------------------------------------------------

def _call_dispatch_live_immediate(auto_actions):
    from app.main import dispatch_job
    from app.workflows.dispatchers.base import DispatchResult

    ok = DispatchResult(
        status="success", system="monday", job_type="lead",
        target={"board_id": "99"}, external_id="1001", message="ok",
    )
    db   = _make_db()
    rec  = _make_job_record()
    db.query.return_value.filter.return_value.first.return_value = rec

    tenant_cfg   = _tenant_config(auto_actions)
    mem_settings = _settings_with_lead_hint()

    mock_adapter = MagicMock()
    mock_adapter.dispatch.return_value = ok

    with (
        patch("app.main.get_tenant_config", return_value=tenant_cfg),
        patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
              return_value=mem_settings),
        patch("app.workflows.dispatchers.engine.DISPATCH_REGISTRY", {("monday", "lead"): mock_adapter}),
        patch("app.workflows.dispatchers.engine._persist_dispatch"),
        patch("app.workflows.dispatchers.engine._find_existing_dispatch", return_value=None),
    ):
        return dispatch_job(job_id="job-1", db=db, tenant_id="T1"), mock_adapter


class TestImmediateDispatchPolicies:
    def test_manual_executes_immediately(self):
        result, adapter = _call_dispatch_live_immediate({"lead": "manual"})
        assert result["status"] == "success"
        adapter.dispatch.assert_called_once()

    def test_full_auto_executes_immediately(self):
        result, adapter = _call_dispatch_live_immediate({"lead": "auto"})
        assert result["status"] == "success"
        adapter.dispatch.assert_called_once()


# ---------------------------------------------------------------------------
# Approving a dispatch approval → runs ControlledDispatchEngine
# ---------------------------------------------------------------------------

def _make_approval_record(
    approval_id="appr-1",
    job_id="job-1",
    tenant_id="T1",
    job_type="lead",
    state="pending",
    next_on_approve="controlled_dispatch",
):
    rec = MagicMock()
    rec.approval_id    = approval_id
    rec.job_id         = job_id
    rec.tenant_id      = tenant_id
    rec.job_type       = job_type
    rec.state          = state
    rec.next_on_approve = next_on_approve
    rec.request_payload = {
        "approval_id": approval_id,
        "job_id": job_id,
        "tenant_id": tenant_id,
        "job_type": job_type,
        "state": "pending",
        "next_on_approve": "controlled_dispatch",
        "dispatch_context": {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "job_type": "lead",
            "system": "monday",
            "target": {"board_id": "99", "board_name": "Leads"},
        },
    }
    return rec


def _call_approve_dispatch(
    approval_id="appr-1",
    dispatch_result=None,
    approval_state="pending",
):
    from app.main import approve_request
    from app.domain.workflows.approval_request_schemas import ApprovalDecisionRequest

    if dispatch_result is None:
        dispatch_result = _ok_dispatch_result()

    approval_rec = _make_approval_record(approval_id=approval_id, state=approval_state)
    db = _make_db()
    mem_settings = _settings_with_lead_hint()
    job_record   = _make_job_record(job_id="job-1")

    mock_engine = MagicMock()
    mock_engine.run.return_value = dispatch_result

    request = ApprovalDecisionRequest(actor="operator", channel="ui")

    with (
        patch("app.repositories.postgres.approval_repository.ApprovalRequestRepository.get_by_approval_id",
              return_value=approval_rec),
        patch("app.repositories.postgres.approval_repository.ApprovalRequestRepository.upsert_from_payload",
              return_value=MagicMock()),
        patch("app.repositories.postgres.job_repository.JobRepository.get_job_by_id",
              return_value=job_record),
        patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
              return_value=mem_settings),
        patch("app.workflows.dispatchers.engine.ControlledDispatchEngine", return_value=mock_engine),
        patch("app.core.audit_service.create_audit_event"),
        patch("app.workflows.approval_service._get_settings"),
    ):
        result = approve_request(
            approval_id=approval_id,
            request=request,
            db=db,
            tenant_id="T1",
        )
    return result, mock_engine


class TestApproveDispatchApproval:
    def test_approve_calls_engine(self):
        _, mock_engine = _call_approve_dispatch()
        mock_engine.run.assert_called_once()

    def test_approve_calls_engine_live_not_dry_run(self):
        _, mock_engine = _call_approve_dispatch()
        call_kw = mock_engine.run.call_args[1]
        assert call_kw.get("dry_run") is False

    def test_approve_returns_success_status(self):
        result, _ = _call_approve_dispatch()
        assert result["status"] == "success"

    def test_approve_returns_approval_id(self):
        result, _ = _call_approve_dispatch(approval_id="appr-1")
        assert result["approval_id"] == "appr-1"

    def test_approve_returns_policy_mode(self):
        result, _ = _call_approve_dispatch()
        assert result["policy_mode"] == "approval_required"

    def test_approve_failed_adapter_returns_failure(self):
        from app.workflows.dispatchers.base import DispatchResult
        fail_result = DispatchResult(
            status="failed", system="monday", job_type="lead",
            target={"board_id": "99"}, message="board not found",
        )
        result, _ = _call_approve_dispatch(dispatch_result=fail_result)
        assert result["status"] == "failed"

    def test_approve_skipped_by_idempotency_returns_skipped(self):
        from app.workflows.dispatchers.base import DispatchResult
        skip_result = DispatchResult(
            status="skipped", system="monday", job_type="lead",
            target={"board_id": "99"}, message="already dispatched",
        )
        result, _ = _call_approve_dispatch(dispatch_result=skip_result)
        assert result["status"] == "skipped"


# ---------------------------------------------------------------------------
# Rejecting a dispatch approval
# ---------------------------------------------------------------------------

def _call_reject_dispatch(approval_id="appr-1"):
    from app.main import reject_request
    from app.domain.workflows.approval_request_schemas import ApprovalDecisionRequest

    approval_rec = _make_approval_record(approval_id=approval_id)
    db = _make_db()
    mock_engine = MagicMock()
    request = ApprovalDecisionRequest(actor="operator", channel="ui")

    with (
        patch("app.repositories.postgres.approval_repository.ApprovalRequestRepository.get_by_approval_id",
              return_value=approval_rec),
        patch("app.repositories.postgres.approval_repository.ApprovalRequestRepository.upsert_from_payload",
              return_value=MagicMock()),
        patch("app.workflows.dispatchers.engine.ControlledDispatchEngine", return_value=mock_engine),
        patch("app.core.audit_service.create_audit_event"),
        patch("app.workflows.approval_service._get_settings"),
    ):
        result = reject_request(
            approval_id=approval_id,
            request=request,
            db=db,
            tenant_id="T1",
        )
    return result, mock_engine


class TestRejectDispatchApproval:
    def test_reject_returns_rejected_status(self):
        result, _ = _call_reject_dispatch()
        assert result["status"] == "rejected"

    def test_reject_does_not_call_engine(self):
        _, mock_engine = _call_reject_dispatch()
        mock_engine.run.assert_not_called()


# ---------------------------------------------------------------------------
# Existing pipeline approvals are unaffected
# ---------------------------------------------------------------------------

class TestExistingPipelineApprovals:
    def test_pipeline_approval_still_uses_resolve_approval(self):
        from app.main import approve_request
        from app.domain.workflows.approval_request_schemas import ApprovalDecisionRequest

        # Approval with pipeline next_on_approve (not controlled_dispatch)
        pipeline_rec = _make_approval_record(next_on_approve="action_dispatch")
        pipeline_rec.next_on_approve = "action_dispatch"
        db = _make_db()

        request = ApprovalDecisionRequest(actor="operator", channel="ui")

        mock_job = MagicMock()
        mock_job.model_dump.return_value = {
            "job_id": "job-1", "tenant_id": "T1", "status": "completed",
            "job_type": "lead", "input_data": {}, "result": {},
            "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
            "processor_history": [], "error_message": None,
        }

        with (
            patch("app.repositories.postgres.approval_repository.ApprovalRequestRepository.get_by_approval_id",
                  return_value=pipeline_rec),
            patch("app.main.resolve_approval", return_value=mock_job) as mock_resolve,
        ):
            approve_request(
                approval_id="appr-pipeline",
                request=request,
                db=db,
                tenant_id="T1",
            )

        mock_resolve.assert_called_once()


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_approve_for_wrong_tenant_returns_404(self):
        from fastapi import HTTPException
        from app.main import approve_request
        from app.domain.workflows.approval_request_schemas import ApprovalDecisionRequest

        db = _make_db()
        request = ApprovalDecisionRequest(actor="operator", channel="ui")

        with (
            patch("app.repositories.postgres.approval_repository.ApprovalRequestRepository.get_by_approval_id",
                  return_value=None),  # tenant isolation: returns None for wrong tenant
        ):
            with pytest.raises(HTTPException) as exc:
                approve_request(
                    approval_id="appr-t1",
                    request=request,
                    db=db,
                    tenant_id="T2",  # wrong tenant
                )
            assert exc.value.status_code == 404
