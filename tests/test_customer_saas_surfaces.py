from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_customer_account_merges_config_and_settings_defaults():
    from app.main import get_customer_account

    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value={"support_email": "support@acme.se"},
        ),
        patch("app.main.get_tenant_config", return_value={"name": "Acme AB"}),
    ):
        result = get_customer_account(db=MagicMock(), tenant_id="TENANT_1")

    assert result["tenant_id"] == "TENANT_1"
    assert result["company_name"] == "Acme AB"
    assert result["support_email"] == "support@acme.se"
    assert result["team_members"] == []


def test_put_customer_account_persists_account_without_clobbering_settings():
    from app.main import CustomerAccountRequest, put_customer_account

    request = CustomerAccountRequest(
        company_name="Acme AB",
        support_email="support@acme.se",
        team_members=[
            {"name": "Anna", "email": "anna@acme.se", "role": "owner", "status": "active"},
            {"name": "", "email": "", "role": "member"},
        ],
    )

    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value={"notifications": {"enabled": True}},
        ),
        patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings") as save,
        patch("app.main.get_tenant_config", return_value={"name": "Old Name"}),
    ):
        result = put_customer_account(request=request, db=MagicMock(), tenant_id="TENANT_1")

    saved_settings = save.call_args.args[2]
    assert saved_settings["notifications"] == {"enabled": True}
    assert saved_settings["support_email"] == "support@acme.se"
    assert saved_settings["account"]["team_members"] == [
        {"name": "Anna", "email": "anna@acme.se", "role": "owner", "status": "active"}
    ]
    assert result["company_name"] == "Acme AB"


def test_customer_activity_hides_internal_job_ids_and_payloads():
    from app.main import customer_activity

    with patch(
        "app.main.dashboard_activity",
        return_value={
            "total": 1,
            "items": [{
                "job_id": "job-secret",
                "created_at": "2026-01-01T10:00:00+00:00",
                "type": "lead",
                "status": "awaiting_approval",
                "latest_action": None,
                "payload": {"secret": True},
            }],
        },
    ):
        result = customer_activity(db=MagicMock(), tenant_id="TENANT_1")

    assert result["total"] == 1
    assert result["items"][0]["label"] == "Väntar på godkännande"
    assert "job_id" not in result["items"][0]
    assert "payload" not in result["items"][0]


def test_customer_results_returns_roi_and_automation_rate():
    from app.main import customer_results

    with (
        patch(
            "app.main._compute_summary",
            return_value={
                "leads_today": 2,
                "inquiries_today": 1,
                "invoices_today": 1,
                "completed_today": 3,
                "waiting_customer": 1,
            },
        ),
        patch(
            "app.main._compute_roi",
            return_value={"estimated_hours_saved": 1.5, "estimated_value_sek": 750},
        ),
    ):
        result = customer_results(db=MagicMock(), tenant_id="TENANT_1")

    assert result["cases_handled"] == 4
    assert result["automation_rate_percent"] == 75
    assert result["estimated_value_sek"] == 750


def test_customer_health_simplifies_integration_statuses():
    from app.main import customer_health

    with patch(
        "app.health.integration_health.get_integration_health",
        return_value={
            "overall_status": "warning",
            "systems": {
                "gmail": {"status": "healthy", "checks": [{"message": "TOKEN ok"}]},
                "monday": {"status": "not_configured", "checks": [{"message": "MONDAY_API_KEY saknas"}]},
            },
        },
    ):
        result = customer_health(db=MagicMock(), tenant_id="TENANT_1")

    assert result["message"] == "Kontroll rekommenderas"
    assert result["systems"]["gmail"] == {"status": "healthy", "label": "Allt fungerar"}
    assert result["systems"]["monday"] == {"status": "not_configured", "label": "Integration saknas"}
