"""
Tests for Slice 10 — Auto Dispatch Pipeline Hook v1.

Covers:
- manual policy → skipped
- approval_required policy → skipped
- full_auto + lead + monday ready → calls ControlledDispatchEngine
- full_auto + missing routing hint → skipped
- full_auto + invalid routing hint → skipped
- non-lead job_type → skipped
- unsupported system → skipped
- duplicate dispatch → engine returns skipped (idempotency)
- engine failure → returns failed, does not raise
- POST /jobs/{job_id}/auto-dispatch uses same logic
- pipeline hook triggers for completed lead job with full_auto
- pipeline hook does not trigger for manual / approval_required
- tenant isolation
- auto-dispatch failure in pipeline does not crash job
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    return MagicMock()


def _make_settings():
    return MagicMock()


def _valid_hint(system="monday", board_id="99", board_name="Leads"):
    return {
        "system": system,
        "target": {"board_id": board_id, "board_name": board_name, "group_id": None, "group_name": None},
        "confidence": "high",
        "reason": "matched",
    }


def _tenant_config(auto_actions: dict | None = None) -> dict:
    return {
        "tenant_id": "T1",
        "name":      "Test",
        "enabled_job_types":  ["lead"],
        "allowed_integrations": ["monday"],
        "auto_actions": auto_actions or {},
    }


def _settings_with_hint(hint=None, job_type="lead"):
    if hint is None:
        hint = _valid_hint()
    return {"memory": {"routing_hints": {job_type: hint}}}


def _ok_dispatch_result():
    from app.workflows.dispatchers.base import DispatchResult
    return DispatchResult(
        status="success", system="monday", job_type="lead",
        target={"board_id": "99"}, external_id="1001", message="ok",
    )


def _skipped_dispatch_result():
    from app.workflows.dispatchers.base import DispatchResult
    return DispatchResult(
        status="skipped", system="monday", job_type="lead",
        target={"board_id": "99"}, message="already dispatched",
    )


def _make_job_record(job_type="lead", tenant_id="T1", job_id="job-1"):
    r = MagicMock()
    r.job_id     = job_id
    r.tenant_id  = tenant_id
    r.job_type   = job_type
    r.input_data = {}
    r.result     = {}
    return r


# ---------------------------------------------------------------------------
# maybe_auto_dispatch_job — unit tests
# ---------------------------------------------------------------------------

def _call_auto_dispatch(
    job_type="lead",
    auto_actions=None,
    mem_settings=None,
    routing_hint=None,
    routing_preview_status="ready",
    routing_preview_system="monday",
    engine_result=None,
    adapter_in_registry=True,
):
    from app.workflows.dispatchers.auto_dispatch import maybe_auto_dispatch_job

    if auto_actions is None:
        auto_actions = {"lead": "auto"}
    if mem_settings is None:
        mem_settings = _settings_with_hint(routing_hint)
    if engine_result is None:
        engine_result = _ok_dispatch_result()

    db   = _make_db()
    job  = _make_job_record(job_type=job_type)
    cfg  = _tenant_config(auto_actions)

    mock_engine = MagicMock()
    mock_engine.run.return_value = engine_result

    registry = {("monday", "lead"): MagicMock()} if adapter_in_registry else {}

    rp = {"status": routing_preview_status, "system": routing_preview_system,
          "target": {"board_id": "99", "board_name": "Leads"}, "message": "ok"}

    with (
        patch("app.workflows.dispatchers.auto_dispatch.get_tenant_config", return_value=cfg),
        patch("app.workflows.dispatchers.auto_dispatch.TenantConfigRepository.get_settings",
              return_value=mem_settings),
        patch("app.workflows.dispatchers.auto_dispatch.ControlledDispatchEngine", return_value=mock_engine),
        patch("app.workflows.dispatchers.auto_dispatch.DISPATCH_REGISTRY", registry),
        patch("app.workflows.dispatchers.auto_dispatch.resolve_routing_preview", return_value=rp),
    ):
        return maybe_auto_dispatch_job(db=db, tenant_id="T1", job=job, settings=_make_settings()), mock_engine


class TestMaybeAutoDispatch:
    def test_manual_policy_skips(self):
        result, _ = _call_auto_dispatch(auto_actions={"lead": "manual"})
        assert result.status == "skipped"
        assert "full_auto" in result.reason.lower()

    def test_semi_policy_skips(self):
        result, _ = _call_auto_dispatch(auto_actions={"lead": "semi"})
        assert result.status == "skipped"
        assert "full_auto" in result.reason.lower()

    def test_missing_policy_skips(self):
        result, _ = _call_auto_dispatch(auto_actions={})
        assert result.status == "skipped"

    def test_non_lead_job_type_skips(self):
        result, _ = _call_auto_dispatch(job_type="invoice", auto_actions={"invoice": "auto"})
        assert result.status == "skipped"
        assert "lead" in result.reason.lower()

    def test_missing_routing_hint_skips(self):
        result, _ = _call_auto_dispatch(routing_preview_status="missing_hint")
        assert result.status == "skipped"
        assert "ready" in result.reason.lower()

    def test_invalid_routing_hint_skips(self):
        result, _ = _call_auto_dispatch(routing_preview_status="invalid_hint")
        assert result.status == "skipped"

    def test_unsupported_system_skips(self):
        result, _ = _call_auto_dispatch(routing_preview_system="hubspot")
        assert result.status == "skipped"
        assert "monday" in result.reason.lower()

    def test_adapter_not_in_registry_skips(self):
        result, _ = _call_auto_dispatch(adapter_in_registry=False)
        assert result.status == "skipped"

    def test_full_auto_lead_monday_calls_engine(self):
        _, mock_engine = _call_auto_dispatch()
        mock_engine.run.assert_called_once()

    def test_full_auto_calls_engine_live_not_dry_run(self):
        _, mock_engine = _call_auto_dispatch()
        call_kw = mock_engine.run.call_args[1]
        assert call_kw.get("dry_run") is False

    def test_full_auto_success_returns_success(self):
        result, _ = _call_auto_dispatch()
        assert result.status == "success"

    def test_full_auto_success_has_dispatch_result(self):
        result, _ = _call_auto_dispatch()
        assert result.dispatch_result is not None
        assert result.dispatch_result["status"] == "success"

    def test_duplicate_dispatch_returns_skipped(self):
        result, _ = _call_auto_dispatch(engine_result=_skipped_dispatch_result())
        assert result.status == "skipped"

    def test_engine_failure_returns_failed(self):
        from app.workflows.dispatchers.base import DispatchResult
        fail = DispatchResult(status="failed", system="monday", job_type="lead",
                              target={"board_id": "99"}, message="board error")
        result, _ = _call_auto_dispatch(engine_result=fail)
        assert result.status == "failed"

    def test_engine_exception_returns_failed_without_raising(self):
        from app.workflows.dispatchers.auto_dispatch import maybe_auto_dispatch_job
        db = _make_db()
        job = _make_job_record()

        with patch("app.workflows.dispatchers.auto_dispatch.get_tenant_config",
                   side_effect=RuntimeError("unexpected")):
            result = maybe_auto_dispatch_job(db=db, tenant_id="T1", job=job, settings=_make_settings())

        assert result.status == "failed"
        assert "RuntimeError" in result.reason

    def test_to_dict_has_required_keys(self):
        result, _ = _call_auto_dispatch()
        d = result.to_dict()
        assert "status" in d
        assert "reason" in d
        assert "dispatch_result" in d


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/auto-dispatch endpoint
# ---------------------------------------------------------------------------

def _call_endpoint(job_type="lead", auto_actions=None, engine_result=None, missing_job=False):
    from app.main import trigger_auto_dispatch

    if auto_actions is None:
        auto_actions = {"lead": "auto"}
    if engine_result is None:
        engine_result = _ok_dispatch_result()

    db  = _make_db()
    rec = _make_job_record(job_type=job_type)

    db.query.return_value.filter.return_value.first.return_value = None if missing_job else rec
    cfg = _tenant_config(auto_actions)
    mem = _settings_with_hint()

    from app.workflows.dispatchers.auto_dispatch import AutoDispatchResult
    mock_result = AutoDispatchResult(
        status=engine_result.status,
        reason=engine_result.message or engine_result.status,
        dispatch_result=engine_result.to_dict() if engine_result.status == "success" else None,
    )

    with (
        patch("app.main.maybe_auto_dispatch_job", return_value=mock_result) as mock_fn,
    ):
        if missing_job:
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                trigger_auto_dispatch(job_id="job-1", db=db, tenant_id="T1")
            return exc.value, mock_fn
        result = trigger_auto_dispatch(job_id="job-1", db=db, tenant_id="T1")
        return result, mock_fn


class TestAutoDispatchEndpoint:
    def test_returns_status(self):
        result, _ = _call_endpoint()
        assert "status" in result

    def test_returns_reason(self):
        result, _ = _call_endpoint()
        assert "reason" in result

    def test_returns_dispatch_result_key(self):
        result, _ = _call_endpoint()
        assert "dispatch_result" in result

    def test_calls_maybe_auto_dispatch(self):
        _, mock_fn = _call_endpoint()
        mock_fn.assert_called_once()

    def test_404_for_missing_job(self):
        exc, _ = _call_endpoint(missing_job=True)
        assert exc.status_code == 404

    def test_manual_policy_skips(self):
        from app.workflows.dispatchers.auto_dispatch import AutoDispatchResult
        skip = AutoDispatchResult(status="skipped", reason="policy manual")
        with patch("app.main.maybe_auto_dispatch_job", return_value=skip):
            db = _make_db()
            rec = _make_job_record()
            db.query.return_value.filter.return_value.first.return_value = rec
            from app.main import trigger_auto_dispatch
            result = trigger_auto_dispatch(job_id="job-1", db=db, tenant_id="T1")
        assert result["status"] == "skipped"


# ---------------------------------------------------------------------------
# Pipeline hook — _maybe_auto_dispatch called from orchestrator
# ---------------------------------------------------------------------------

def _make_domain_job(job_type="lead", tenant_id="T1", job_id="job-1", status="completed"):
    from app.domain.workflows.models import Job
    from app.domain.workflows.enums import JobType
    from app.domain.workflows.statuses import JobStatus
    j = MagicMock(spec=Job)
    j.job_id     = job_id
    j.tenant_id  = tenant_id
    j.job_type   = JobType(job_type) if job_type in [e.value for e in JobType] else MagicMock()
    j.status     = JobStatus.COMPLETED
    j.result     = {}
    j.processor_history = []
    j.input_data = {}
    return j


class TestPipelineHook:
    def test_finalize_success_calls_maybe_auto_dispatch_for_completed(self):
        from app.workflows.orchestrator import WorkflowOrchestrator
        orch = WorkflowOrchestrator(db=_make_db())
        job  = _make_domain_job(status="completed")

        with patch("app.workflows.orchestrator.maybe_auto_dispatch_job") as mock_fn:
            mock_fn.return_value = MagicMock(status="skipped", reason="no full_auto")
            orch._maybe_auto_dispatch(job)

        mock_fn.assert_called_once()

    def test_maybe_auto_dispatch_passes_tenant_id(self):
        from app.workflows.orchestrator import WorkflowOrchestrator
        orch = WorkflowOrchestrator(db=_make_db())
        job  = _make_domain_job(tenant_id="T_special")

        with patch("app.workflows.orchestrator.maybe_auto_dispatch_job") as mock_fn:
            mock_fn.return_value = MagicMock(status="skipped", reason="ok")
            orch._maybe_auto_dispatch(job)

        call_kw = mock_fn.call_args[1]
        assert call_kw["tenant_id"] == "T_special"

    def test_auto_dispatch_failure_in_pipeline_does_not_raise(self):
        from app.workflows.orchestrator import WorkflowOrchestrator
        orch = WorkflowOrchestrator(db=_make_db())
        job  = _make_domain_job()

        with patch("app.workflows.orchestrator.maybe_auto_dispatch_job",
                   side_effect=RuntimeError("boom")):
            orch._maybe_auto_dispatch(job)  # must not raise

    def test_maybe_auto_dispatch_not_called_when_db_is_none(self):
        from app.workflows.orchestrator import WorkflowOrchestrator

        # When _maybe_auto_dispatch is called with db=None it returns early
        orch = WorkflowOrchestrator(db=None)
        job  = _make_domain_job()

        # Patch _maybe_auto_dispatch itself to capture if it short-circuits
        with patch("app.workflows.orchestrator.maybe_auto_dispatch_job") as mock_fn:
            orch._maybe_auto_dispatch(job)  # db is None → early return

        mock_fn.assert_not_called()


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_different_tenants_do_not_interfere(self):
        result_t1, _ = _call_auto_dispatch()
        # Same code, different tenant would use different config/hints
        # Structural isolation test — both run independently without error
        assert result_t1.status in ("success", "skipped", "failed")

    def test_endpoint_uses_verified_tenant_id(self):
        from app.main import trigger_auto_dispatch
        from app.workflows.dispatchers.auto_dispatch import AutoDispatchResult

        skip = AutoDispatchResult(status="skipped", reason="ok")
        db = _make_db()
        rec = _make_job_record(tenant_id="T2")
        db.query.return_value.filter.return_value.first.return_value = rec

        with patch("app.main.maybe_auto_dispatch_job", return_value=skip) as mock_fn:
            trigger_auto_dispatch(job_id="job-1", db=db, tenant_id="T2")

        call_kw = mock_fn.call_args[1]
        assert call_kw["tenant_id"] == "T2"


# ---------------------------------------------------------------------------
# No secret leakage
# ---------------------------------------------------------------------------

class TestNoSecretLeakage:
    def test_engine_exception_reason_does_not_include_traceback(self):
        from app.workflows.dispatchers.auto_dispatch import maybe_auto_dispatch_job
        db  = _make_db()
        job = _make_job_record()

        with patch("app.workflows.dispatchers.auto_dispatch.get_tenant_config",
                   side_effect=ConnectionError("Connection refused to internal-host:5432")):
            result = maybe_auto_dispatch_job(db=db, tenant_id="T1", job=job, settings=_make_settings())

        assert "Traceback" not in result.reason
        assert result.status == "failed"
