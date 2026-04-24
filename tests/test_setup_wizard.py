"""Tests for GET /setup/status, PUT /setup/modules, POST /setup/verify.

Uses direct function calls with mocked DB + patched settings — repo pattern.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


# ── helpers ───────────────────────────────────────────────────────────────────

_EMPTY_SETTINGS = {
    "GOOGLE_MAIL_ACCESS_TOKEN": "",
    "MICROSOFT_MAIL_ACCESS_TOKEN": "",
    "MONDAY_API_KEY": "",
    "FORTNOX_ACCESS_TOKEN": "",
    "VISMA_ACCESS_TOKEN": "",
}

_FULL_SETTINGS = {
    "GOOGLE_MAIL_ACCESS_TOKEN": "tok_google",
    "MICROSOFT_MAIL_ACCESS_TOKEN": "",
    "MONDAY_API_KEY": "tok_monday",
    "FORTNOX_ACCESS_TOKEN": "",
    "VISMA_ACCESS_TOKEN": "",
}


def _mock_settings(**overrides):
    s = MagicMock()
    merged = {**_EMPTY_SETTINGS, **overrides}
    for k, v in merged.items():
        setattr(s, k, v)
    return s


def _make_db_record(enabled_job_types=None):
    r = MagicMock()
    r.enabled_job_types = enabled_job_types
    return r


def _get_status(
    tenant_id: str = "T1",
    enabled_job_types: list | None = None,
    ctrl_settings: dict | None = None,
    db_record=None,
    **setting_overrides,
):
    from app.main import get_setup_status

    db = MagicMock()
    mock_q = MagicMock()
    db.query.return_value = mock_q
    mock_q.filter.return_value = mock_q
    mock_q.first.return_value = db_record

    cfg = {"enabled_job_types": enabled_job_types or [], "allowed_integrations": []}

    with (
        patch("app.main.get_tenant_config", return_value=cfg),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=ctrl_settings or {},
        ),
        patch("app.main.get_settings", return_value=_mock_settings(**setting_overrides)),
    ):
        return get_setup_status(db=db, tenant_id=tenant_id)


def _put_modules(body: dict, tenant_id: str = "T1", existing_types: list | None = None):
    from app.main import put_setup_modules, SetupModulesRequest

    db = MagicMock()
    existing_record = _make_db_record(enabled_job_types=existing_types)

    request = SetupModulesRequest(**body)
    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=existing_record,
        ),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert",
        ) as mock_upsert,
    ):
        result = put_setup_modules(request=request, db=db, tenant_id=tenant_id)
        return result, mock_upsert


def _post_verify(
    tenant_id: str = "T1",
    enabled_job_types: list | None = None,
    ctrl_settings: dict | None = None,
    db_record=None,
    **setting_overrides,
):
    from app.main import post_setup_verify

    db = MagicMock()
    mock_q = MagicMock()
    db.query.return_value = mock_q
    mock_q.filter.return_value = mock_q
    mock_q.first.return_value = db_record

    cfg = {"enabled_job_types": enabled_job_types or [], "allowed_integrations": []}

    with (
        patch("app.main.get_tenant_config", return_value=cfg),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=db_record,
        ),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=ctrl_settings or {},
        ),
        patch("app.main.get_settings", return_value=_mock_settings(**setting_overrides)),
    ):
        return post_setup_verify(db=db, tenant_id=tenant_id)


# ══════════════════════════════════════════════════════════════════════════════
# GET /setup/status — shape
# ══════════════════════════════════════════════════════════════════════════════

class TestSetupStatusShape:
    def test_returns_all_required_keys(self):
        r = _get_status()
        for key in ("tenant_id", "modules", "connections", "automation", "readiness", "missing"):
            assert key in r, f"Missing key: {key}"

    def test_modules_has_sales_support_finance(self):
        m = _get_status()["modules"]
        assert "sales" in m
        assert "support" in m
        assert "finance" in m

    def test_connections_has_all_keys(self):
        c = _get_status()["connections"]
        for key in ("email_connected", "google_mail", "microsoft_mail",
                    "fortnox", "visma", "monday"):
            assert key in c, f"Missing connection key: {key}"

    def test_automation_has_scheduler_and_followups(self):
        a = _get_status()["automation"]
        assert "scheduler_mode" in a
        assert "followups_enabled" in a

    def test_readiness_has_score_and_status(self):
        rd = _get_status()["readiness"]
        assert "score" in rd
        assert "status" in rd

    def test_missing_is_list(self):
        assert isinstance(_get_status()["missing"], list)

    def test_tenant_id_in_response(self):
        r = _get_status(tenant_id="MY_TENANT")
        assert r["tenant_id"] == "MY_TENANT"


# ══════════════════════════════════════════════════════════════════════════════
# GET /setup/status — module derivation
# ══════════════════════════════════════════════════════════════════════════════

class TestSetupStatusModules:
    def test_no_types_all_modules_false(self):
        m = _get_status(enabled_job_types=[])["modules"]
        assert m["sales"] is False
        assert m["support"] is False
        assert m["finance"] is False

    def test_lead_enables_sales(self):
        m = _get_status(enabled_job_types=["lead"])["modules"]
        assert m["sales"] is True
        assert m["support"] is False
        assert m["finance"] is False

    def test_customer_inquiry_enables_support(self):
        m = _get_status(enabled_job_types=["customer_inquiry"])["modules"]
        assert m["support"] is True
        assert m["sales"] is False

    def test_invoice_enables_finance(self):
        m = _get_status(enabled_job_types=["invoice"])["modules"]
        assert m["finance"] is True

    def test_all_types_all_modules(self):
        m = _get_status(enabled_job_types=["lead", "customer_inquiry", "invoice"])["modules"]
        assert m["sales"] is True
        assert m["support"] is True
        assert m["finance"] is True


# ══════════════════════════════════════════════════════════════════════════════
# GET /setup/status — connection detection
# ══════════════════════════════════════════════════════════════════════════════

class TestSetupStatusConnections:
    def test_no_credentials_all_false(self):
        c = _get_status()["connections"]
        assert c["email_connected"] is False
        assert c["google_mail"] is False
        assert c["microsoft_mail"] is False
        assert c["monday"] is False

    def test_google_mail_token_sets_connected(self):
        c = _get_status(GOOGLE_MAIL_ACCESS_TOKEN="tok")["connections"]
        assert c["google_mail"] is True
        assert c["email_connected"] is True

    def test_microsoft_mail_token_sets_connected(self):
        c = _get_status(MICROSOFT_MAIL_ACCESS_TOKEN="tok")["connections"]
        assert c["microsoft_mail"] is True
        assert c["email_connected"] is True

    def test_monday_key_sets_monday(self):
        c = _get_status(MONDAY_API_KEY="key")["connections"]
        assert c["monday"] is True

    def test_fortnox_token_sets_fortnox(self):
        c = _get_status(FORTNOX_ACCESS_TOKEN="tok")["connections"]
        assert c["fortnox"] is True

    def test_visma_token_sets_visma(self):
        c = _get_status(VISMA_ACCESS_TOKEN="tok")["connections"]
        assert c["visma"] is True


# ══════════════════════════════════════════════════════════════════════════════
# GET /setup/status — readiness scoring
# ══════════════════════════════════════════════════════════════════════════════

class TestSetupStatusReadiness:
    def test_score_low_for_empty_tenant(self):
        # Default: scheduler=manual (+20), no email, no module, no support_email, no dest → 20
        rd = _get_status()["readiness"]
        assert rd["score"] == 20

    def test_score_clamped_to_100_maximum(self):
        rd = _get_status(
            enabled_job_types=["lead"],
            ctrl_settings={"scheduler": {"run_mode": "scheduled"},
                           "automation": {"followups_enabled": True},
                           "support_email": "ops@x.com"},
            GOOGLE_MAIL_ACCESS_TOKEN="tok",
            MONDAY_API_KEY="key",
        )["readiness"]
        assert rd["score"] <= 100

    def test_score_non_negative(self):
        assert _get_status()["readiness"]["score"] >= 0

    def test_email_adds_30(self):
        # baseline (manual scheduler) = 20; add email → 50
        without = _get_status()["readiness"]["score"]
        with_email = _get_status(GOOGLE_MAIL_ACCESS_TOKEN="tok")["readiness"]["score"]
        assert with_email - without == 30

    def test_module_adds_20(self):
        without = _get_status()["readiness"]["score"]
        with_module = _get_status(enabled_job_types=["lead"])["readiness"]["score"]
        assert with_module - without == 20

    def test_destination_integration_adds_20(self):
        without = _get_status()["readiness"]["score"]
        with_dest = _get_status(MONDAY_API_KEY="key")["readiness"]["score"]
        assert with_dest - without == 20

    def test_support_email_adds_10(self):
        without = _get_status()["readiness"]["score"]
        with_email = _get_status(ctrl_settings={"support_email": "ops@x.com"})["readiness"]["score"]
        assert with_email - without == 10

    def test_paused_scheduler_costs_20(self):
        # default scheduler=manual → score=20; paused → score=0 (loses the +20)
        no_pause = _get_status()["readiness"]["score"]
        paused = _get_status(ctrl_settings={"scheduler": {"run_mode": "paused"}})["readiness"]["score"]
        assert no_pause - paused == 20

    def test_status_needs_setup_when_score_low(self):
        assert _get_status()["readiness"]["status"] == "needs_setup"

    def test_status_ready_when_score_high(self):
        rd = _get_status(
            enabled_job_types=["lead"],
            ctrl_settings={"scheduler": {"run_mode": "scheduled"},
                           "support_email": "ops@x.com"},
            GOOGLE_MAIL_ACCESS_TOKEN="tok",
            MONDAY_API_KEY="key",
        )["readiness"]
        assert rd["score"] == 100
        assert rd["status"] == "ready"

    def test_missing_populated_for_no_email(self):
        missing = _get_status()["missing"]
        assert any("email" in m.lower() for m in missing)

    def test_missing_empty_when_fully_configured(self):
        rd = _get_status(
            enabled_job_types=["lead"],
            ctrl_settings={"scheduler": {"run_mode": "manual"},
                           "support_email": "ops@x.com"},
            GOOGLE_MAIL_ACCESS_TOKEN="tok",
            MONDAY_API_KEY="key",
        )
        assert rd["missing"] == []


# ══════════════════════════════════════════════════════════════════════════════
# PUT /setup/modules
# ══════════════════════════════════════════════════════════════════════════════

class TestPutSetupModules:
    def test_returns_modules_and_enabled_types(self):
        result, _ = _put_modules({"sales": True, "support": False, "finance": False})
        assert "modules" in result
        assert "enabled_job_types" in result

    def test_sales_true_includes_lead(self):
        result, _ = _put_modules({"sales": True, "support": False, "finance": False})
        assert "lead" in result["enabled_job_types"]

    def test_support_true_includes_customer_inquiry(self):
        result, _ = _put_modules({"sales": False, "support": True, "finance": False})
        assert "customer_inquiry" in result["enabled_job_types"]

    def test_finance_true_includes_invoice(self):
        result, _ = _put_modules({"sales": False, "support": False, "finance": True})
        assert "invoice" in result["enabled_job_types"]

    def test_all_false_clears_known_types(self):
        result, _ = _put_modules({"sales": False, "support": False, "finance": False},
                                  existing_types=["lead", "customer_inquiry", "invoice"])
        for t in ("lead", "customer_inquiry", "invoice"):
            assert t not in result["enabled_job_types"]

    def test_upsert_called_with_tenant_id(self):
        _, mock_upsert = _put_modules({"sales": True, "support": True, "finance": False},
                                       tenant_id="MY_T")
        assert mock_upsert.call_args[1].get("tenant_id") == "MY_T" or \
               mock_upsert.call_args[0][1] == "MY_T"

    def test_response_modules_reflect_request(self):
        result, _ = _put_modules({"sales": True, "support": False, "finance": True})
        assert result["modules"]["sales"] is True
        assert result["modules"]["support"] is False
        assert result["modules"]["finance"] is True


# ══════════════════════════════════════════════════════════════════════════════
# POST /setup/verify — shape
# ══════════════════════════════════════════════════════════════════════════════

class TestPostSetupVerify:
    def test_returns_status_checks_message(self):
        r = _post_verify()
        assert "status" in r
        assert "checks" in r
        assert "message" in r

    def test_checks_is_list(self):
        assert isinstance(_post_verify()["checks"], list)

    def test_each_check_has_name_and_status(self):
        for check in _post_verify()["checks"]:
            assert "name" in check
            assert "status" in check

    def test_status_is_valid_value(self):
        assert _post_verify()["status"] in ("ok", "warning", "failed")

    def test_failed_when_no_modules(self):
        r = _post_verify(enabled_job_types=[], db_record=MagicMock())
        assert r["status"] == "failed"

    def test_warning_when_no_email(self):
        r = _post_verify(enabled_job_types=["lead"], db_record=MagicMock())
        assert r["status"] in ("warning", "failed")

    def test_ok_when_fully_configured(self):
        db_record = MagicMock()
        r = _post_verify(
            enabled_job_types=["lead"],
            ctrl_settings={"scheduler": {"run_mode": "manual"}},
            db_record=db_record,
            GOOGLE_MAIL_ACCESS_TOKEN="tok",
            MONDAY_API_KEY="key",
        )
        assert r["status"] == "ok"

    def test_message_is_string(self):
        assert isinstance(_post_verify()["message"], str)
