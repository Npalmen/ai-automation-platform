"""Tests for GET /admin/system/status (Kapitel 8)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.admin.operations_overview import _derive_scheduler_signal
from app.admin.system_status import get_system_status
from app.admin.system_status_schemas import SystemStatusResponse
from app.admin.system_status_sources import DatabaseUnreachable
from app.repositories.postgres.database import Base
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.domain.integrations.models import IntegrationEvent


def _utc(dt: str) -> datetime:
    return datetime.fromisoformat(dt)


def _settings(tmp_path, **kwargs):
    defaults = {
        "ADMIN_API_KEY": "test-admin-key",
        "APP_NAME": "Test",
        "ENV": "test",
        "BACKUP_STATUS_FILE": str(tmp_path / "backup_status.json"),
        "RESTORE_STATUS_FILE": str(tmp_path / "restore_status.json"),
        "BUILD_METADATA_PATH": str(tmp_path / "build-metadata.json"),
        "BACKUP_EXPECTED_INTERVAL_HOURS": 24,
        "BACKUP_MAX_AGE_HOURS": 25,
        "RESTORE_TEST_MAX_AGE_DAYS": 30,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _write_json(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture()
def system_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            TenantConfigRecord.__table__,
            JobRecord.__table__,
            IntegrationEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _tenant(settings=None):
    record = MagicMock()
    record.settings = settings or {}
    return record


def _make_sqlite_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        bind=engine,
        tables=[
            TenantConfigRecord.__table__,
            JobRecord.__table__,
            IntegrationEvent.__table__,
        ],
    )
    Session = sessionmaker(bind=engine)
    return Session()


class TestSchedulerSignalFix:
    def test_nested_scheduler_run_mode_paused(self):
        result = _derive_scheduler_signal(
            [_tenant(settings={"scheduler": {"run_mode": "paused"}})]
        )
        assert result["status"] == "paused"

    def test_legacy_flat_run_mode_paused(self):
        result = _derive_scheduler_signal([_tenant(settings={"run_mode": "paused"})])
        assert result["status"] == "paused"


class TestSystemStatusService:
    def test_build_time_not_deploy_time(self, system_db, tmp_path):
        _write_json(
            tmp_path / "build-metadata.json",
            {
                "schema_version": 1,
                "commit_sha": "abc1234567890",
                "build_time": "2026-07-17T10:00:00Z",
                "release_id": "ci-abc1234",
                "source": "docker_build",
            },
        )
        result = get_system_status(system_db, app_settings=_settings(tmp_path))
        assert result.deployment.current_build.build_time is not None
        assert result.deployment.last_deploy.deployed_at is None
        assert result.deployment.last_deploy.status == "unknown"

    def test_backup_and_restore_separate(self, system_db, tmp_path):
        recent = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _write_json(
            tmp_path / "backup_status.json",
            {
                "schema_version": 1,
                "backup_id": "ai_platform_2026-07-17-020000",
                "started_at": recent,
                "completed_at": recent,
                "status": "success",
                "size_bytes": 1000,
                "retention_days": 30,
                "archive_integrity_verified": True,
                "error_code": None,
            },
        )
        result = get_system_status(system_db, app_settings=_settings(tmp_path))
        assert result.resilience.last_backup.status in ("healthy", "warning")
        assert result.resilience.last_restore_test.status == "not_configured"

    def test_deploy_readiness_gap_does_not_fail_runtime(self, system_db, tmp_path):
        result = get_system_status(system_db, app_settings=_settings(tmp_path))
        assert result.deploy_readiness_status.status == "warning"
        assert result.runtime_status.status in ("healthy", "warning", "unknown")
        assert result.runtime_status.status != "failed"

    def test_limitations_include_metadata_log_note(self, system_db, tmp_path):
        result = get_system_status(system_db, app_settings=_settings(tmp_path))
        assert any("skriptlogg" in item for item in result.limitations)

    def test_stale_backup_metadata(self, system_db, tmp_path):
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _write_json(
            tmp_path / "backup_status.json",
            {
                "schema_version": 1,
                "backup_id": "old",
                "started_at": old,
                "completed_at": old,
                "status": "success",
                "size_bytes": 1000,
                "retention_days": 30,
                "archive_integrity_verified": True,
                "error_code": None,
            },
        )
        result = get_system_status(system_db, app_settings=_settings(tmp_path))
        assert result.resilience.last_backup.freshness == "stale"

    def test_no_secrets_in_response(self, system_db, tmp_path):
        result = get_system_status(
            system_db,
            app_settings=_settings(tmp_path, ADMIN_API_KEY="super-secret"),
        )
        blob = SystemStatusResponse.model_validate(
            result.model_dump()
        ).model_dump_json()
        assert "super-secret" not in blob
        assert "/opt/krowolf" not in blob
        assert "DATABASE_URL" not in blob


class TestSystemStatusRoutes:
    def test_requires_auth(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/admin/system/status").status_code == 401

    def test_tenant_key_denied(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/admin/system/status",
            headers={"X-API-Key": "tenant-key"},
        )
        assert response.status_code == 401

    def test_read_only_allowed(self, tmp_path):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.core.admin_auth.resolve_authenticated_operator") as resolve:
            resolve.return_value = {
                "id": "op",
                "display_name": "Op",
                "role": "read_only",
            }
            with patch("app.admin.system_status.get_system_status") as mock_status:
                mock_status.return_value = get_system_status(
                    _make_sqlite_session(),
                    app_settings=_settings(tmp_path),
                )
                response = client.get(
                    "/admin/system/status",
                    headers={"X-Admin-API-Key": "test-admin-key"},
                )
        assert response.status_code == 200

    def test_super_admin_allowed(self, tmp_path):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.core.admin_auth.resolve_authenticated_operator") as resolve:
            resolve.return_value = {
                "id": "op",
                "display_name": "Op",
                "role": "super_admin",
            }
            with patch("app.admin.system_status.get_system_status") as mock_status:
                mock_status.return_value = get_system_status(
                    _make_sqlite_session(),
                    app_settings=_settings(tmp_path),
                )
                response = client.get(
                    "/admin/system/status",
                    headers={"X-Admin-API-Key": "test-admin-key"},
                )
        assert response.status_code == 200
        SystemStatusResponse.model_validate(response.json())

    def test_database_unreachable_returns_503(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.core.admin_auth.resolve_authenticated_operator") as resolve:
            resolve.return_value = {
                "id": "op",
                "display_name": "Op",
                "role": "operations",
            }
            with patch("app.admin.system_status.get_system_status") as mock_status:
                mock_status.side_effect = DatabaseUnreachable()
                response = client.get(
                    "/admin/system/status",
                    headers={"X-Admin-API-Key": "test-admin-key"},
                )
        assert response.status_code == 503
