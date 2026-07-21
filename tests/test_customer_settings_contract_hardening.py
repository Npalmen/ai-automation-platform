"""Customer settings contract hardening tests (Slice C Commit 2B)."""

from __future__ import annotations

import copy
import os
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from app.admin.customer_settings.automation_projection import compute_automation_runtime_projection
from app.admin.customer_settings.readiness import compute_customer_settings_readiness
from app.admin.customer_settings.service import (
    get_customer_settings_view,
    patch_domain_settings,
    preview_domain_settings,
)
from app.admin.customer_settings.validation import validate_domain_config
from app.admin.tenant_lifecycle.models import TenantActivationSnapshotRecord
from app.main import app
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from tests.onboarding_db_tables import onboarding_sqlite_tables
from tests.test_customer_settings_backend import _active_tenant, _operator


def _commit_settings(db, tenant):
    flag_modified(tenant, "settings")
    db.commit()
    db.refresh(tenant)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
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
            id="snap-1",
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


class TestAggregateReadiness:
    def test_required_integration_disconnected_is_blocker(self, db, tenant):
        tenant.settings["integrations"]["selections"]["google_mail"]["selection_status"] = (
            "selected_required"
        )
        tenant.settings["integrations"]["verification"] = {}
        db.commit()
        readiness = compute_customer_settings_readiness(db, tenant)
        assert readiness["overall_status"] == "not_ready"
        assert any("google_mail" in item["id"] for item in readiness["blockers"])

    def test_optional_disconnected_is_neutral(self, db, tenant):
        tenant.settings["integrations"]["selections"]["fortnox"]["selection_status"] = (
            "selected_optional"
        )
        db.commit()
        readiness = compute_customer_settings_readiness(db, tenant)
        assert not any("fortnox" in item["id"] for item in readiness["blockers"])

    def test_fortnox_not_selected_no_blocker(self, db, tenant):
        readiness = compute_customer_settings_readiness(db, tenant)
        assert not any("fortnox" in item["id"] for item in readiness["blockers"])

    def test_finance_destination_without_implementation_blocks(self, db, tenant):
        tenant.settings["integrations"]["selections"]["visma"]["selection_status"] = "not_selected"
        tenant.settings["integrations"]["group_implementations"] = {}
        tenant.settings["routing"] = {"route_overrides": {}}
        _commit_settings(db, tenant)
        readiness = compute_customer_settings_readiness(db, tenant)
        assert any(
            item["id"] == "finance_destination.not_configured" for item in readiness["blockers"]
        )

    def test_manual_routing_without_valid_route_blocks(self, db, tenant):
        tenant.settings["integrations"]["selections"]["visma"]["selection_status"] = "not_selected"
        tenant.settings["integrations"]["group_implementations"] = {
            "finance_destination": {"type": "manual_accounting_routing"}
        }
        tenant.settings["routing"] = {"route_overrides": {"invoice_generic": "support"}}
        _commit_settings(db, tenant)
        readiness = compute_customer_settings_readiness(db, tenant)
        assert any(
            "manual_accounting_routing_missing_routing" in item["id"]
            for item in readiness["blockers"]
        )

    def test_valid_manual_routing_satisfies_group(self, db, tenant):
        tenant.settings["integrations"]["selections"]["visma"]["selection_status"] = "not_selected"
        tenant.settings["integrations"]["group_implementations"] = {
            "finance_destination": {"type": "manual_accounting_routing"}
        }
        tenant.settings["routing"] = {
            "route_overrides": {"invoice_generic": "finance"},
        }
        _commit_settings(db, tenant)
        readiness = compute_customer_settings_readiness(db, tenant)
        finance = readiness["integration_group_status"]["finance_destination"]
        assert finance["active_implementation"] == "manual_accounting_routing"
        assert finance["accounting_routing_valid"] is True

    def test_stale_domain_after_patch(self, db, tenant):
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="identity",
            expected_config_version=3,
            payload={"timezone": "Europe/Oslo"},
            operator=_operator(),
        )
        view = get_customer_settings_view(db, tenant.tenant_id, _operator())
        readiness = view["effective_readiness"]
        assert readiness["is_stale"] is True
        assert "identity" in readiness["stale_domains"]

    def test_aggregate_get_is_read_only(self, db, tenant):
        version_before = tenant.config_version
        settings_before = copy.deepcopy(tenant.settings)
        audit_before = db.query(AuditEventRecord).count()
        get_customer_settings_view(db, tenant.tenant_id, _operator())
        db.refresh(tenant)
        assert tenant.config_version == version_before
        assert tenant.settings == settings_before
        assert db.query(AuditEventRecord).count() == audit_before


