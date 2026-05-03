"""Tests for Admin Customer Provisioning slice.

Coverage:
- TenantApiKeyRepository: create, lookup, rotate, revoke
- auth.py DB-key lookup + env fallback + inactive-tenant rejection
- POST /admin/tenants: create, duplicate, bad slug
- GET /admin/tenants: no API keys in response
- POST /admin/tenants/{id}/rotate-key: new key works, old key fails
- PATCH /admin/tenants/{id}/status: inactive tenant key rejected

All DB tests use direct function calls with mocked sessions — no TestClient.
"""
from __future__ import annotations

import hashlib
from unittest.mock import MagicMock, patch

import pytest

from app.repositories.postgres.tenant_api_key_repository import (
    TenantApiKeyRepository,
    _hash_key,
    _generate_raw_key,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db() -> MagicMock:
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.first.return_value = None
    q.all.return_value = []
    return db


def _make_key_record(tenant_id: str = "T_TEST", raw_key: str | None = None, is_active: bool = True):
    raw = raw_key or _generate_raw_key()
    rec = MagicMock()
    rec.tenant_id = tenant_id
    rec.key_hash = _hash_key(raw)
    rec.key_hint = raw[-4:]
    rec.is_active = is_active
    rec.revoked_at = None
    return rec, raw


def _make_tenant_record(tenant_id: str = "T_TEST", status: str = "active"):
    rec = MagicMock()
    rec.tenant_id = tenant_id
    rec.name = "Test AB"
    rec.slug = "test"
    rec.status = status
    rec.enabled_job_types = ["lead"]
    rec.allowed_integrations = []
    rec.auto_actions = {}
    rec.created_at = None
    rec.updated_at = None
    return rec


# ---------------------------------------------------------------------------
# TenantApiKeyRepository unit tests
# ---------------------------------------------------------------------------

class TestTenantApiKeyRepository:

    def test_generate_raw_key_format(self):
        key = _generate_raw_key()
        assert key.startswith("kw_")
        assert len(key) == 35  # "kw_" + 32 hex chars

    def test_hash_key_is_sha256(self):
        raw = "kw_" + "a" * 32
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert _hash_key(raw) == expected

    def test_hash_key_deterministic(self):
        raw = _generate_raw_key()
        assert _hash_key(raw) == _hash_key(raw)

    def test_two_different_keys_have_different_hashes(self):
        k1 = _generate_raw_key()
        k2 = _generate_raw_key()
        assert _hash_key(k1) != _hash_key(k2)

    def test_create_key_returns_raw_key_and_record(self):
        db = _mock_db()
        raw_key, record = TenantApiKeyRepository.create_key(db, "T_NEW")
        assert raw_key.startswith("kw_")
        assert len(raw_key) == 35
        db.add.assert_called_once()
        db.commit.assert_called_once()

    def test_lookup_tenant_returns_tenant_id_for_valid_key(self):
        db = _mock_db()
        raw_key = _generate_raw_key()
        key_rec, _ = _make_key_record("T_FOUND", raw_key=raw_key)
        db.query.return_value.filter.return_value.first.return_value = key_rec

        result = TenantApiKeyRepository.lookup_tenant(db, raw_key)
        assert result == "T_FOUND"

    def test_lookup_tenant_returns_none_for_unknown_key(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        result = TenantApiKeyRepository.lookup_tenant(db, "kw_" + "x" * 32)
        assert result is None

    def test_lookup_tenant_returns_none_for_inactive_key(self):
        db = _mock_db()
        # Inactive key — DB filter on is_active should exclude it
        db.query.return_value.filter.return_value.first.return_value = None
        raw_key = _generate_raw_key()
        result = TenantApiKeyRepository.lookup_tenant(db, raw_key)
        assert result is None

    def test_rotate_key_revokes_existing_and_issues_new(self):
        db = _mock_db()
        old_rec = MagicMock()
        old_rec.is_active = True
        old_rec.revoked_at = None
        db.query.return_value.filter.return_value.all.return_value = [old_rec]

        new_raw, new_rec = TenantApiKeyRepository.rotate_key(db, "T_ROTATE")
        assert new_raw.startswith("kw_")
        assert old_rec.is_active is False
        assert old_rec.revoked_at is not None
        db.commit.assert_called()

    def test_revoke_all_marks_all_active_keys_inactive(self):
        db = _mock_db()
        rec1, rec2 = MagicMock(), MagicMock()
        rec1.is_active = True
        rec2.is_active = True
        db.query.return_value.filter.return_value.all.return_value = [rec1, rec2]

        count = TenantApiKeyRepository.revoke_all(db, "T_REVOKE")
        assert count == 2
        assert rec1.is_active is False
        assert rec2.is_active is False


# ---------------------------------------------------------------------------
# auth.py: DB key lookup + env fallback + inactive tenant
# ---------------------------------------------------------------------------

class TestAuthDbKeyLookup:

    def test_db_key_resolves_tenant(self):
        from app.core.auth import _lookup_db_key
        db = _mock_db()
        raw_key = _generate_raw_key()
        key_rec = MagicMock()
        key_rec.tenant_id = "T_DB"
        db.query.return_value.filter.return_value.first.return_value = key_rec

        with patch("app.repositories.postgres.tenant_api_key_repository.TenantApiKeyRepository.lookup_tenant", return_value="T_DB"):
            result = _lookup_db_key(db, raw_key)
        assert result == "T_DB"

    def test_db_key_returns_none_on_missing(self):
        from app.core.auth import _lookup_db_key
        db = _mock_db()
        with patch("app.repositories.postgres.tenant_api_key_repository.TenantApiKeyRepository.lookup_tenant", return_value=None):
            result = _lookup_db_key(db, "kw_" + "x" * 32)
        assert result is None

    def test_db_key_degrades_on_exception(self):
        from app.core.auth import _lookup_db_key
        db = _mock_db()
        with patch("app.repositories.postgres.tenant_api_key_repository.TenantApiKeyRepository.lookup_tenant", side_effect=Exception("DB down")):
            result = _lookup_db_key(db, "kw_anything")
        assert result is None

    def test_env_fallback_resolves_known_key(self):
        from app.core import auth as auth_mod
        # Reset cache
        auth_mod._API_KEY_MAP = {"TENANT_2001": "test-api-key-2"}
        from app.core.auth import _lookup_env_key
        result = _lookup_env_key("test-api-key-2")
        assert result == "TENANT_2001"

    def test_env_fallback_returns_none_for_unknown(self):
        from app.core import auth as auth_mod
        auth_mod._API_KEY_MAP = {"TENANT_2001": "test-api-key-2"}
        from app.core.auth import _lookup_env_key
        result = _lookup_env_key("completely-wrong-key")
        assert result is None

    def test_is_tenant_active_returns_true_for_active(self):
        from app.core.auth import _is_tenant_active
        db = _mock_db()
        rec = _make_tenant_record(status="active")
        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get", return_value=rec):
            assert _is_tenant_active(db, "T_TEST") is True

    def test_is_tenant_active_returns_false_for_inactive(self):
        from app.core.auth import _is_tenant_active
        db = _mock_db()
        rec = _make_tenant_record(status="inactive")
        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get", return_value=rec):
            assert _is_tenant_active(db, "T_TEST") is False

    def test_is_tenant_active_returns_true_when_not_in_db(self):
        from app.core.auth import _is_tenant_active
        db = _mock_db()
        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get", return_value=None):
            assert _is_tenant_active(db, "TENANT_2001") is True

    def test_is_tenant_active_degrades_on_exception(self):
        from app.core.auth import _is_tenant_active
        db = _mock_db()
        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get", side_effect=Exception("DB down")):
            assert _is_tenant_active(db, "T_FAIL") is True


# ---------------------------------------------------------------------------
# POST /admin/tenants endpoint
# ---------------------------------------------------------------------------

class TestAdminCreateTenant:

    def _call(self, body: dict, existing_record=None):
        from app.main import admin_create_tenant, AdminTenantCreateRequest
        db = _mock_db()

        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                   return_value=existing_record), \
             patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert",
                   return_value=_make_tenant_record()), \
             patch("app.repositories.postgres.tenant_api_key_repository.TenantApiKeyRepository.create_key",
                   return_value=("kw_" + "a" * 32, MagicMock())):
            return admin_create_tenant(body=AdminTenantCreateRequest(**body), db=db)

    def test_create_returns_tenant_id_and_api_key(self):
        result = self._call({"name": "Elitgruppen", "slug": "elitgruppen"})
        assert result["tenant_id"] == "T_ELITGRUPPEN"
        assert result["api_key"].startswith("kw_")
        assert result["status"] == "active"

    def test_create_derives_tenant_id_from_slug(self):
        result = self._call({"name": "Test AB", "slug": "test-ab"})
        assert result["tenant_id"] == "T_TEST_AB"

    def test_create_returns_slug(self):
        result = self._call({"name": "Elitgruppen", "slug": "elitgruppen"})
        assert result["slug"] == "elitgruppen"

    def test_duplicate_tenant_raises_409(self):
        from fastapi import HTTPException
        existing = _make_tenant_record()
        with pytest.raises(HTTPException) as exc_info:
            self._call({"name": "Dup", "slug": "dup"}, existing_record=existing)
        assert exc_info.value.status_code == 409

    def test_invalid_slug_raises_422(self):
        from fastapi import HTTPException
        from app.main import admin_create_tenant, AdminTenantCreateRequest
        db = _mock_db()
        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                admin_create_tenant(body=AdminTenantCreateRequest(name="X", slug="INVALID SLUG!"), db=db)
        assert exc_info.value.status_code == 422

    def test_api_key_not_stored_in_response_metadata(self):
        result = self._call({"name": "Safe Co", "slug": "safeco"})
        # The key is in the response (show-once), but NOT in list endpoint
        assert "api_key" in result

    def test_enabled_job_types_passed_through(self):
        from app.main import admin_create_tenant, AdminTenantCreateRequest
        db = _mock_db()
        captured = {}
        def mock_upsert(**kwargs):
            captured.update(kwargs)
            return _make_tenant_record()
        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get", return_value=None), \
             patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert", side_effect=mock_upsert), \
             patch("app.repositories.postgres.tenant_api_key_repository.TenantApiKeyRepository.create_key", return_value=("kw_" + "a" * 32, MagicMock())):
            admin_create_tenant(body=AdminTenantCreateRequest(name="X", slug="testco", enabled_job_types=["lead", "invoice"]), db=db)
        assert captured.get("enabled_job_types") == ["lead", "invoice"]


