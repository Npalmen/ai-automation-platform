"""
Regression tests for nested tenant settings persistence.

SQLAlchemy JSON columns do not detect in-place nested mutations. update_settings
must deep-copy and flag the column as modified.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.repositories.postgres.tenant_config_repository import TenantConfigRepository


def _record_with_settings(settings: dict) -> MagicMock:
    record = MagicMock()
    record.tenant_id = "T_NIKLAS_DEMO"
    record.settings = settings
    record.created_at = None
    return record


class TestTenantSettingsPersistence:
    def test_nested_automation_followups_enabled_persists(self):
        db = MagicMock()
        nested_automation = {"followups_enabled": False, "leads_enabled": True}
        record = _record_with_settings(
            {
                "automation": nested_automation,
                "scheduler": {"run_mode": "manual"},
                "memory": {"enabled": True},
            }
        )
        db.query.return_value.filter.return_value.first.return_value = record

        TenantConfigRepository.update_settings(
            db,
            "T_NIKLAS_DEMO",
            {"automation": {"followups_enabled": True}},
        )

        assert record.settings["automation"]["followups_enabled"] is True
        assert record.settings["automation"]["leads_enabled"] is True
        assert record.settings["memory"]["enabled"] is True
        # Must not mutate the original nested dict reference in-place only.
        assert record.settings["automation"] is not nested_automation
        db.commit.assert_called_once()

    def test_nested_scheduler_run_mode_persists(self):
        db = MagicMock()
        nested_scheduler = {"run_mode": "manual"}
        record = _record_with_settings(
            {
                "automation": {"followups_enabled": True},
                "scheduler": nested_scheduler,
            }
        )
        db.query.return_value.filter.return_value.first.return_value = record

        TenantConfigRepository.update_settings(
            db,
            "T_NIKLAS_DEMO",
            {"scheduler": {"run_mode": "scheduled"}},
        )

        assert record.settings["scheduler"]["run_mode"] == "scheduled"
        assert record.settings["automation"]["followups_enabled"] is True
        assert record.settings["scheduler"] is not nested_scheduler
        db.commit.assert_called_once()

    def test_merge_false_replaces_entire_settings_blob(self):
        db = MagicMock()
        record = _record_with_settings({"automation": {"followups_enabled": False}})
        db.query.return_value.filter.return_value.first.return_value = record

        TenantConfigRepository.update_settings(
            db,
            "T_NIKLAS_DEMO",
            {"scheduler": {"run_mode": "paused"}},
            merge=False,
        )

        assert record.settings == {"scheduler": {"run_mode": "paused"}}
        assert "automation" not in record.settings