class TestAutomationProjection:
    def test_automation_patch_syncs_auto_actions(self, db, tenant):
        scheduler_before = copy.deepcopy(tenant.settings["scheduler"])
        writes_before = list(
            tenant.settings["integrations"].get("enabled_external_writes") or []
        )
        result = patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="automation",
            expected_config_version=3,
            payload={"preset_key": "approval_first", "preset_version": 1},
            operator=_operator(),
        )
        db.refresh(tenant)
        assert result["config_version"] == 4
        assert tenant.auto_actions.get("invoice") == "semi"
        assert tenant.settings["scheduler"] == scheduler_before
        assert tenant.settings["integrations"].get("enabled_external_writes") == writes_before

    def test_preview_shows_same_projection_without_write(self, db, tenant):
        payload = {"preset_key": "prepare_only", "preset_version": 1}
        preview = preview_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="automation",
            payload=payload,
            operator=_operator(),
        )
        version_before = tenant.config_version
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="automation",
            expected_config_version=3,
            payload=payload,
            operator=_operator(),
        )
        db.refresh(tenant)
        assert tenant.config_version == version_before + 1
        assert preview["automation_projection"]["auto_actions"] == tenant.auto_actions

    def test_client_auto_actions_rejected(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="automation",
                expected_config_version=3,
                payload={"auto_actions": {"lead": "auto"}},
                operator=_operator(),
            )
        assert exc.value.status_code == 422

    def test_client_effective_policy_snapshot_rejected(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="automation",
                expected_config_version=3,
                payload={
                    "preset_key": "approval_first",
                    "effective_policy_snapshot": {"auto_actions": {"lead": "auto"}},
                },
                operator=_operator(),
            )
        assert exc.value.status_code == 422

    def test_scheduler_unchanged(self, db, tenant):
        before = copy.deepcopy(tenant.settings["scheduler"])
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="automation",
            expected_config_version=3,
            payload={"preset_key": "controlled_automation", "preset_version": 1},
            operator=_operator(),
        )
        db.refresh(tenant)
        assert tenant.settings["scheduler"] == before

    def test_external_writes_unchanged(self, db, tenant):
        before = list(tenant.settings["integrations"].get("enabled_external_writes") or [])
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="automation",
            expected_config_version=3,
            payload={"preset_key": "approval_first", "preset_version": 1},
            operator=_operator(),
        )
        db.refresh(tenant)
        assert tenant.settings["integrations"].get("enabled_external_writes") == before

    def test_version_bumps_exactly_once(self, db, tenant):
        result = patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="automation",
            expected_config_version=3,
            payload={"preset_key": "approval_first", "preset_version": 1},
            operator=_operator(),
        )
        assert result["config_version"] == 4

    def test_rollback_on_projection_failure(self, db, tenant):
        before_settings = copy.deepcopy(tenant.settings)
        before_version = tenant.config_version
        before_auto_actions = copy.deepcopy(tenant.auto_actions)
        cred_before = db.get(
            OAuthCredentialRecord,
            {"tenant_id": tenant.tenant_id, "provider": "visma"},
        )
        snap_before = db.query(TenantActivationSnapshotRecord).count()
        audit_before = db.query(AuditEventRecord).count()
        with patch(
            "app.admin.customer_settings.service.apply_runtime_projections",
            side_effect=RuntimeError("projection failed"),
        ):
            with pytest.raises(RuntimeError):
                patch_domain_settings(
                    db,
                    tenant_id=tenant.tenant_id,
                    domain="automation",
                    expected_config_version=3,
                    payload={"preset_key": "approval_first", "preset_version": 1},
                    operator=_operator(),
                )
        db.refresh(tenant)
        cred_after = db.get(
            OAuthCredentialRecord,
            {"tenant_id": tenant.tenant_id, "provider": "visma"},
        )
        assert tenant.settings == before_settings
        assert tenant.config_version == before_version
        assert tenant.auto_actions == before_auto_actions
        assert cred_before.access_token == cred_after.access_token
        assert db.query(TenantActivationSnapshotRecord).count() == snap_before
        assert db.query(AuditEventRecord).count() == audit_before

    def test_approval_first_downgrades_auto(self):
        projection = compute_automation_runtime_projection(
            {
                "automation": {
                    "preset_key": "controlled_automation",
                    "preset_version": 1,
                    "approval_first": True,
                },
                "capabilities": {"lead_management": True},
            },
            capability_keys=["lead_management"],
        )
        assert projection["auto_actions"].get("lead") == "semi"