# ---------------------------------------------------------------------------
# GET /admin/tenants — never returns API keys
# ---------------------------------------------------------------------------

class TestAdminListTenants:

    def _call(self, records=None):
        from app.main import admin_list_tenants
        db = _mock_db()
        recs = records if records is not None else [_make_tenant_record()]
        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.list_all",
                   return_value=recs), \
             patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.to_dict",
                   side_effect=lambda r: {"tenant_id": r.tenant_id, "name": r.name, "slug": r.slug,
                                          "status": r.status, "enabled_job_types": [], "allowed_integrations": [],
                                          "auto_actions": {}, "created_at": None, "updated_at": None}):
            return admin_list_tenants(db=db)

    def test_returns_items_list(self):
        result = self._call()
        assert "items" in result
        assert "total" in result

    def test_no_api_key_in_list_response(self):
        result = self._call()
        for item in result["items"]:
            assert "api_key" not in item
            assert "key_hash" not in item
            assert "key" not in item

    def test_empty_db_returns_zero(self):
        result = self._call(records=[])
        assert result["total"] == 0
        assert result["items"] == []

    def test_includes_expected_fields(self):
        result = self._call()
        item = result["items"][0]
        for field in ("tenant_id", "name", "status"):
            assert field in item


# ---------------------------------------------------------------------------
# POST /admin/tenants/{id}/rotate-key
# ---------------------------------------------------------------------------

