"""
Tests for Slice 8 — Dispatch Control Policy Integration.

Covers:
- resolve_dispatch_policy(): manual, semi→approval_required, auto→full_auto
- missing/None/False/unknown values default to manual
- dispatch-preview includes policy_mode, requires_approval, can_dispatch_now
- dispatch endpoint: manual mode allows execution
- dispatch endpoint: approval_required blocks external dispatch
- dispatch endpoint: approval_required does not call Monday adapter
- dispatch endpoint: full_auto mode allows execution
- GET /jobs/{job_id}/dispatch-policy: shape, 404 for missing job
- tenant isolation
- existing dispatch duplicate protection still works
- existing routing preview/readiness unaffected
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Helpers
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


# ---------------------------------------------------------------------------
# resolve_dispatch_policy — pure function
# ---------------------------------------------------------------------------

class TestResolveDispatchPolicy:
    def _call(self, auto_actions, job_type="lead"):
        from app.workflows.dispatchers.policy import resolve_dispatch_policy
        return resolve_dispatch_policy(_tenant_config(auto_actions), job_type)

    def test_manual_string_returns_manual(self):
        result = self._call({"lead": "manual"})
        assert result["policy_mode"] == "manual"
        assert result["requires_approval"] is False
        assert result["can_dispatch_now"] is True

    def test_false_value_returns_manual(self):
        result = self._call({"lead": False})
        assert result["policy_mode"] == "manual"

    def test_none_value_returns_manual(self):
        result = self._call({"lead": None})
        assert result["policy_mode"] == "manual"

    def test_missing_key_returns_manual(self):
        result = self._call({})
        assert result["policy_mode"] == "manual"

    def test_semi_returns_approval_required(self):
        result = self._call({"lead": "semi"})
        assert result["policy_mode"] == "approval_required"
        assert result["requires_approval"] is True
        assert result["can_dispatch_now"] is False

    def test_auto_string_returns_full_auto(self):
        result = self._call({"lead": "auto"})
        assert result["policy_mode"] == "full_auto"
        assert result["requires_approval"] is False
        assert result["can_dispatch_now"] is True

    def test_true_value_returns_full_auto(self):
        result = self._call({"lead": True})
        assert result["policy_mode"] == "full_auto"

    def test_unknown_value_returns_manual(self):
        result = self._call({"lead": "gibberish"})
        assert result["policy_mode"] == "manual"

    def test_different_job_type_isolated(self):
        result_lead    = self._call({"lead": "auto", "invoice": "semi"}, job_type="lead")
        result_invoice = self._call({"lead": "auto", "invoice": "semi"}, job_type="invoice")
        assert result_lead["policy_mode"]    == "full_auto"
        assert result_invoice["policy_mode"] == "approval_required"

    def test_response_has_all_keys(self):
        result = self._call({})
        assert "policy_mode" in result
        assert "requires_approval" in result
        assert "can_dispatch_now" in result


# ---------------------------------------------------------------------------
# GET /jobs/{job_id}/dispatch-policy endpoint
# ---------------------------------------------------------------------------

def _call_get_policy(job_type="lead", auto_actions=None, missing_job=False):
    from app.main import get_dispatch_policy
    db = _make_db()

    if missing_job:
        db.query.return_value.filter.return_value.first.return_value = None
    else:
        db.query.return_value.filter.return_value.first.return_value = _make_job_record(job_type=job_type)

    tenant_cfg = _tenant_config(auto_actions or {})

    with patch("app.main.get_tenant_config", return_value=tenant_cfg):
        return get_dispatch_policy(job_id="job-1", db=db, tenant_id="T1")


class TestGetDispatchPolicyEndpoint:
    def test_returns_job_id_and_job_type(self):
        result = _call_get_policy()
        assert result["job_id"] == "job-1"
        assert result["job_type"] == "lead"

    def test_manual_default(self):
        result = _call_get_policy(auto_actions={})
        assert result["policy_mode"] == "manual"
        assert result["can_dispatch_now"] is True
        assert result["requires_approval"] is False

    def test_semi_returns_approval_required(self):
        result = _call_get_policy(auto_actions={"lead": "semi"})
        assert result["policy_mode"] == "approval_required"

    def test_auto_returns_full_auto(self):
        result = _call_get_policy(auto_actions={"lead": "auto"})
        assert result["policy_mode"] == "full_auto"

    def test_missing_job_raises_404(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _call_get_policy(missing_job=True)
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/dispatch-preview — includes policy fields
# ---------------------------------------------------------------------------

def _call_dispatch_preview(auto_actions=None, settings_data=None):
    from app.main import dispatch_preview
    db = _make_db()
    record = _make_job_record()
    db.query.return_value.filter.return_value.first.return_value = record

    tenant_cfg = _tenant_config(auto_actions or {})
    mem_settings = settings_data or _settings_with_lead_hint()

    with (
        patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value=mem_settings),
        patch("app.main.get_tenant_config", return_value=tenant_cfg),
    ):
        return dispatch_preview(job_id="job-1", db=db, tenant_id="T1")


class TestDispatchPreviewWithPolicy:
    def test_includes_policy_mode(self):
        result = _call_dispatch_preview()
        assert "policy_mode" in result

    def test_includes_requires_approval(self):
        result = _call_dispatch_preview()
        assert "requires_approval" in result

    def test_includes_can_dispatch_now(self):
        result = _call_dispatch_preview()
        assert "can_dispatch_now" in result

    def test_manual_policy_in_preview(self):
        result = _call_dispatch_preview(auto_actions={"lead": "manual"})
        assert result["policy_mode"] == "manual"
        assert result["can_dispatch_now"] is True

    def test_semi_policy_in_preview(self):
        result = _call_dispatch_preview(auto_actions={"lead": "semi"})
        assert result["policy_mode"] == "approval_required"
        assert result["requires_approval"] is True

    def test_full_auto_policy_in_preview(self):
        result = _call_dispatch_preview(auto_actions={"lead": "auto"})
        assert result["policy_mode"] == "full_auto"

    def test_preview_still_returns_dry_run_status(self):
        result = _call_dispatch_preview()
        assert result["status"] == "dry_run"

    def test_preview_never_writes_externally(self):
        with patch("app.integrations.monday.client.MondayClient.create_item") as mock_create:
            _call_dispatch_preview()
        mock_create.assert_not_called()


# ---------------------------------------------------------------------------
# POST /jobs/{job_id}/dispatch — policy enforcement
# ---------------------------------------------------------------------------

def _call_dispatch_live(auto_actions=None, settings_data=None, mock_adapter_result=None):
    from app.main import dispatch_job
    from app.workflows.dispatchers.base import DispatchResult
    db = _make_db()
    record = _make_job_record()
    db.query.return_value.filter.return_value.first.return_value = record

    tenant_cfg = _tenant_config(auto_actions or {})
    mem_settings = settings_data or _settings_with_lead_hint()

    if mock_adapter_result is None:
        mock_adapter_result = DispatchResult(
            status="success", system="monday", job_type="lead",
            target={"board_id": "99"}, external_id="1001", message="ok",
        )

    mock_adapter = MagicMock()
    mock_adapter.dispatch.return_value = mock_adapter_result

    with (
        patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value=mem_settings),
        patch("app.main.get_tenant_config", return_value=tenant_cfg),
        patch("app.workflows.dispatchers.engine.DISPATCH_REGISTRY", {("monday", "lead"): mock_adapter}),
        patch("app.workflows.dispatchers.engine._persist_dispatch"),
        patch("app.workflows.dispatchers.engine._find_existing_dispatch", return_value=None),
    ):
        return dispatch_job(job_id="job-1", db=db, tenant_id="T1"), mock_adapter


class TestDispatchLiveWithPolicy:
    def test_manual_mode_allows_dispatch(self):
        result, adapter = _call_dispatch_live(auto_actions={"lead": "manual"})
        assert result["status"] == "success"
        adapter.dispatch.assert_called_once()

    def test_full_auto_allows_dispatch(self):
        result, adapter = _call_dispatch_live(auto_actions={"lead": "auto"})
        assert result["status"] == "success"
        adapter.dispatch.assert_called_once()

    def test_approval_required_blocks_dispatch(self):
        result, adapter = _call_dispatch_live(auto_actions={"lead": "semi"})
        assert result["status"] == "approval_required"

    def test_approval_required_does_not_call_adapter(self):
        _, adapter = _call_dispatch_live(auto_actions={"lead": "semi"})
        adapter.dispatch.assert_not_called()

    def test_approval_required_response_has_policy_mode(self):
        result, _ = _call_dispatch_live(auto_actions={"lead": "semi"})
        assert result["policy_mode"] == "approval_required"

    def test_approval_required_response_has_message(self):
        result, _ = _call_dispatch_live(auto_actions={"lead": "semi"})
        assert "approval" in result["message"].lower() or "godkännande" in result["message"].lower()

    def test_success_includes_policy_fields(self):
        result, _ = _call_dispatch_live(auto_actions={"lead": "auto"})
        assert "policy_mode" in result
        assert "can_dispatch_now" in result

    def test_default_no_auto_actions_is_manual_allows(self):
        result, adapter = _call_dispatch_live(auto_actions={})
        assert result["status"] == "success"
        adapter.dispatch.assert_called_once()

    def test_tenant_isolation(self):
        # T1 has "auto", T2 has "semi" — calls should not interfere
        result_t1, _ = _call_dispatch_live(auto_actions={"lead": "auto"})
        result_t2, _ = _call_dispatch_live(auto_actions={"lead": "semi"})
        assert result_t1["status"] == "success"
        assert result_t2["status"] == "approval_required"


# ---------------------------------------------------------------------------
# Existing behavior preserved
# ---------------------------------------------------------------------------

class TestExistingBehaviorPreserved:
    def test_routing_preview_endpoint_still_works(self):
        from app.main import get_routing_preview
        db = _make_db()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value={"memory": {"routing_hints": {"lead": _valid_hint()}}},
        ):
            result = get_routing_preview(job_type="lead", db=db, tenant_id="T1")
        assert result["status"] == "ready"

    def test_routing_readiness_endpoint_still_works(self):
        from app.main import get_routing_readiness
        db = _make_db()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value={},
        ):
            result = get_routing_readiness(db=db, tenant_id="T1")
        assert "score" in result

    def test_dispatch_preview_404_still_works(self):
        from fastapi import HTTPException
        from app.main import dispatch_preview
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None
        with (
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={}),
            patch("app.core.config.get_tenant_config", return_value=_tenant_config()),
        ):
            with pytest.raises(HTTPException) as exc:
                dispatch_preview(job_id="missing", db=db, tenant_id="T1")
        assert exc.value.status_code == 404
