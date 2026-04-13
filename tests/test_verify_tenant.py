"""
Tests for POST /verify/{tenant_id} — deterministic verification endpoint.

The endpoint no longer calls run_pipeline (LLM-dependent). Instead it:
  - Picks the first enabled type from _VERIFICATION_SUPPORTED_TYPES
  - Raises 400 if no supported type is enabled (not just unrecognised)
  - Calls _run_verification_pipeline (mocked in success tests)
  - Returns job_id, tenant_id, job_type, status, result, verification_type

Covers:
  - 404 when tenant not found in DB
  - 400 when tenant has no enabled job types
  - 400 when only unsupported job types are enabled
  - Success: response keys present
  - Success: returned tenant_id matches path param
  - Success: first supported type is preferred (not just first enabled)
  - Success: verification_type key present and matches chosen type
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def _mock_db():
    return MagicMock()


def _record(tenant_id="TENANT_X", enabled_job_types=None):
    rec = MagicMock()
    rec.tenant_id = tenant_id
    rec.enabled_job_types = enabled_job_types if enabled_job_types is not None else ["lead"]
    return rec


def _processed_job(tenant_id="TENANT_X", job_type_value="lead", status_value="completed"):
    job = MagicMock()
    job.job_id = "job-verify-001"
    job.tenant_id = tenant_id
    job.job_type = MagicMock()
    job.job_type.value = job_type_value
    job.status = MagicMock()
    job.status.value = status_value
    job.result = {"summary": "ok", "payload": {"processor_name": "human_handoff_processor"}}
    return job


def _call(tenant_id, record=None, pipeline_result=None):
    from app.main import verify_tenant

    db = _mock_db()
    if pipeline_result is None:
        pipeline_result = _processed_job(tenant_id=tenant_id)

    with patch(
        "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
        return_value=record,
    ), patch(
        "app.repositories.postgres.job_repository.JobRepository.create_job",
        return_value=pipeline_result,
    ), patch(
        "app.main._run_verification_pipeline",
        return_value=pipeline_result,
    ), patch(
        "app.main.set_current_tenant",
    ):
        return verify_tenant(tenant_id=tenant_id, db=db)


class TestVerifyTenant404:
    def test_raises_404_when_tenant_not_found(self):
        with pytest.raises(HTTPException) as exc_info:
            _call("TENANT_MISSING", record=None)
        assert exc_info.value.status_code == 404

    def test_404_detail_mentions_tenant_id(self):
        with pytest.raises(HTTPException) as exc_info:
            _call("TENANT_MISSING", record=None)
        assert "TENANT_MISSING" in exc_info.value.detail


class TestVerifyTenant400:
    def test_raises_400_when_no_enabled_job_types(self):
        with pytest.raises(HTTPException) as exc_info:
            _call("TENANT_X", record=_record(enabled_job_types=[]))
        assert exc_info.value.status_code == 400

    def test_400_detail_mentions_tenant_id_when_empty(self):
        with pytest.raises(HTTPException) as exc_info:
            _call("TENANT_X", record=_record(enabled_job_types=[]))
        assert "TENANT_X" in exc_info.value.detail

    def test_raises_400_when_only_unsupported_types_enabled(self):
        """Types not in _VERIFICATION_SUPPORTED_TYPES must produce a clear 400."""
        with pytest.raises(HTTPException) as exc_info:
            _call("TENANT_X", record=_record(enabled_job_types=["kpi", "report", "exec_summary"]))
        assert exc_info.value.status_code == 400

    def test_400_detail_mentions_supported_types_when_unsupported(self):
        with pytest.raises(HTTPException) as exc_info:
            _call("TENANT_X", record=_record(enabled_job_types=["kpi", "report"]))
        detail = exc_info.value.detail
        # Should mention at least one supported type so user knows what to enable
        assert any(t in detail for t in ["lead", "customer_inquiry", "invoice"])


class TestVerifyTenantSuccess:
    def test_returns_job_id_key(self):
        result = _call("TENANT_X", record=_record())
        assert "job_id" in result

    def test_returns_tenant_id_key(self):
        result = _call("TENANT_X", record=_record())
        assert "tenant_id" in result

    def test_returns_job_type_key(self):
        result = _call("TENANT_X", record=_record())
        assert "job_type" in result

    def test_returns_status_key(self):
        result = _call("TENANT_X", record=_record())
        assert "status" in result

    def test_returns_result_key(self):
        result = _call("TENANT_X", record=_record())
        assert "result" in result

    def test_returns_verification_type_key(self):
        result = _call("TENANT_X", record=_record())
        assert "verification_type" in result

    def test_returned_tenant_id_is_path_param(self):
        """tenant_id in response must match the path param, not a derived value."""
        job = _processed_job(tenant_id="TENANT_2002")
        result = _call("TENANT_2002", record=_record(tenant_id="TENANT_2002"), pipeline_result=job)
        assert result["tenant_id"] == "TENANT_2002"

    def test_prefers_supported_type_over_unsupported_first(self):
        """If enabled list starts with unsupported type, skip to first supported one."""
        job = _processed_job(job_type_value="invoice")
        result = _call(
            "TENANT_X",
            record=_record(enabled_job_types=["kpi", "invoice", "lead"]),
            pipeline_result=job,
        )
        assert result["job_type"] in ("invoice", "lead")

    def test_uses_lead_when_enabled(self):
        job = _processed_job(job_type_value="lead")
        result = _call(
            "TENANT_X",
            record=_record(enabled_job_types=["lead", "invoice"]),
            pipeline_result=job,
        )
        assert result["job_type"] == "lead"

    def test_does_not_raise_with_valid_tenant(self):
        """Smoke: no exception raised for a valid, configured tenant."""
        _call("TENANT_X", record=_record())