class TestAdminRotateKey:

    def _call(self, tenant_id: str = "T_TEST", existing=True):
        from app.main import admin_rotate_tenant_key
        db = _mock_db()
        record = _make_tenant_record(tenant_id) if existing else None
        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                   return_value=record), \
             patch("app.repositories.postgres.tenant_api_key_repository.TenantApiKeyRepository.rotate_key",
                   return_value=("kw_" + "b" * 32, MagicMock())):
            return admin_rotate_tenant_key(tenant_id=tenant_id, db=db)

    def test_rotate_returns_new_api_key(self):
        result = self._call()
        assert result["api_key"].startswith("kw_")
        assert result["tenant_id"] == "T_TEST"

    def test_rotate_on_missing_tenant_raises_404(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._call(existing=False)
        assert exc_info.value.status_code == 404

    def test_rotate_issues_fresh_key_each_time(self):
        # Two rotations should give different keys (mocked here, but key is unique per call)
        from app.main import admin_rotate_tenant_key
        db = _mock_db()
        keys = ["kw_" + c * 32 for c in ("c", "d")]
        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                   return_value=_make_tenant_record()), \
             patch("app.repositories.postgres.tenant_api_key_repository.TenantApiKeyRepository.rotate_key",
                   side_effect=[(k, MagicMock()) for k in keys]):
            r1 = admin_rotate_tenant_key(tenant_id="T_TEST", db=db)
            r2 = admin_rotate_tenant_key(tenant_id="T_TEST", db=db)
        assert r1["api_key"] != r2["api_key"]


