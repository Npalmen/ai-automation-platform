"""Tests for scripts/ops/migrate_visma_oauth_credential.py"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parents[1]


def _load_migration_module():
    path = REPO / "scripts" / "ops" / "migrate_visma_oauth_credential.py"
    spec = importlib.util.spec_from_file_location("migrate_visma_oauth_credential", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mig():
    return _load_migration_module()


@pytest.fixture
def sample_record():
    return SimpleNamespace(
        tenant_id="T_NIKLAS_DEMO_001",
        provider="visma",
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        scopes="ea:api offline_access",
        metadata_json={"connected_via": "oauth_callback", "token_type": "Bearer"},
    )


@pytest.fixture
def local_settings():
    return SimpleNamespace(
        VISMA_CLIENT_ID="same-client-id",
        VISMA_CLIENT_SECRET="same-client-secret",
        VISMA_API_URL="https://eaccountingapi.vismaonline.com/v2",
    )


class TestSourceValidation:
    def test_tenant_mismatch_raises(self, mig):
        with pytest.raises(mig.MigrationError, match="Source tenant must be"):
            mig.assert_tenant_id("OTHER_TENANT")

    def test_missing_credential_raises(self, mig):
        db = MagicMock()
        with patch.object(mig.OAuthCredentialRepository, "get", return_value=None):
            with pytest.raises(mig.MigrationError, match="No local Visma credential"):
                mig.load_source_credential(db)

    def test_missing_refresh_token_raises(self, mig, sample_record):
        sample_record.refresh_token = ""
        with pytest.raises(mig.MigrationError, match="missing refresh_token"):
            mig.require_refresh_token(sample_record)

    def test_refresh_failure_raises(self, mig, sample_record):
        with patch.object(mig, "refresh_access_token", side_effect=RuntimeError("boom")):
            with pytest.raises(mig.MigrationError, match="Visma refresh failed"):
                mig.refresh_source_credential(sample_record)


class TestClientIdMatch:
    def test_client_ids_match_without_printing_values(self, mig, local_settings):
        fp = mig.fingerprint_secret(local_settings.VISMA_CLIENT_ID)
        assert mig.client_ids_match(local_settings, fp) is True
        assert mig.client_ids_match(local_settings, "different") is False


class TestProductionIdempotency:
    def test_existing_credential_without_replace_raises(self, mig):
        db = MagicMock()
        payload = {
            "tenant_id": "T_NIKLAS_DEMO_001",
            "provider": "visma",
            "access_token": "at",
            "refresh_token": "rt",
            "expires_at": "2026-12-31T00:00:00+00:00",
            "scopes": "ea:api",
            "metadata_json": {},
            "client_id_fingerprint": mig.fingerprint_secret("same-client-id"),
        }
        settings = SimpleNamespace(VISMA_CLIENT_ID="same-client-id")
        with patch.object(mig, "production_credential_exists", return_value=True):
            with patch.object(
                mig,
                "get_tenant_integration_snapshot",
                return_value={"found": True, "allowed_integrations": ["google_mail"], "auto_actions": {}},
            ):
                with pytest.raises(mig.MigrationError, match="--replace"):
                    mig.apply_production_import(db, payload, replace=False, settings=settings)

    def test_upsert_success_and_audit_created(self, mig):
        db = MagicMock()
        payload = {
            "tenant_id": "T_NIKLAS_DEMO_001",
            "provider": "visma",
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": "2026-12-31T00:00:00+00:00",
            "scopes": "ea:api offline_access",
            "metadata_json": {"connected_via": "oauth_credential_migration"},
            "client_id_fingerprint": mig.fingerprint_secret("same-client-id"),
            "validation": {"refresh_ok": True},
        }
        settings = SimpleNamespace(VISMA_CLIENT_ID="same-client-id")
        tenant_snapshot = {
            "found": True,
            "allowed_integrations": ["google_mail", "google_sheets"],
            "auto_actions": {"lead": False},
        }

        with patch.object(mig, "production_credential_exists", return_value=False):
            with patch.object(mig, "get_tenant_integration_snapshot", return_value=tenant_snapshot):
                with patch.object(mig.OAuthCredentialRepository, "upsert") as upsert:
                    with patch.object(mig, "create_audit_event") as audit:
                        result = mig.apply_production_import(
                            db, payload, replace=False, settings=settings
                        )

        upsert.assert_called_once()
        audit.assert_called_once()
        audit_kwargs = audit.call_args.kwargs
        assert audit_kwargs["tenant_id"] == "T_NIKLAS_DEMO_001"
        assert audit_kwargs["category"] == "integration"
        assert audit_kwargs["action"] == "visma_oauth_credential_migrated"
        assert audit_kwargs["status"] == "success"
        assert "access_token" not in audit_kwargs["details"]
        assert "refresh_token" not in audit_kwargs["details"]
        assert result["status"] == "imported"
        assert result["tenant_config_unchanged"] is True


class TestOutputSafety:
    def test_no_secrets_in_logs_or_output(self, mig, sample_record, local_settings):
        refreshed = {
            "access_token": "super-secret-access",
            "refresh_token": "super-secret-refresh",
            "expires_at": datetime(2026, 12, 31, tzinfo=timezone.utc),
            "scopes": "ea:api",
        }
        payload = mig.build_migration_payload(
            sample_record, refreshed, local_settings=local_settings
        )
        rendered = mig.safe_json_dumps(
            payload,
            secrets=[payload["access_token"], payload["refresh_token"]],
        )
        assert "super-secret-access" not in rendered
        assert "super-secret-refresh" not in rendered
        assert "<redacted>" in rendered

    def test_ensure_no_secrets_in_text_raises(self, mig):
        with pytest.raises(mig.MigrationError, match="secret values"):
            mig.ensure_no_secrets_in_text("contains secret-value", ["secret-value"])


class TestPayloadAndCleanup:
    def test_write_and_delete_secure_payload(self, mig, tmp_path):
        mig.TEMP_DIR = tmp_path
        payload = {
            "tenant_id": "T_NIKLAS_DEMO_001",
            "access_token": "secret-access",
            "refresh_token": "secret-refresh",
        }
        with patch.object(mig.os, "chmod") as chmod_mock:
            path = mig.write_secure_payload(payload)
            chmod_mock.assert_called_once_with(path, 0o600)
        assert path.exists()
        loaded = mig.read_secure_payload(path)
        assert loaded["tenant_id"] == "T_NIKLAS_DEMO_001"
        mig.delete_secure_file(path)
        assert not path.exists()

    def test_metadata_merge_includes_migration_fields(self, mig, sample_record, local_settings):
        refreshed = {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_at": datetime(2026, 12, 31, tzinfo=timezone.utc),
            "scopes": "ea:api",
        }
        payload = mig.build_migration_payload(
            sample_record, refreshed, local_settings=local_settings
        )
        meta = payload["metadata_json"]
        assert meta["connected_via"] == "oauth_credential_migration"
        assert meta["source_environment"] == "local"
        assert meta["migrated_at"]
        assert meta["token_type"] == "Bearer"


class TestTenantConfigUnchanged:
    def test_tenant_config_change_aborts_import(self, mig):
        db = MagicMock()
        payload = {
            "tenant_id": "T_NIKLAS_DEMO_001",
            "provider": "visma",
            "access_token": "at",
            "refresh_token": "rt",
            "expires_at": "2026-12-31T00:00:00+00:00",
            "scopes": "ea:api",
            "metadata_json": {},
            "client_id_fingerprint": mig.fingerprint_secret("same-client-id"),
        }
        settings = SimpleNamespace(VISMA_CLIENT_ID="same-client-id")
        before = {"found": True, "allowed_integrations": ["google_mail"], "auto_actions": {}}
        after = {
            "found": True,
            "allowed_integrations": ["google_mail", "visma"],
            "auto_actions": {},
        }

        with patch.object(mig, "production_credential_exists", return_value=False):
            with patch.object(mig, "get_tenant_integration_snapshot", side_effect=[before, after]):
                with patch.object(mig.OAuthCredentialRepository, "upsert"):
                    with patch.object(mig, "create_audit_event"):
                        with pytest.raises(mig.MigrationError, match="Tenant config changed"):
                            mig.apply_production_import(db, payload, replace=False, settings=settings)


class TestCliValidationOnly:
    def test_validate_only_does_not_migrate(self, mig, sample_record, local_settings):
        db = MagicMock()
        with patch.object(mig, "SessionLocal", return_value=db):
            with patch.object(mig, "get_settings", return_value=local_settings):
                with patch.object(mig, "fetch_remote_client_fingerprint", return_value=mig.fingerprint_secret("same-client-id")):
                    with patch.object(mig.OAuthCredentialRepository, "get", return_value=sample_record):
                        with patch.object(
                            mig,
                            "refresh_access_token",
                            return_value={
                                "access_token": "new-at",
                                "refresh_token": "new-rt",
                                "expires_at": datetime(2026, 12, 31, tzinfo=timezone.utc),
                                "scopes": "ea:api",
                            },
                        ):
                            with patch.object(
                                mig,
                                "optional_company_test",
                                return_value={"company_test_ok": True, "has_company_name": True},
                            ):
                                with patch.object(mig, "run_migrate") as migrate:
                                    rc = mig.main(["--validate-only"])
        migrate.assert_not_called()
        assert rc == 0

    def test_migrate_short_circuits_when_production_exists_without_replace(self, mig, local_settings):
        with patch.object(mig, "get_settings", return_value=local_settings):
            with patch.object(mig, "fetch_remote_client_fingerprint", return_value="fp"):
                with patch.object(mig, "remote_production_credential_exists", return_value=True):
                    rc = mig.main([])
        assert rc == 1