class TestInvalidVsNotReady:
    def test_unknown_key_is_422(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="automation",
                expected_config_version=3,
                payload={"unknown_area": True},
                operator=_operator(),
            )
        assert exc.value.status_code == 422

    def test_invalid_preset_is_422(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="automation",
                expected_config_version=3,
                payload={"preset_key": "does_not_exist", "preset_version": 99},
                operator=_operator(),
            )
        assert exc.value.status_code == 422

    def test_not_ready_finance_destination_patch_allowed(self, db, tenant):
        tenant.settings["integrations"]["selections"]["visma"]["selection_status"] = "not_selected"
        tenant.settings["integrations"]["group_implementations"] = {}
        tenant.settings["routing"] = {"route_overrides": {"invoice_generic": "support"}}
        _commit_settings(db, tenant)
        result = patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="integrations",
            expected_config_version=3,
            payload={
                "finance_destination": {
                    "choice": "manual_accounting_routing",
                    "visma_disposition": "not_selected",
                }
            },
            operator=_operator(),
        )
        assert result["config_version"] == 4
        assert result["not_ready"] is True
        assert result["blockers"]

    def test_missing_visma_disposition_is_422(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="integrations",
                expected_config_version=3,
                payload={"finance_destination": {"choice": "manual_accounting_routing"}},
                operator=_operator(),
            )
        assert exc.value.status_code == 422