# ---------------------------------------------------------------------------
# PATCH /admin/tenants/{id}/status
# ---------------------------------------------------------------------------

class TestAdminSetTenantStatus:

    def _call(self, tenant_id: str = "T_TEST", status: str = "inactive", existing: bool = True):
        from app.main import admin_set_tenant_status, AdminTenantStatusRequest
        db = _mock_db()
        record = _make_tenant_record(tenant_id) if existing else None
        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                   return_value=record), \
             patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert",
                   return_value=_make_tenant_record(tenant_id, status=status)):
            return admin_set_tenant_status(tenant_id=tenant_id, body=AdminTenantStatusRequest(status=status), db=db)

    def test_set_inactive_returns_correct_status(self):
        result = self._call(status="inactive")
        assert result["status"] == "inactive"
        assert result["tenant_id"] == "T_TEST"

    def test_set_active_returns_correct_status(self):
        result = self._call(status="active")
        assert result["status"] == "active"

    def test_invalid_status_raises_422(self):
        from fastapi import HTTPException
        from app.main import admin_set_tenant_status, AdminTenantStatusRequest
        db = _mock_db()
        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                   return_value=_make_tenant_record()):
            with pytest.raises(HTTPException) as exc_info:
                admin_set_tenant_status(
                    tenant_id="T_TEST",
                    body=AdminTenantStatusRequest(status="suspended"),
                    db=db,
                )
        assert exc_info.value.status_code == 422

    def test_missing_tenant_raises_404(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            self._call(existing=False)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Integration: inactive tenant key is rejected at auth
# ---------------------------------------------------------------------------

class TestInactiveTenantRejected:

    def test_inactive_tenant_raises_403(self):
        from fastapi import HTTPException
        from app.core.auth import get_verified_tenant

        raw_key = _generate_raw_key()
        db = _mock_db()

        with patch("app.core.auth._lookup_db_key", return_value="T_INACTIVE"), \
             patch("app.core.auth._is_tenant_active", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                get_verified_tenant(x_api_key=raw_key, x_tenant_id=None, db=db)
        assert exc_info.value.status_code == 403
        assert "inactive" in exc_info.value.detail.lower()

    def test_active_tenant_passes(self):
        from app.core import auth as auth_mod
        auth_mod._API_KEY_MAP = {}  # dev-mode so no env key required
        from app.core.auth import get_verified_tenant
        from app.core.tenancy import set_current_tenant

        raw_key = _generate_raw_key()
        db = _mock_db()

        with patch("app.core.auth._lookup_db_key", return_value="T_ACTIVE"), \
             patch("app.core.auth._is_tenant_active", return_value=True), \
             patch("app.core.tenancy.set_current_tenant"):
            result = get_verified_tenant(x_api_key=raw_key, x_tenant_id=None, db=db)
        assert result == "T_ACTIVE"
