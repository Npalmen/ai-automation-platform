"""Parity tests: not_selected integrations must not appear in tenant-facing views."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.admin.alerts.evaluators import evaluate_integration_health_critical
from app.admin.integrations.selection_resolver import derive_integration_selection
from app.admin.operations_triage import _integration_signals
from app.admin.tenant_directory import _health_integrations_for_tenant
from app.health.integration_health import get_integration_health


def _tenant_record(
    tenant_id: str = "T_NIKLAS_DEMO_001",
    *,
    allowed_integrations: list[str] | None = None,
    settings: dict | None = None,
):
    return SimpleNamespace(
        tenant_id=tenant_id,
        allowed_integrations=allowed_integrations or ["google_mail", "visma"],
        settings=settings or {},
    )


def _app_settings():
    return SimpleNamespace(
        GOOGLE_MAIL_ACCESS_TOKEN="",
        MONDAY_API_KEY="",
        FORTNOX_ACCESS_TOKEN="",
        FORTNOX_CLIENT_SECRET="",
    )


def _mock_db():
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.first.return_value = None
    q.all.return_value = []
    db.query.return_value = q
    return db


class TestFortnoxNotSelectedParity:
  def test_fortnox_not_selected_for_niklas_like_tenant(self):
      record = _tenant_record(allowed_integrations=["google_mail", "visma"])
      db = _mock_db()
      selection = derive_integration_selection(db, record, "fortnox")
      assert selection.selection_status == "not_selected"

  def test_fortnox_not_in_tenant_health_systems_as_warning(self):
      record = _tenant_record(allowed_integrations=["google_mail", "visma"])
      db = _mock_db()
      with patch(
          "app.health.integration_health.TenantConfigRepository.get_settings",
          return_value={},
      ), patch(
          "app.health.integration_health.TenantConfigRepository.get",
          return_value=record,
      ):
          health = get_integration_health(db, record.tenant_id, app_settings=_app_settings())

      fortnox = health["systems"]["fortnox"]
      assert fortnox["status"] == "not_applicable"
      assert not any(sig.get("area") == "fortnox" for sig in health["runbook_signals"])

  def test_fortnox_absent_from_triage(self):
      record = _tenant_record(allowed_integrations=["google_mail", "visma"])
      db = _mock_db()
      with patch(
          "app.health.integration_health.TenantConfigRepository.get_settings",
          return_value={},
      ), patch(
          "app.health.integration_health.TenantConfigRepository.get",
          return_value=record,
      ), patch(
          "app.admin.operations_triage.TenantConfigRepository.get",
          return_value=record,
      ):
          rows = _integration_signals(
              db,
              record.tenant_id,
              "Niklas Demo",
              _app_settings(),
              record=record,
          )

      assert not any("fortnox" in (row.get("title") or "").lower() for row in rows)

  def test_fortnox_hidden_from_customer_detail_health_block(self):
      record = _tenant_record(allowed_integrations=["google_mail", "visma"])
      db = _mock_db()
      systems = {
          "google_mail": {"status": "healthy"},
          "monday": {"status": "not_applicable", "description": "not selected"},
          "fortnox": {"status": "not_applicable", "description": "not selected"},
      }
      block = _health_integrations_for_tenant(record, db, systems)
      assert block["fortnox"] is None
      assert block["monday"] is None
      assert block["google_mail"] is not None

  def test_platform_capability_separate_from_tenant_health(self):
      record = _tenant_record(allowed_integrations=["google_mail", "visma"])
      db = _mock_db()
      with patch(
          "app.health.integration_health.TenantConfigRepository.get_settings",
          return_value={},
      ), patch(
          "app.health.integration_health.TenantConfigRepository.get",
          return_value=record,
      ):
          health = get_integration_health(
              db,
              record.tenant_id,
              app_settings=SimpleNamespace(
                  GOOGLE_MAIL_ACCESS_TOKEN="tok",
                  MONDAY_API_KEY="",
                  FORTNOX_ACCESS_TOKEN="",
                  FORTNOX_CLIENT_SECRET="",
              ),
          )

      assert health["systems"]["fortnox"]["status"] == "not_applicable"
      assert health["platform_capabilities"]["fortnox"]["status"] == "not_configured"

  def test_integration_health_alert_skips_unselected_fortnox(self):
      record = _tenant_record(allowed_integrations=["google_mail", "visma"])
      db = _mock_db()

      class _Definition:
          alert_type = "integration.health_critical"
          scope_type = "tenant"
          default_severity = "critical"
          runbook_ref = "integration_general"

      with patch(
          "app.admin.alerts.evaluators.iter_active_tenants",
          return_value=[(record.tenant_id, "Niklas Demo")],
      ), patch(
          "app.admin.alerts.evaluators.get_integration_health",
          return_value={
              "systems": {
                  "fortnox": {
                      "status": "error",
                      "recommended_action": "should not alert",
                  }
              }
          },
      ), patch(
          "app.admin.alerts.evaluators.TenantConfigRepository.get",
          return_value=record,
      ), patch(
          "app.admin.alerts.evaluators.resolve_alerts_for_unselected_integrations",
          return_value=0,
      ):
          candidates = evaluate_integration_health_critical(db, _Definition(), _app_settings())

      assert candidates == []


class TestCanonicalKeys:
    def test_legacy_gmail_maps_to_google_mail(self):
        from app.integrations.keys import normalize_integration_key

        assert normalize_integration_key("gmail") == "google_mail"
        assert normalize_integration_key("google_mail") == "google_mail"
