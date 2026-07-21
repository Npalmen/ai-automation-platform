"""Google Sheets OAuth fallback vs active customer settings (Slice C Commit 5)."""

from __future__ import annotations

import copy
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.admin.customer_settings.service import patch_domain_settings
from app.api.dependencies import get_db
from app.integrations.google.sheets_auth import resolve_google_sheets_access_token
from app.main import app
from app.repositories.postgres.database import Base
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from tests.onboarding_db_tables import onboarding_sqlite_tables
from tests.test_customer_settings_backend import _active_tenant, _operator

TEST_ADMIN_API_KEY = "test-google-sheets-settings-gate-key"


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = onboarding_sqlite_tables()
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _tenant_with_google_sheets(tenant_id: str = "T_GS_SETTINGS") -> TenantConfigRecord:
    record = _active_tenant(tenant_id)
    settings = dict(record.settings or {})
    settings["google_sheets"] = {
        "spreadsheet_id": "sheet-abc-123",
        "worksheet_name": "Leads",
    }
    record.settings = settings
    return record


class TestGoogleSheetsAuthFallback:
    def test_platform_refresh_used_when_tenant_has_no_access_token_override(self):
        with (
            patch("app.integrations.google.sheets_auth.get_settings") as mock_settings,
            patch(
                "app.integrations.google.sheets_auth.refresh_access_token",
                return_value="refreshed_token",
            ) as mock_refresh,
        ):
            mock_settings.return_value.GOOGLE_OAUTH_REFRESH_TOKEN = "rt"
            mock_settings.return_value.GOOGLE_OAUTH_CLIENT_ID = "cid"
            mock_settings.return_value.GOOGLE_OAUTH_CLIENT_SECRET = "secret"
            token = resolve_google_sheets_access_token(
                {"spreadsheet_id": "sheet-abc-123"},
            )

        assert token == "refreshed_token"
        mock_refresh.assert_called_once()

    def test_tenant_access_token_override_still_wins_over_platform_refresh(self):
        with patch(
            "app.integrations.google.sheets_auth.refresh_access_token",
            return_value="refreshed_token",
        ) as mock_refresh:
            token = resolve_google_sheets_access_token(
                {"access_token": "tenant-only-token", "spreadsheet_id": "sheet-abc-123"},
            )

        assert token == "tenant-only-token"
        mock_refresh.assert_not_called()


class TestGoogleSheetsCustomerSettingsIsolation:
    def test_integrations_patch_preserves_google_sheets_settings_envelope(self, db):
        tenant = _tenant_with_google_sheets()
        db.add(tenant)
        db.commit()
        snapshot = copy.deepcopy(tenant.settings)

        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="integrations",
            expected_config_version=tenant.config_version,
            payload={
                "selections": {
                    "google_sheets": {"selection_status": "selected_optional"},
                }
            },
            operator=_operator(),
        )
        db.refresh(tenant)

        assert tenant.settings["google_sheets"] == snapshot["google_sheets"]
        assert tenant.settings["google_sheets"]["spreadsheet_id"] == "sheet-abc-123"

    def test_tenant_isolation_preserves_peer_google_sheets_settings(self, db):
        tenant_a = _tenant_with_google_sheets("T_GS_A")
        tenant_b = _tenant_with_google_sheets("T_GS_B")
        tenant_b.settings = {
            **tenant_b.settings,
            "google_sheets": {"spreadsheet_id": "sheet-b-only", "worksheet_name": "Other"},
        }
        db.add_all([tenant_a, tenant_b])
        db.commit()
        snapshot_a = copy.deepcopy(tenant_a.settings)

        patch_domain_settings(
            db,
            tenant_id=tenant_b.tenant_id,
            domain="integrations",
            expected_config_version=tenant_b.config_version,
            payload={
                "selections": {
                    "google_sheets": {"selection_status": "selected_required"},
                }
            },
            operator=_operator(),
        )
        db.refresh(tenant_a)
        db.refresh(tenant_b)

        assert tenant_a.settings == snapshot_a
        assert tenant_b.settings["google_sheets"]["spreadsheet_id"] == "sheet-b-only"


class TestGoogleSheetsCustomerSettingsHttpIsolation:
    @pytest.fixture(autouse=True)
    def http_env(self):
        with patch.dict(
            os.environ,
            {"ADMIN_API_KEY": TEST_ADMIN_API_KEY, "ADMIN_ROLE": "admin"},
            clear=False,
        ):
            from app.core.settings import get_settings

            get_settings.cache_clear()
            yield
            get_settings.cache_clear()

    @pytest.fixture
    def client(self, db):
        tenant = _tenant_with_google_sheets("T_GS_HTTP")
        db.add(tenant)
        db.commit()

        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app, raise_server_exceptions=False)
        yield client, tenant
        app.dependency_overrides.clear()

    def test_http_aggregate_scoped_to_requested_tenant(self, client):
        test_client, tenant = client
        headers = {"X-Admin-API-Key": TEST_ADMIN_API_KEY, "Origin": "http://testserver"}
        response = test_client.get(
            f"/admin/tenants/{tenant.tenant_id}/settings",
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"] == tenant.tenant_id
        assert body["domains"]["identity"]["name"] == tenant.name
        wrong = test_client.get(
            "/admin/tenants/T_MISSING_TENANT/settings",
            headers=headers,
        )
        assert wrong.status_code == 404