class TestCustomerSettingsHttpRoutes:
    @pytest.fixture
    def client(self, db, tenant):
        def override_get_db():
            yield db

        app.dependency_overrides[__import__("app.api.dependencies", fromlist=["get_db"]).get_db] = (
            override_get_db
        )
        client = TestClient(app, raise_server_exceptions=False)
        yield client
        app.dependency_overrides.clear()

    @pytest.fixture
    def admin_headers(self):
        key = os.environ.get("ADMIN_API_KEY", "").strip()
        if not key:
            pytest.skip("ADMIN_API_KEY not configured")
        return {"X-Admin-API-Key": key, "Origin": "http://testserver"}

    def test_aggregate_get_200(self, client, admin_headers, tenant):
        response = client.get(f"/admin/tenants/{tenant.tenant_id}/settings", headers=admin_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"] == tenant.tenant_id
        assert "effective_readiness" in body

    def test_domain_get_200(self, client, admin_headers, tenant):
        response = client.get(
            f"/admin/tenants/{tenant.tenant_id}/settings/integrations",
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert response.json()["section"] == "integrations"

    def test_patch_200(self, client, admin_headers, tenant):
        response = client.patch(
            f"/admin/tenants/{tenant.tenant_id}/settings/identity",
            headers=admin_headers,
            json={
                "expected_config_version": tenant.config_version,
                "payload": {"timezone": "Europe/Oslo"},
            },
        )
        assert response.status_code == 200

    def test_preview_200(self, client, admin_headers, tenant):
        response = client.post(
            f"/admin/tenants/{tenant.tenant_id}/settings/modules/preview",
            headers=admin_headers,
            json={"payload": {"capabilities": ["customer_inquiries"]}},
        )
        assert response.status_code == 200

    def test_stale_version_409(self, client, admin_headers, tenant):
        response = client.patch(
            f"/admin/tenants/{tenant.tenant_id}/settings/identity",
            headers=admin_headers,
            json={"expected_config_version": 999, "payload": {"timezone": "Europe/Oslo"}},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["config_version"] == tenant.config_version

    def test_missing_expected_config_version_422(self, client, admin_headers, tenant):
        response = client.patch(
            f"/admin/tenants/{tenant.tenant_id}/settings/identity",
            headers=admin_headers,
            json={"payload": {"timezone": "Europe/Oslo"}},
        )
        assert response.status_code == 422

    def test_unknown_domain_404(self, client, admin_headers, tenant):
        response = client.get(
            f"/admin/tenants/{tenant.tenant_id}/settings/not-a-domain",
            headers=admin_headers,
        )
        assert response.status_code == 404

    def test_read_only_patch_403(self, client, admin_headers, tenant):
        with patch.dict(os.environ, {"ADMIN_ROLE": "read_only"}, clear=False):
            from app.core.settings import get_settings

            get_settings.cache_clear()
            try:
                response = client.patch(
                    f"/admin/tenants/{tenant.tenant_id}/settings/identity",
                    headers=admin_headers,
                    json={
                        "expected_config_version": tenant.config_version,
                        "payload": {"timezone": "Europe/Oslo"},
                    },
                )
                assert response.status_code == 403
            finally:
                get_settings.cache_clear()

    def test_operations_routing_patch_200(self, client, admin_headers, tenant):
        with patch.dict(os.environ, {"ADMIN_ROLE": "operations"}, clear=False):
            from app.core.settings import get_settings

            get_settings.cache_clear()
            try:
                response = client.patch(
                    f"/admin/tenants/{tenant.tenant_id}/settings/routing",
                    headers=admin_headers,
                    json={
                        "expected_config_version": tenant.config_version,
                        "payload": {"route_overrides": {"invoice_generic": "finance"}},
                    },
                )
                assert response.status_code == 200
            finally:
                get_settings.cache_clear()

    def test_operations_integrations_patch_403(self, client, admin_headers, tenant):
        with patch.dict(os.environ, {"ADMIN_ROLE": "operations"}, clear=False):
            from app.core.settings import get_settings

            get_settings.cache_clear()
            try:
                response = client.patch(
                    f"/admin/tenants/{tenant.tenant_id}/settings/integrations",
                    headers=admin_headers,
                    json={
                        "expected_config_version": tenant.config_version,
                        "payload": {
                            "selections": {
                                "fortnox": {"selection_status": "not_selected"},
                            }
                        },
                    },
                )
                assert response.status_code == 403
            finally:
                get_settings.cache_clear()

    def test_admin_patch_200(self, client, admin_headers, tenant):
        with patch.dict(os.environ, {"ADMIN_ROLE": "admin"}, clear=False):
            from app.core.settings import get_settings

            get_settings.cache_clear()
            try:
                response = client.patch(
                    f"/admin/tenants/{tenant.tenant_id}/settings/identity",
                    headers=admin_headers,
                    json={
                        "expected_config_version": tenant.config_version,
                        "payload": {"language": "sv"},
                    },
                )
                assert response.status_code == 200
            finally:
                get_settings.cache_clear()

    def test_super_admin_patch_200(self, client, admin_headers, tenant):
        with patch.dict(os.environ, {"ADMIN_ROLE": "super_admin"}, clear=False):
            from app.core.settings import get_settings

            get_settings.cache_clear()
            try:
                response = client.patch(
                    f"/admin/tenants/{tenant.tenant_id}/settings/identity",
                    headers=admin_headers,
                    json={
                        "expected_config_version": tenant.config_version,
                        "payload": {"language": "en"},
                    },
                )
                assert response.status_code == 200
            finally:
                get_settings.cache_clear()

    def test_forbidden_runtime_key_422(self, client, admin_headers, tenant):
        response = client.patch(
            f"/admin/tenants/{tenant.tenant_id}/settings/automation",
            headers=admin_headers,
            json={
                "expected_config_version": tenant.config_version,
                "payload": {"scheduler": {"run_mode": "scheduled"}},
            },
        )
        assert response.status_code == 422

    def test_unknown_tenant_404(self, client, admin_headers):
        response = client.get("/admin/tenants/T_MISSING/settings", headers=admin_headers)
        assert response.status_code == 404

    def test_aggregate_route_not_shadowed_by_domain_route(self, client, admin_headers, tenant):
        aggregate = client.get(
            f"/admin/tenants/{tenant.tenant_id}/settings",
            headers=admin_headers,
        )
        domain = client.get(
            f"/admin/tenants/{tenant.tenant_id}/settings/integrations",
            headers=admin_headers,
        )
        assert aggregate.status_code == 200
        assert domain.status_code == 200
        assert "domains" in aggregate.json()
        assert domain.json()["section"] == "integrations"
