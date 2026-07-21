"""Slice C Commit 4 — end-to-end customer settings integration gates."""

from __future__ import annotations

import copy
import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.admin.customer_settings.readiness import mark_readiness_stale_domains
from app.admin.customer_settings.service import patch_domain_settings, preview_domain_settings
from app.admin.tenant_lifecycle.models import TenantActivationSnapshotRecord
from app.api.dependencies import get_db
from app.main import app
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from tests.onboarding_db_tables import onboarding_sqlite_tables
from tests.test_customer_settings_backend import _active_tenant, _operator

TEST_ADMIN_API_KEY = "test-customer-settings-integration-gate-key"


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


@pytest.fixture
def tenant(db):
    record = _active_tenant()
    db.add(record)
    db.add(
        OAuthCredentialRecord(
            tenant_id=record.tenant_id,
            provider="visma",
            access_token="static-visma-access",
            refresh_token="static-visma-refresh",
        )
    )
    db.add(
        TenantActivationSnapshotRecord(
            id="snap-gate-1",
            tenant_id=record.tenant_id,
            config_version=1,
            plan_hash="abc",
            readiness_check_version=1,
            snapshot_json={"seed": True},
            activated_by_operator_id="op-seed",
        )
    )
    db.commit()
    return record


@pytest.fixture
def tenant_b(db):
    record = _active_tenant("T_OTHER", config_version=2)
    db.add(record)
    db.commit()
    return record


