from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_tenant_context_current_includes_demo_mode_and_onboarding():
    from app.main import tenant_context_current

    db = MagicMock()
    with (
        patch("app.main.get_tenant_config", return_value={"name": "Pilot AB", "enabled_job_types": ["lead"]}),
        patch("app.main._build_control_response", return_value={"automation": {"demo_mode": True}}),
        patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={}),
        patch(
            "app.main.onboarding_status",
            return_value={"status": "in_progress", "score": {"percent": 50, "completed": 4, "total": 8}},
        ),
    ):
        result = tenant_context_current(db=db, tenant_id="TENANT_1")

    assert result["tenant_id"] == "TENANT_1"
    assert result["name"] == "Pilot AB"
    assert result["enabled_job_types"] == ["lead"]
    assert result["demo_mode"] is True
    assert result["onboarding"]["status"] == "in_progress"
    assert result["onboarding"]["percent"] == 50


def test_admin_tenant_context_uses_requested_tenant():
    from app.main import admin_tenant_context

    db = MagicMock()
    with (
        patch("app.main.get_tenant_config", return_value={"name": "X", "enabled_job_types": []}),
        patch("app.main._build_control_response", return_value={"automation": {"demo_mode": False}}),
        patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={}),
        patch(
            "app.main.onboarding_status",
            return_value={"status": "ready", "score": {"percent": 100, "completed": 8, "total": 8}},
        ),
    ):
        result = admin_tenant_context(tenant_id="TENANT_ADMIN", db=db, _=None)

    assert result["tenant_id"] == "TENANT_ADMIN"
    assert result["demo_mode"] is False
    assert result["onboarding"]["status"] == "ready"
