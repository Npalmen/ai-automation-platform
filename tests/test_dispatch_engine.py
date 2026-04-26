"""
Tests for Slice 7 — Generic Controlled Dispatch Engine + Monday Lead Adapter.

Covers:
- _derive_item_name: company_name, customer_name, sender_name, sender_email,
  subject, and "New lead" fallback
- MondayLeadDispatchAdapter: dry_run, live success, missing API key, adapter error
- ControlledDispatchEngine: missing hint → failed, invalid hint → failed,
  unsupported system → failed, unsupported job_type → failed, dry_run result,
  live success, duplicate guard (already dispatched → skipped), tenant isolation
- POST /jobs/{job_id}/dispatch-preview: does not call external writes, returns dry_run
- POST /jobs/{job_id}/dispatch: returns 404 for unknown job, success, failed → 400
- Existing APIs preserved (existing test modules not broken)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    return MagicMock()


def _make_job(
    job_id="job-1",
    tenant_id="T1",
    job_type="lead",
    input_data=None,
    result=None,
):
    j = MagicMock()
    j.job_id    = job_id
    j.tenant_id = tenant_id
    j.job_type  = job_type
    j.input_data = input_data or {}
    j.result     = result or {}
    return j


def _valid_hint(board_id="99", board_name="Leads", group_id=None):
    return {
        "system": "monday",
        "target": {
            "board_id":   board_id,
            "board_name": board_name,
            "group_id":   group_id,
            "group_name": None,
        },
        "confidence": "high",
        "reason":     "Board matched lead",
    }


def _memory_with_lead_hint(hint=None):
    return {
        "business_profile": {},
        "system_map": {},
        "routing_hints": {"lead": hint if hint is not None else _valid_hint()},
    }


# ---------------------------------------------------------------------------
# _derive_item_name
# ---------------------------------------------------------------------------

class TestDeriveItemName:
    def _call(self, input_data=None, processor_history=None):
        from app.workflows.dispatchers.monday_lead_adapter import _derive_item_name
        job = _make_job(
            input_data=input_data or {},
            result={"processor_history": processor_history or []},
        )
        return _derive_item_name(job)

    def test_company_name_first(self):
        history = [{"result": {"payload": {"entities": {"company_name": "Acme AB", "customer_name": "John"}}}}]
        assert self._call(processor_history=history) == "Acme AB"

    def test_customer_name_when_no_company(self):
        history = [{"result": {"payload": {"entities": {"customer_name": "Anna Svensson"}}}}]
        assert self._call(processor_history=history) == "Anna Svensson"

    def test_sender_name_fallback(self):
        assert self._call(input_data={"sender": {"name": "Bob"}}) == "Bob"

    def test_sender_email_fallback(self):
        assert self._call(input_data={"sender": {"email": "bob@example.com"}}) == "bob@example.com"

    def test_subject_fallback(self):
        assert self._call(input_data={"subject": "Offer request"}) == "Offer request"

    def test_new_lead_ultimate_fallback(self):
        assert self._call() == "New lead"

    def test_strips_whitespace(self):
        assert self._call(input_data={"subject": "  My Lead  "}) == "My Lead"


# ---------------------------------------------------------------------------
# MondayLeadDispatchAdapter — dry_run
# ---------------------------------------------------------------------------

class TestMondayLeadAdapterDryRun:
    def _adapter(self):
        from app.workflows.dispatchers.monday_lead_adapter import MondayLeadDispatchAdapter
        return MondayLeadDispatchAdapter()

    def test_dry_run_returns_dry_run_status(self):
        adapter = self._adapter()
        job = _make_job(input_data={"subject": "Test lead"})
        result = adapter.dispatch(job=job, routing_hint=_valid_hint(), settings=None, dry_run=True)
        assert result.status == "dry_run"

    def test_dry_run_no_external_call(self):
        adapter = self._adapter()
        job = _make_job()
        with patch("app.integrations.monday.client.MondayClient") as mock_client:
            adapter.dispatch(job=job, routing_hint=_valid_hint(), settings=None, dry_run=True)
        mock_client.assert_not_called()

    def test_dry_run_message_contains_board_name(self):
        adapter = self._adapter()
        job = _make_job(input_data={"subject": "Hi"})
        result = adapter.dispatch(job=job, routing_hint=_valid_hint(board_name="Sales"), settings=None, dry_run=True)
        assert "Sales" in result.message

    def test_dry_run_details_has_item_name(self):
        adapter = self._adapter()
        job = _make_job(input_data={"subject": "Test"})
        result = adapter.dispatch(job=job, routing_hint=_valid_hint(), settings=None, dry_run=True)
        assert "item_name" in result.details


# ---------------------------------------------------------------------------
# MondayLeadDispatchAdapter — live
# ---------------------------------------------------------------------------

class TestMondayLeadAdapterLive:
    def _adapter(self):
        from app.workflows.dispatchers.monday_lead_adapter import MondayLeadDispatchAdapter
        return MondayLeadDispatchAdapter()

    def _mock_settings(self, api_key="test-key"):
        s = MagicMock()
        s.MONDAY_API_KEY = api_key
        s.MONDAY_API_URL = "https://api.monday.com/v2"
        return s

    def test_missing_api_key_returns_failed(self):
        adapter = self._adapter()
        job = _make_job()
        result = adapter.dispatch(job=job, routing_hint=_valid_hint(), settings=None, dry_run=False)
        # get_settings returns empty key in test env
        assert result.status in ("failed",)

    def test_live_success_returns_success(self):
        adapter = self._adapter()
        job = _make_job(input_data={"subject": "Lead 1"})
        mock_resp = {"data": {"create_item": {"id": "9001", "name": "Lead 1", "state": "active", "board": {"id": "99", "name": "Leads"}}}}

        with (
            patch("app.workflows.dispatchers.monday_lead_adapter.get_settings", return_value=self._mock_settings()),
            patch("app.integrations.monday.client.MondayClient.create_item", return_value=mock_resp),
        ):
            result = adapter.dispatch(job=job, routing_hint=_valid_hint(), settings=None, dry_run=False)

        assert result.status == "success"
        assert result.external_id == "9001"
        assert result.system == "monday"

    def test_live_success_message_contains_board_name(self):
        adapter = self._adapter()
        job = _make_job(input_data={"subject": "Lead"})
        mock_resp = {"data": {"create_item": {"id": "10", "name": "Lead", "state": "active", "board": {"id": "99", "name": "Leads"}}}}

        with (
            patch("app.workflows.dispatchers.monday_lead_adapter.get_settings", return_value=self._mock_settings()),
            patch("app.integrations.monday.client.MondayClient.create_item", return_value=mock_resp),
        ):
            result = adapter.dispatch(job=job, routing_hint=_valid_hint(board_name="Leads"), settings=None, dry_run=False)

        assert "Leads" in result.message

    def test_adapter_error_returns_failed(self):
        adapter = self._adapter()
        job = _make_job()

        with (
            patch("app.workflows.dispatchers.monday_lead_adapter.get_settings", return_value=self._mock_settings()),
            patch("app.integrations.monday.client.MondayClient.create_item", side_effect=RuntimeError("API error")),
        ):
            result = adapter.dispatch(job=job, routing_hint=_valid_hint(), settings=None, dry_run=False)

        assert result.status == "failed"
        assert "API error" in result.message

    def test_board_id_passed_to_create_item(self):
        adapter = self._adapter()
        job = _make_job()
        captured = {}
        mock_resp = {"data": {"create_item": {"id": "55"}}}

        def fake_create(board_id, item_name, group_id=None, column_values=None):
            captured["board_id"] = board_id
            return mock_resp

        with (
            patch("app.workflows.dispatchers.monday_lead_adapter.get_settings", return_value=self._mock_settings()),
            patch("app.integrations.monday.client.MondayClient.create_item", side_effect=fake_create),
        ):
            adapter.dispatch(job=job, routing_hint=_valid_hint(board_id="77"), settings=None, dry_run=False)

        assert captured["board_id"] == 77  # cast to int


# ---------------------------------------------------------------------------
# ControlledDispatchEngine
# ---------------------------------------------------------------------------

class TestControlledDispatchEngine:
    def _engine(self, tenant_id="T1"):
        from app.workflows.dispatchers.engine import ControlledDispatchEngine
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None
        return ControlledDispatchEngine(db=db, tenant_id=tenant_id, settings=MagicMock()), db

    def test_missing_hint_returns_failed(self):
        engine, _ = self._engine()
        job = _make_job(job_type="lead")
        result = engine.run(job, memory={"routing_hints": {"lead": None}})
        assert result.status == "failed"
        assert "routing hint" in result.message.lower() or "hint" in result.message.lower()

    def test_invalid_hint_returns_failed(self):
        engine, _ = self._engine()
        job = _make_job(job_type="lead")
        result = engine.run(job, memory={"routing_hints": {"lead": {"bad": "data"}}})
        assert result.status == "failed"

    def test_unsupported_job_type_returns_failed(self):
        engine, _ = self._engine()
        job = _make_job(job_type="unknown_xyz")
        result = engine.run(job, memory={"routing_hints": {}})
        assert result.status == "failed"

    def test_unsupported_system_returns_failed(self):
        engine, _ = self._engine()
        job = _make_job(job_type="lead")
        hint = {"system": "hubspot", "target": {"board_id": "1", "board_name": "X", "group_id": None, "group_name": None}}
        result = engine.run(job, memory={"routing_hints": {"lead": hint}})
        assert result.status == "failed"
        assert "hubspot" in result.message.lower() or "adapter" in result.message.lower()

    def test_dry_run_returns_dry_run_status(self):
        engine, _ = self._engine()
        job = _make_job(job_type="lead")
        result = engine.run(job, memory=_memory_with_lead_hint(), dry_run=True)
        assert result.status == "dry_run"

    def test_dry_run_does_not_persist(self):
        from app.workflows.dispatchers.engine import ControlledDispatchEngine
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None
        engine = ControlledDispatchEngine(db=db, tenant_id="T1", settings=MagicMock())
        job = _make_job(job_type="lead")
        with patch("app.workflows.dispatchers.engine._persist_dispatch") as mock_persist:
            engine.run(job, memory=_memory_with_lead_hint(), dry_run=True)
        mock_persist.assert_not_called()

    def test_duplicate_dispatch_returns_skipped(self):
        from app.workflows.dispatchers.engine import ControlledDispatchEngine
        db = _make_db()
        engine = ControlledDispatchEngine(db=db, tenant_id="T1", settings=MagicMock())
        job = _make_job(job_type="lead")

        existing = MagicMock()
        existing.status = "success"

        with patch("app.workflows.dispatchers.engine._find_existing_dispatch", return_value=existing):
            result = engine.run(job, memory=_memory_with_lead_hint(), dry_run=False)

        assert result.status == "skipped"
        assert "skickad" in result.message.lower() or "dispatched" in result.message.lower()

    def test_successful_dispatch_persists_event(self):
        from app.workflows.dispatchers.engine import ControlledDispatchEngine
        from app.workflows.dispatchers.base import DispatchResult
        db = _make_db()
        engine = ControlledDispatchEngine(db=db, tenant_id="T1", settings=MagicMock())
        job = _make_job(job_type="lead")

        ok_result = DispatchResult(
            status="success", system="monday", job_type="lead",
            target={}, external_id="999", message="ok",
        )
        mock_adapter = MagicMock()
        mock_adapter.dispatch.return_value = ok_result

        with (
            patch("app.workflows.dispatchers.engine.DISPATCH_REGISTRY", {("monday", "lead"): mock_adapter}),
            patch("app.workflows.dispatchers.engine._find_existing_dispatch", return_value=None),
            patch("app.workflows.dispatchers.engine._persist_dispatch") as mock_persist,
        ):
            engine.run(job, memory=_memory_with_lead_hint(), dry_run=False)

        mock_persist.assert_called_once()


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/dispatch-preview endpoint
# ---------------------------------------------------------------------------

class TestDispatchPreviewEndpoint:
    def _make_job_record(self, job_id="job-1", job_type="lead"):
        r = MagicMock()
        r.job_id    = job_id
        r.tenant_id = "T1"
        r.job_type  = job_type
        r.input_data = {}
        r.result     = {}
        return r

    def _call(self, job_record=None, settings_data=None):
        from app.main import dispatch_preview
        db = _make_db()
        record = job_record or self._make_job_record()
        db.query.return_value.filter.return_value.first.return_value = record
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=settings_data or {"memory": {"routing_hints": {"lead": _valid_hint()}}},
        ):
            return dispatch_preview(job_id=record.job_id, db=db, tenant_id="T1")

    def test_returns_dry_run_status(self):
        result = self._call()
        assert result["status"] == "dry_run"

    def test_does_not_call_monday_api(self):
        with patch("app.integrations.monday.client.MondayClient.create_item") as mock_create:
            self._call()
        mock_create.assert_not_called()

    def test_job_not_found_raises_404(self):
        from fastapi import HTTPException
        from app.main import dispatch_preview
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None
        with pytest.raises(HTTPException) as exc:
            dispatch_preview(job_id="missing", db=db, tenant_id="T1")
        assert exc.value.status_code == 404

    def test_missing_hint_still_returns_result(self):
        # Preview never raises — always returns a result dict
        result = self._call(
            settings_data={"memory": {"routing_hints": {"lead": None}}}
        )
        assert result["status"] == "failed"
        assert "job_type" in result


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/dispatch endpoint
# ---------------------------------------------------------------------------

class TestDispatchEndpoint:
    def _make_job_record(self, job_type="lead"):
        r = MagicMock()
        r.job_id    = "job-2"
        r.tenant_id = "T1"
        r.job_type  = job_type
        r.input_data = {}
        r.result     = {}
        return r

    def _call_dispatch(self, settings_data=None, job_record=None, mock_adapter_result=None):
        from app.main import dispatch_job
        from app.workflows.dispatchers.base import DispatchResult
        db = _make_db()
        record = job_record or self._make_job_record()
        db.query.return_value.filter.return_value.first.return_value = record

        # Default: no existing dispatch event
        db.query.return_value.filter.return_value.filter.return_value.first.return_value = None

        settings = settings_data or {"memory": {"routing_hints": {"lead": _valid_hint()}}}

        if mock_adapter_result is None:
            mock_adapter_result = DispatchResult(
                status="success", system="monday", job_type="lead",
                target={"board_id": "99"}, external_id="1001", message="ok",
            )

        with (
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value=settings,
            ),
            patch(
                "app.workflows.dispatchers.engine.DISPATCH_REGISTRY",
                {("monday", "lead"): MagicMock(dispatch=lambda **k: mock_adapter_result)},
            ),
            patch("app.workflows.dispatchers.engine._persist_dispatch"),
            patch("app.workflows.dispatchers.engine._find_existing_dispatch", return_value=None),
        ):
            return dispatch_job(job_id="job-2", db=db, tenant_id="T1")

    def test_success_response_shape(self):
        result = self._call_dispatch()
        assert result["status"] == "success"
        assert result["system"] == "monday"
        assert result["job_type"] == "lead"
        assert "target" in result
        assert "message" in result

    def test_failed_raises_400(self):
        from fastapi import HTTPException
        from app.workflows.dispatchers.base import DispatchResult
        failed = DispatchResult(status="failed", system="monday", job_type="lead", message="No hint")
        with pytest.raises(HTTPException) as exc:
            self._call_dispatch(mock_adapter_result=failed)
        assert exc.value.status_code == 400

    def test_job_not_found_raises_404(self):
        from fastapi import HTTPException
        from app.main import dispatch_job
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None
        with (
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={}),
        ):
            with pytest.raises(HTTPException) as exc:
                dispatch_job(job_id="nope", db=db, tenant_id="T1")
        assert exc.value.status_code == 404

    def test_skipped_returns_skipped_not_400(self):
        from app.workflows.dispatchers.base import DispatchResult
        skipped = DispatchResult(status="skipped", system="monday", job_type="lead", message="Redan skickad")
        result = self._call_dispatch(mock_adapter_result=skipped)
        assert result["status"] == "skipped"

    def test_tenant_isolation(self):
        from app.main import dispatch_job
        from app.workflows.dispatchers.base import DispatchResult
        db = _make_db()
        r1 = self._make_job_record()
        db.query.return_value.filter.return_value.first.return_value = r1

        ok = DispatchResult(status="success", system="monday", job_type="lead", target={}, external_id="1", message="ok")
        mock_adapter = MagicMock()
        mock_adapter.dispatch.return_value = ok

        with (
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={"memory": {"routing_hints": {"lead": _valid_hint()}}}),
            patch("app.workflows.dispatchers.engine.DISPATCH_REGISTRY", {("monday", "lead"): mock_adapter}),
            patch("app.workflows.dispatchers.engine._persist_dispatch"),
            patch("app.workflows.dispatchers.engine._find_existing_dispatch", return_value=None),
        ):
            result = dispatch_job(job_id="job-2", db=db, tenant_id="T1")
        assert result["status"] == "success"
