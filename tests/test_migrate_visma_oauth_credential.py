"""Tests for scripts/ops/migrate_visma_oauth_credential.py"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
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


class TestDockerPythonTransport:
    def test_docker_python_uses_stdin_not_shell_quoted_c_flag(self, mig):
        with patch.object(mig.subprocess, "run") as run_mock:
            run_mock.return_value = MagicMock(
                returncode=0,
                stdout='{"configured": true, "client_id_fingerprint": "abc"}',
                stderr="",
            )
            result = mig._docker_python("import json\nprint(json.dumps({'ok': True}))")

        assert result["ok"] is True
        kwargs = run_mock.call_args.kwargs
        assert "import json" in kwargs["input"]
        assert kwargs.get("encoding") == "utf-8"
        remote_cmd = run_mock.call_args.args[0][2]
        assert f"-w {mig.REMOTE_APP_WORKDIR}" in remote_cmd
        assert remote_cmd.endswith("python -")
        assert "python -c" not in remote_cmd

    def test_bootstrap_import_path_adds_app_root_when_present(self, mig, monkeypatch):
        monkeypatch.setattr(mig.sys, "path", [])

        def fake_resolve(self):
            return Path("/tmp/migrate_visma_oauth_credential.py")

        def fake_is_dir(self):
            normalized = str(self).replace("\\", "/").rstrip("/")
            return normalized.endswith("/app/app") or normalized == "/app/app"

        monkeypatch.setattr(mig.Path, "resolve", fake_resolve)
        monkeypatch.setattr(mig.Path, "is_dir", fake_is_dir)

        mig._bootstrap_import_path()

        assert mig.sys.path and mig.sys.path[0] in {"/app", "\\app"}


class TestRemoteImportExecution:
    def test_ssh_remote_import_uses_app_workdir_and_payload_path(self, mig):
        with patch.object(mig, "_docker_cp_host_to_container") as cp_mock:
            with patch.object(mig.subprocess, "run") as run_mock:
                run_mock.return_value = MagicMock(
                    returncode=0,
                    stdout='{"status": "imported"}',
                    stderr="",
                )
                mig._ssh_remote_import(
                    "/tmp/visma_oauth_migration_payload_host.json",
                    "/tmp/visma_oauth_migration_payload.json",
                    False,
                )

        assert cp_mock.call_count == 2
        remote_cmd = run_mock.call_args.args[0][2]
        assert f"-w {mig.REMOTE_APP_WORKDIR}" in remote_cmd
        assert "--remote-import" in remote_cmd
        assert "--payload /tmp/visma_oauth_migration_payload.json" in remote_cmd
        assert "--replace" not in remote_cmd
        assert "super-secret" not in remote_cmd

    def test_ssh_remote_import_failure_does_not_include_payload_contents(self, mig):
        with patch.object(mig, "_docker_cp_host_to_container"):
            with patch.object(mig.subprocess, "run") as run_mock:
                run_mock.return_value = MagicMock(
                    returncode=1,
                    stdout="",
                    stderr="ModuleNotFoundError: No module named 'app'",
                )
                with pytest.raises(mig.MigrationError, match="Remote import failed"):
                    mig._ssh_remote_import(
                        "/tmp/host-payload.json",
                        "/tmp/visma_oauth_migration_payload.json",
                        False,
                    )

        remote_cmd = run_mock.call_args.args[0][2]
        assert "payload.json" not in remote_cmd or remote_cmd.endswith(
            "--payload /tmp/visma_oauth_migration_payload.json"
        )

    def test_run_migrate_cleans_local_temp_when_remote_import_fails(self, mig, tmp_path):
        mig.TEMP_DIR = tmp_path
        payload_path = tmp_path / "visma_oauth_migration_test.json"
        payload_path.write_text('{"access_token":"secret-at"}', encoding="utf-8")

        with patch.object(mig, "get_settings", return_value=SimpleNamespace(
            VISMA_CLIENT_ID="id", VISMA_CLIENT_SECRET="secret",
        )):
            with patch.object(mig, "fetch_remote_client_fingerprint", return_value="fp"):
                with patch.object(mig, "remote_production_credential_exists", return_value=False):
                    with patch.object(mig, "SessionLocal", return_value=MagicMock()):
                        with patch.object(
                            mig,
                            "run_local_validation",
                            return_value=({"status": "validated"}, {"access_token": "secret-at"}),
                        ):
                            with patch.object(mig, "write_secure_payload", return_value=payload_path):
                                with patch.object(mig, "_scp_script_to_remote"):
                                    with patch.object(mig, "_scp_to_remote"):
                                        with patch.object(
                                            mig,
                                            "_ssh_remote_import",
                                            side_effect=mig.MigrationError("Remote import failed"),
                                        ):
                                            with patch.object(mig, "_ssh_delete_remote") as delete_mock:
                                                with pytest.raises(mig.MigrationError):
                                                    mig.run_migrate(replace=False)

        assert not payload_path.exists()
        delete_mock.assert_called()


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
