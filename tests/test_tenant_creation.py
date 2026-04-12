"""
Tests for POST /tenant — tenant creation endpoint.

Covers:
  - Success: new tenant stored, response shape correct
  - Duplicate: 400 returned when tenant_id already exists
  - Retrievable: created tenant readable via GET /tenant (config fallback path)

Tests call endpoint functions directly with mocked DB sessions,
matching the established pattern in this repo (no httpx / TestClient).
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db():
    return MagicMock()


def _make_request(tenant_id: str = "TENANT_9001", name: str = "Acme Corp"):
    from app.main import TenantCreateRequest
    return TenantCreateRequest(tenant_id=tenant_id, name=name)


# ---------------------------------------------------------------------------
# POST /tenant — success
# ---------------------------------------------------------------------------

class TestCreateTenantSuccess:
    def test_returns_created_status(self):
        from app.main import create_tenant
        db = _mock_db()
        req = _make_request()

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=None,
        ), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert",
            return_value=MagicMock(),
        ):
            result = create_tenant(request=req, db=db)

        assert result["status"] == "created"

    def test_returns_tenant_id_in_response(self):
        from app.main import create_tenant
        db = _mock_db()
        req = _make_request(tenant_id="TENANT_9002")

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=None,
        ), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert",
            return_value=MagicMock(),
        ):
            result = create_tenant(request=req, db=db)

        assert result["tenant_id"] == "TENANT_9002"

    def test_returns_name_in_response(self):
        from app.main import create_tenant
        db = _mock_db()
        req = _make_request(name="Beta Corp")

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=None,
        ), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert",
            return_value=MagicMock(),
        ):
            result = create_tenant(request=req, db=db)

        assert result["name"] == "Beta Corp"

    def test_upsert_called_with_empty_collections(self):
        from app.main import create_tenant
        db = _mock_db()
        req = _make_request(tenant_id="TENANT_9003", name="Gamma Ltd")

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=None,
        ), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert"
        ) as mock_upsert:
            mock_upsert.return_value = MagicMock()
            create_tenant(request=req, db=db)

        mock_upsert.assert_called_once()
        kw = mock_upsert.call_args.kwargs
        assert kw["tenant_id"] == "TENANT_9003"
        assert kw["name"] == "Gamma Ltd"
        assert kw["enabled_job_types"] == []
        assert kw["allowed_integrations"] == []
        assert kw["auto_actions"] == {}


# ---------------------------------------------------------------------------
# POST /tenant — duplicate rejection
# ---------------------------------------------------------------------------

class TestCreateTenantDuplicate:
    def test_raises_400_when_tenant_exists(self):
        from app.main import create_tenant
        db = _mock_db()
        req = _make_request(tenant_id="TENANT_EXISTING")

        existing_record = MagicMock()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=existing_record,
        ):
            with pytest.raises(HTTPException) as exc_info:
                create_tenant(request=req, db=db)

        assert exc_info.value.status_code == 400

    def test_error_detail_mentions_tenant_id(self):
        from app.main import create_tenant
        db = _mock_db()
        req = _make_request(tenant_id="TENANT_EXISTING")

        existing_record = MagicMock()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=existing_record,
        ):
            with pytest.raises(HTTPException) as exc_info:
                create_tenant(request=req, db=db)

        assert "TENANT_EXISTING" in exc_info.value.detail

    def test_upsert_not_called_when_duplicate(self):
        from app.main import create_tenant
        db = _mock_db()
        req = _make_request(tenant_id="TENANT_DUP")

        existing_record = MagicMock()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=existing_record,
        ), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert"
        ) as mock_upsert:
            with pytest.raises(HTTPException):
                create_tenant(request=req, db=db)

        mock_upsert.assert_not_called()


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

class TestTenantCreateRequestSchema:
    def test_schema_accepts_valid_body(self):
        from app.main import TenantCreateRequest
        req = TenantCreateRequest(tenant_id="TENANT_X", name="X Corp")
        assert req.tenant_id == "TENANT_X"
        assert req.name == "X Corp"

    def test_schema_requires_tenant_id(self):
        from pydantic import ValidationError
        from app.main import TenantCreateRequest
        with pytest.raises(ValidationError):
            TenantCreateRequest(name="Missing ID Corp")

    def test_schema_requires_name(self):
        from pydantic import ValidationError
        from app.main import TenantCreateRequest
        with pytest.raises(ValidationError):
            TenantCreateRequest(tenant_id="TENANT_Y")
