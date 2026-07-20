"""Focused tests for Onboarding 2.0 (DEC-032)."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.admin.onboarding.industry_registry import list_industries, validate_industry_keys
from app.admin.tenant_lifecycle.constants import VALID_LIFECYCLE_STATUSES
from app.admin.tenant_lifecycle.deletion_service import TenantDeletionService
from app.core.admin_session import get_operator_identity, is_super_admin_operator
from app.integrations.oauth_state_resolver import lookup_oauth_state_source
from app.service_profiles.catalog import list_services_for_tenant
from app.workflows.intake_enforcement import evaluate_intake_gate, parse_gmail_internal_date_ms


class TestIndustryRegistry:
    def test_list_industries_has_swedish_labels(self):
        industries = list_industries()
        keys = {item["key"] for item in industries}
        assert "electrical" in keys
        assert "carpentry" in keys
        assert all(item["label"] for item in industries)

    def test_validate_unknown_industry(self):
        assert validate_industry_keys(["electrical", "nope"]) == ["nope"]


class TestServiceCatalog:
    def test_filter_by_capability_and_industry(self):
        services = list_services_for_tenant(
            capability_keys=["lead_management"],
            industry_keys=["electrical"],
        )
        keys = {s["key"] for s in services}
        assert "ev_charger_installation" in keys


class TestIntakeEnforcement:
    def test_before_cutoff_blocks(self):
        cutoff = datetime(2026, 7, 1, tzinfo=timezone.utc)
        msg_ms = int(datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp() * 1000)
        result = evaluate_intake_gate(
            tenant_id="T_TEST",
            lifecycle_status="active",
            intake_settings={"intake_cutoff_at": cutoff.isoformat()},
            message_internal_date_ms=msg_ms,
        )
        assert result["allowed"] is False
        assert result["reason"] == "before_intake_cutoff"

    def test_parse_internal_date_ms(self):
        dt = parse_gmail_internal_date_ms("1609459200000")
        assert dt is not None
        assert dt.tzinfo is not None


class TestLifecycleConstants:
    def test_no_paused_in_lifecycle(self):
        assert "paused" not in VALID_LIFECYCLE_STATUSES


class TestSuperAdminOperatorId:
    def test_super_admin_from_env_ids(self, monkeypatch):
        monkeypatch.setenv("SUPER_ADMIN_OPERATOR_IDS", "operator-admin")
        monkeypatch.setenv("ADMIN_USERNAME", "admin")
        monkeypatch.setenv("ADMIN_ROLE", "admin")
        from app.core.settings import get_settings

        get_settings.cache_clear()
        operator = get_operator_identity("admin")
        assert operator["role"] == "super_admin"
        assert is_super_admin_operator(operator) is True
        get_settings.cache_clear()


class TestOAuthStateResolverInvite:
    def test_invite_source_when_invitation_id_set(self):
        db = MagicMock()
        state = SimpleNamespace(invitation_id="inv-1")
        db.query.return_value.filter.return_value.first.return_value = state
        assert lookup_oauth_state_source(db, "state-123") == "invite"


class TestTenantDeletionService:
    def test_non_test_tenant_not_deletable(self):
        db = MagicMock()
        record = SimpleNamespace(is_test_tenant=False)
        db.query.return_value.filter.return_value.first.return_value = record
        dry = TenantDeletionService.dry_run(db, "T_REAL")
        assert dry.deletable is False
        assert dry.blocked_reason == "not_test_tenant"
