"""
Tests for tenant-level email branding:
  - company_display_name / email_signature_name / internal_notification_email
    read from settings.branding blob via _read_automation_settings
  - No email body contains hardcoded "AI Automation"
  - No internal handoff goes to support@company.com when tenant config overrides it
  - T_ELITGRUPPEN branding applied correctly
  - Fallback: no signature when branding not configured
  - Approval gate still works with branding applied
  - provision_tenant_defaults seeds T_ELITGRUPPEN branding (no-clobber)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.processors.action_dispatch_processor import (
    _apply_dispatch_authorization,
    _build_inquiry_default_actions,
    _build_lead_default_actions,
    _read_automation_settings,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lead_job(input_data: dict | None = None, tenant_id: str = "T_TEST") -> Job:
    job = Job(
        tenant_id=tenant_id,
        job_type=JobType.LEAD,
        input_data=input_data or {
            "subject": "Intresserad av era tjänster",
            "message_text": "Hej, vill veta mer.",
            "sender_name": "Anna Svensson",
            "sender_email": "anna@example.com",
        },
    )
    job.processor_history = [
        {"processor": "classification_processor", "result": {"payload": {"detected_job_type": "lead"}}},
    ]
    return job


def _inquiry_job(input_data: dict | None = None, tenant_id: str = "T_TEST") -> Job:
    job = Job(
        tenant_id=tenant_id,
        job_type=JobType.CUSTOMER_INQUIRY,
        input_data=input_data or {
            "subject": "Fråga om er service",
            "message_text": "Hur fungerar det?",
            "sender_name": "Björn Nilsson",
            "sender_email": "bjorn@example.com",
        },
    )
    job.processor_history = [
        {"processor": "classification_processor", "result": {"payload": {"detected_job_type": "customer_inquiry"}}},
    ]
    return job


def _settings_with_branding(
    company_display_name: str = "",
    email_signature_name: str = "",
    internal_notification_email: str = "",
    support_email: str = "",
    auto_actions: dict | None = None,
) -> dict:
    return {
        "followups_enabled": True,
        "leads_enabled": True,
        "support_enabled": True,
        "support_email": support_email,
        "auto_actions": auto_actions or {"lead": True, "customer_inquiry": True},
        "company_display_name": company_display_name,
        "email_signature_name": email_signature_name,
        "internal_notification_email": internal_notification_email,
    }


def _authorized_lead_actions(job: Job, settings: dict) -> list[dict]:
    history = list(job.processor_history or [])
    history.append(
        {
            "processor": "policy_processor",
            "result": {"payload": {"decision": "auto_execute", "detected_job_type": "lead"}},
        }
    )
    job.processor_history = history
    built = _build_lead_default_actions(job, settings)
    return _apply_dispatch_authorization(job, built, settings, db=None, trace=None)


# ---------------------------------------------------------------------------
# No "AI Automation" in generated bodies
# ---------------------------------------------------------------------------

class TestNoHardcodedAIAutomation:
    def test_lead_auto_reply_has_no_ai_automation(self):
        settings = _settings_with_branding()
        actions = _build_lead_default_actions(_lead_job(), settings)
        for a in actions:
            body = a.get("body") or ""
            assert "AI Automation" not in body, f"Found 'AI Automation' in action {a.get('type')}: {body[:200]}"

    def test_lead_handoff_has_no_ai_automation(self):
        settings = _settings_with_branding(internal_notification_email="ops@example.com")
        actions = _build_lead_default_actions(_lead_job(), settings)
        handoff = next((a for a in actions if a.get("type") == "send_internal_handoff"), None)
        assert handoff is not None
        assert "AI Automation" not in handoff["body"]

    def test_inquiry_auto_reply_has_no_ai_automation(self):
        settings = _settings_with_branding()
        actions = _build_inquiry_default_actions(_inquiry_job(), settings)
        for a in actions:
            body = a.get("body") or ""
            assert "AI Automation" not in body, f"Found 'AI Automation' in action {a.get('type')}: {body[:200]}"

    def test_inquiry_handoff_has_no_ai_automation(self):
        settings = _settings_with_branding(internal_notification_email="ops@example.com")
        actions = _build_inquiry_default_actions(_inquiry_job(), settings)
        handoff = next((a for a in actions if a.get("type") == "send_internal_handoff"), None)
        assert handoff is not None
        assert "AI Automation" not in handoff["body"]


# ---------------------------------------------------------------------------
# No hardcoded support@company.com
# ---------------------------------------------------------------------------

class TestNoHardcodedSupportEmail:
    def test_lead_handoff_not_sent_to_company_com_when_no_config(self):
        """When no internal_notification_email configured, handoff should be skipped, not sent to support@company.com."""
        settings = _settings_with_branding(internal_notification_email="")
        actions = _build_lead_default_actions(_lead_job(), settings)
        handoff = next((a for a in actions if a.get("type") == "send_internal_handoff"), None)
        # Should be skipped, not sent anywhere
        if handoff is not None:
            assert handoff.get("_skip"), "Expected handoff to be skipped when no recipient configured"
            assert handoff.get("to", "") != "support@company.com"

    def test_inquiry_handoff_not_sent_to_company_com_when_no_config(self):
        settings = _settings_with_branding(internal_notification_email="")
        actions = _build_inquiry_default_actions(_inquiry_job(), settings)
        handoff = next((a for a in actions if a.get("type") == "send_internal_handoff"), None)
        if handoff is not None:
            assert handoff.get("_skip"), "Expected handoff to be skipped when no recipient configured"
            assert handoff.get("to", "") != "support@company.com"

    def test_lead_handoff_uses_internal_notification_email(self):
        settings = _settings_with_branding(internal_notification_email="internal@mycompany.se")
        actions = _build_lead_default_actions(_lead_job(), settings)
        handoff = next((a for a in actions if a.get("type") == "send_internal_handoff"), None)
        assert handoff is not None
        assert not handoff.get("_skip")
        assert handoff["to"] == "internal@mycompany.se"

    def test_inquiry_handoff_uses_internal_notification_email(self):
        settings = _settings_with_branding(internal_notification_email="internal@mycompany.se")
        actions = _build_inquiry_default_actions(_inquiry_job(), settings)
        handoff = next((a for a in actions if a.get("type") == "send_internal_handoff"), None)
        assert handoff is not None
        assert not handoff.get("_skip")
        assert handoff["to"] == "internal@mycompany.se"

    def test_support_email_fallback_used_when_no_branding_override(self):
        """support_email is the legacy fallback when internal_notification_email not set in branding."""
        # Simulate _read_automation_settings behavior: internal_notification_email falls back to support_email
        settings = {
            **_settings_with_branding(internal_notification_email=""),
            "internal_notification_email": "legacy@support.se",
        }
        actions = _build_lead_default_actions(_lead_job(), settings)
        handoff = next((a for a in actions if a.get("type") == "send_internal_handoff"), None)
        assert handoff is not None
        assert handoff["to"] == "legacy@support.se"


# ---------------------------------------------------------------------------
# Signature name in customer-facing emails
# ---------------------------------------------------------------------------

class TestEmailSignatureName:
    def test_lead_reply_contains_signature_when_set(self):
        settings = _settings_with_branding(email_signature_name="Elit Gruppen")
        actions = _build_lead_default_actions(_lead_job(), settings)
        reply = next((a for a in actions if a.get("type") == "send_customer_auto_reply"), None)
        assert reply is not None
        assert "Vänliga hälsningar\nElit Gruppen" in reply["body"]

    def test_lead_reply_no_signature_block_when_not_configured(self):
        settings = _settings_with_branding(email_signature_name="")
        actions = _build_lead_default_actions(_lead_job(), settings)
        reply = next((a for a in actions if a.get("type") == "send_customer_auto_reply"), None)
        assert reply is not None
        assert "Vänliga hälsningar" not in reply["body"]

    def test_inquiry_reply_contains_signature_when_set(self):
        settings = _settings_with_branding(email_signature_name="Mitt Företag AB")
        actions = _build_inquiry_default_actions(_inquiry_job(), settings)
        reply = next((a for a in actions if a.get("type") == "send_customer_auto_reply"), None)
        assert reply is not None
        assert "Vänliga hälsningar\nMitt Företag AB" in reply["body"]

    def test_inquiry_reply_no_signature_when_not_configured(self):
        settings = _settings_with_branding(email_signature_name="")
        actions = _build_inquiry_default_actions(_inquiry_job(), settings)
        reply = next((a for a in actions if a.get("type") == "send_customer_auto_reply"), None)
        assert reply is not None
        assert "Vänliga hälsningar" not in reply["body"]


# ---------------------------------------------------------------------------
# T_ELITGRUPPEN branding
# ---------------------------------------------------------------------------

class TestElitgruppenBranding:
    def _elit_settings(self) -> dict:
        return _settings_with_branding(
            company_display_name="Elit Gruppen",
            email_signature_name="Elit Gruppen",
            internal_notification_email="info@elitgruppen.se",
            auto_actions={"lead": True, "customer_inquiry": True},
        )

    def test_lead_reply_signed_elit_gruppen(self):
        actions = _build_lead_default_actions(
            _lead_job(tenant_id="T_ELITGRUPPEN"), self._elit_settings()
        )
        reply = next(a for a in actions if a.get("type") == "send_customer_auto_reply")
        assert "Vänliga hälsningar\nElit Gruppen" in reply["body"]

    def test_lead_handoff_to_info_elitgruppen(self):
        actions = _build_lead_default_actions(
            _lead_job(tenant_id="T_ELITGRUPPEN"), self._elit_settings()
        )
        handoff = next(a for a in actions if a.get("type") == "send_internal_handoff")
        assert handoff["to"] == "info@elitgruppen.se"

    def test_inquiry_reply_signed_elit_gruppen(self):
        actions = _build_inquiry_default_actions(
            _inquiry_job(tenant_id="T_ELITGRUPPEN"), self._elit_settings()
        )
        reply = next(a for a in actions if a.get("type") == "send_customer_auto_reply")
        assert "Vänliga hälsningar\nElit Gruppen" in reply["body"]

    def test_inquiry_handoff_to_info_elitgruppen(self):
        actions = _build_inquiry_default_actions(
            _inquiry_job(tenant_id="T_ELITGRUPPEN"), self._elit_settings()
        )
        handoff = next(a for a in actions if a.get("type") == "send_internal_handoff")
        assert handoff["to"] == "info@elitgruppen.se"

    def test_no_ai_automation_in_any_elit_action(self):
        for builder, job_fn in [
            (_build_lead_default_actions, _lead_job),
            (_build_inquiry_default_actions, _inquiry_job),
        ]:
            actions = builder(job_fn(tenant_id="T_ELITGRUPPEN"), self._elit_settings())
            for a in actions:
                body = a.get("body") or ""
                assert "AI Automation" not in body


# ---------------------------------------------------------------------------
# _read_automation_settings reads branding from settings blob
# ---------------------------------------------------------------------------

class TestReadAutomationSettingsBranding:
    def _mock_db_for(
        self,
        settings_blob: dict,
        auto_actions: dict | None = None,
        tenant_name: str = "Test Tenant",
    ):
        from app.repositories.postgres.tenant_config_models import TenantConfigRecord
        record = MagicMock(spec=TenantConfigRecord)
        record.auto_actions = auto_actions or {}
        record.name = tenant_name
        db = MagicMock()

        with (
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value=settings_blob,
            ),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=record,
            ),
        ):
            job = _lead_job()
            return _read_automation_settings(job, db)

    def test_reads_company_display_name_from_branding(self):
        result = self._mock_db_for(
            {"branding": {"company_display_name": "Elit Gruppen"}}
        )
        assert result["company_display_name"] == "Elit Gruppen"

    def test_reads_email_signature_name_from_branding(self):
        result = self._mock_db_for(
            {"branding": {"email_signature_name": "Elit Gruppen AB"}}
        )
        assert result["email_signature_name"] == "Elit Gruppen AB"

    def test_reads_internal_notification_email_from_branding(self):
        result = self._mock_db_for(
            {"branding": {"internal_notification_email": "info@elitgruppen.se"}}
        )
        assert result["internal_notification_email"] == "info@elitgruppen.se"

    def test_email_signature_name_falls_back_to_company_display_name(self):
        result = self._mock_db_for(
            {"branding": {"company_display_name": "Elit Gruppen"}}
        )
        assert result["email_signature_name"] == "Elit Gruppen"

    def test_company_display_name_falls_back_to_tenant_name(self):
        result = self._mock_db_for({}, tenant_name="Min Firma AB")
        assert result["company_display_name"] == "Min Firma AB"

    def test_internal_email_falls_back_to_support_email(self):
        result = self._mock_db_for({"support_email": "support@legacy.se"})
        assert result["internal_notification_email"] == "support@legacy.se"

    def test_all_branding_empty_when_no_config(self):
        result = self._mock_db_for({}, tenant_name="")
        assert result["company_display_name"] == ""
        assert result["email_signature_name"] == ""
        assert result["internal_notification_email"] == ""

    def test_db_none_returns_empty_dict(self):
        job = _lead_job()
        result = _read_automation_settings(job, None)
        assert result == {}


# ---------------------------------------------------------------------------
# Approval gate still works with branding
# ---------------------------------------------------------------------------

class TestApprovalGateWithBranding:
    def test_lead_email_approval_gated_with_signature_name_in_payload(self):
        settings = _settings_with_branding(
            email_signature_name="Elit Gruppen",
            internal_notification_email="info@elitgruppen.se",
            auto_actions={"lead": False},
        )
        actions = _authorized_lead_actions(_lead_job(tenant_id="T_ELITGRUPPEN"), settings)
        for a in actions:
            if a.get("type") in ("send_customer_auto_reply", "send_internal_handoff"):
                assert a.get("_needs_approval"), f"Expected _needs_approval on {a.get('type')}"
                body = a.get("body") or ""
                assert "Elit Gruppen" in body or a.get("type") == "send_internal_handoff"

    def test_monday_gated_at_dispatch_boundary_with_branding(self):
        """Branding does not bypass dispatch authorization for external writes."""
        settings = _settings_with_branding(
            email_signature_name="Elit Gruppen",
            auto_actions={"lead": False},
        )
        actions = _authorized_lead_actions(_lead_job(tenant_id="T_ELITGRUPPEN"), settings)
        monday = next((a for a in actions if a.get("type") == "create_monday_item"), None)
        assert monday is not None
        assert monday.get("_needs_approval")
        assert not monday.get("_skip")


# ---------------------------------------------------------------------------
# provision_tenant_defaults
# ---------------------------------------------------------------------------

class TestProvisionTenantDefaults:
    def _make_engine_with_row(self, existing_settings: dict | None):
        engine = MagicMock()
        conn = MagicMock()
        engine.begin.return_value.__enter__ = MagicMock(return_value=conn)
        engine.begin.return_value.__exit__ = MagicMock(return_value=False)
        row = (json.dumps(existing_settings),) if existing_settings is not None else None
        conn.execute.return_value.fetchone.return_value = row
        return engine, conn

    def _get_update_call_settings(self, conn) -> dict | None:
        """Return parsed settings dict from the UPDATE call, or None if no UPDATE was made."""
        # Each call: (text_obj, params_dict) as positional args
        for c in conn.execute.call_args_list:
            args = c.args
            if len(args) >= 2 and isinstance(args[1], dict) and "s" in args[1]:
                return json.loads(args[1]["s"])
        return None

    def test_seeds_branding_when_tenant_exists_and_no_branding(self):
        from app.repositories.postgres.schema_migrations import provision_tenant_defaults
        engine, conn = self._make_engine_with_row({})
        provision_tenant_defaults(engine)
        updated = self._get_update_call_settings(conn)
        assert updated is not None, "Expected an UPDATE to be executed"
        assert updated["branding"]["company_display_name"] == "Elit Gruppen"
        assert updated["branding"]["internal_notification_email"] == "info@elitgruppen.se"

    def test_no_clobber_when_branding_already_set(self):
        from app.repositories.postgres.schema_migrations import provision_tenant_defaults
        existing = {"branding": {
            "company_display_name": "Custom Name",
            "email_signature_name": "Custom Name",
            "internal_notification_email": "custom@example.com",
        }}
        engine, conn = self._make_engine_with_row(existing)
        provision_tenant_defaults(engine)
        updated = self._get_update_call_settings(conn)
        assert updated is None, "Expected no UPDATE when all branding keys already present"

    def test_partial_branding_fills_in_missing_keys(self):
        from app.repositories.postgres.schema_migrations import provision_tenant_defaults
        existing = {"branding": {"company_display_name": "My Name"}}
        engine, conn = self._make_engine_with_row(existing)
        provision_tenant_defaults(engine)
        updated = self._get_update_call_settings(conn)
        assert updated is not None, "Expected UPDATE for partial branding"
        assert updated["branding"]["company_display_name"] == "My Name"
        assert updated["branding"]["internal_notification_email"] == "info@elitgruppen.se"

    def test_skips_when_tenant_not_in_db(self):
        from app.repositories.postgres.schema_migrations import provision_tenant_defaults
        engine, conn = self._make_engine_with_row(None)
        provision_tenant_defaults(engine)
        updated = self._get_update_call_settings(conn)
        assert updated is None, "Expected no UPDATE when tenant not in DB"

    def test_non_fatal_on_db_error(self):
        from app.repositories.postgres.schema_migrations import provision_tenant_defaults
        engine = MagicMock()
        engine.begin.side_effect = Exception("DB down")
        provision_tenant_defaults(engine)  # must not raise