class TestCustomerSettingsIntegrationFlow:
    """Service-level integration gate matrix (items 1–15)."""

    def test_aggregate_get(self, db, tenant):
        from app.admin.customer_settings.service import get_customer_settings_view

        view = get_customer_settings_view(db, tenant.tenant_id, _operator())
        assert view["config_version"] == tenant.config_version
        assert "effective_readiness" in view

    def test_domain_get(self, db, tenant):
        from app.admin.customer_settings.service import get_domain_settings

        result = get_domain_settings(db, tenant.tenant_id, "routing", _operator())
        assert result["domain"] == "routing"

    def test_preview(self, db, tenant):
        preview = preview_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="modules",
            payload={"capabilities": ["customer_inquiries"]},
            operator=_operator(),
        )
        assert preview["valid"] is True
        assert "runtime_gates" in preview

    def test_patch_and_config_version_increment(self, db, tenant):
        before = tenant.config_version
        result = patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="identity",
            expected_config_version=before,
            payload={"timezone": "Europe/Helsinki"},
            operator=_operator(),
        )
        db.refresh(tenant)
        assert result["config_version"] == before + 1
        assert tenant.config_version == before + 1

    def test_readiness_invalidation_after_patch(self, db, tenant):
        tenant.settings = mark_readiness_stale_domains(tenant.settings or {}, [])
        db.commit()
        result = patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="routing",
            expected_config_version=tenant.config_version,
            payload={"route_overrides": {"invoice_generic": "finance"}},
            operator=_operator(),
        )
        assert "routing" in result["readiness_invalidated"]

    def test_runtime_projection_sync_fail_closed_no_expand(self, db, tenant):
        before_allowed = list(tenant.allowed_integrations)
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
        assert tenant.allowed_integrations == before_allowed
        preview = preview_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="integrations",
            payload={
                "selections": {
                    "google_sheets": {"selection_status": "selected_optional"},
                }
            },
            operator=_operator(),
        )
        assert "allowed_integrations" in preview["runtime_gates"]

    def test_audit_created_on_patch(self, db, tenant):
        before = db.query(AuditEventRecord).count()
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="identity",
            expected_config_version=tenant.config_version,
            payload={"phone": "+4612345678"},
            operator=_operator(),
            change_reason="gate test",
        )
        assert db.query(AuditEventRecord).count() == before + 1

    def test_activation_snapshot_unchanged(self, db, tenant):
        snap = db.query(TenantActivationSnapshotRecord).filter_by(tenant_id=tenant.tenant_id).one()
        before = copy.deepcopy(snap.snapshot_json)
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="identity",
            expected_config_version=tenant.config_version,
            payload={"language": "sv"},
            operator=_operator(),
        )
        db.refresh(snap)
        assert snap.snapshot_json == before

    def test_credentials_unchanged(self, db, tenant):
        before = db.get(
            OAuthCredentialRecord,
            {"tenant_id": tenant.tenant_id, "provider": "visma"},
        )
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="integrations",
            expected_config_version=tenant.config_version,
            payload={
                "finance_destination": {
                    "choice": "manual_accounting_routing",
                    "visma_disposition": "selected_optional",
                }
            },
            operator=_operator(),
        )
        after = db.get(
            OAuthCredentialRecord,
            {"tenant_id": tenant.tenant_id, "provider": "visma"},
        )
        assert before.access_token == after.access_token

    def test_external_writes_unchanged_on_selection_patch(self, db, tenant):
        writes_before = list(tenant.settings["integrations"].get("enabled_external_writes") or [])
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
        assert tenant.settings["integrations"].get("enabled_external_writes") == writes_before

    def test_unknown_domain_fail_closed(self, db, tenant):
        with pytest.raises(ValueError, match="Unknown settings domain"):
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="not-a-domain",
                expected_config_version=tenant.config_version,
                payload={},
                operator=_operator(),
            )

    def test_role_matrix_operations_routing_only(self, db, tenant):
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="routing",
            expected_config_version=tenant.config_version,
            payload={"route_overrides": {"invoice_generic": "finance"}},
            operator=_operator(role="operations"),
        )
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="integrations",
                expected_config_version=tenant.config_version,
                payload={"selections": {"fortnox": {"selection_status": "not_selected"}}},
                operator=_operator(role="operations"),
            )
        assert exc.value.status_code == 403

    def test_tenant_isolation_write(self, db, tenant, tenant_b):
        snap_a = copy.deepcopy(tenant.settings)
        patch_domain_settings(
            db,
            tenant_id=tenant_b.tenant_id,
            domain="identity",
            expected_config_version=tenant_b.config_version,
            payload={"timezone": "Europe/Oslo"},
            operator=_operator(),
        )
        db.refresh(tenant)
        assert tenant.settings == snap_a
        db.refresh(tenant_b)
        assert tenant_b.settings["company"]["timezone"] == "Europe/Oslo"

    def test_invalid_visma_disposition_rejected(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="integrations",
                expected_config_version=tenant.config_version,
                payload={
                    "finance_destination": {
                        "choice": "manual_accounting_routing",
                        "visma_disposition": "selected_required",
                    }
                },
                operator=_operator(),
            )
        assert exc.value.status_code == 422

    def test_preview_runtime_gates_for_integrations(self, db, tenant):
        preview = preview_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="integrations",
            payload={
                "selections": {
                    "google_sheets": {"selection_status": "selected_optional"},
                }
            },
            operator=_operator(),
        )
        assert preview["valid"] is True
        assert "allowed_integrations" in preview["runtime_gates"]


class TestCustomerSettingsHttpIntegrationGates:
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
    def client(self, db, tenant):
        def override_get_db():
            yield db

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app, raise_server_exceptions=False)
        yield client
        app.dependency_overrides.clear()

    @pytest.fixture
    def admin_headers(self):
        return {
            "X-Admin-API-Key": TEST_ADMIN_API_KEY,
            "Origin": "http://testserver",
        }

    def test_http_finance_destination_manual_routing(self, client, admin_headers, tenant, db):
        response = client.patch(
            f"/admin/tenants/{tenant.tenant_id}/settings/integrations",
            headers=admin_headers,
            json={
                "expected_config_version": tenant.config_version,
                "payload": {
                    "finance_destination": {
                        "choice": "manual_accounting_routing",
                        "visma_disposition": "not_selected",
                    }
                },
            },
        )
        assert response.status_code == 200
        db.refresh(tenant)
        assert tenant.config_version == 4

    def test_http_cross_tenant_patch_404_or_409(self, client, admin_headers, tenant, tenant_b):
        response = client.patch(
            f"/admin/tenants/{tenant_b.tenant_id}/settings/identity",
            headers=admin_headers,
            json={
                "expected_config_version": tenant.config_version,
                "payload": {"timezone": "Europe/Oslo"},
            },
        )
        assert response.status_code in {404, 409}
