"""Tests for digital coworker reply foundation (Todos A-C)."""

from __future__ import annotations

from app.workflows.missing_fact_plan import build_missing_fact_plan
from app.workflows.reply_quality.audit import SEND_SCENARIO_IDS, audit_legacy_reply_path
from app.workflows.reply_quality.information_value import build_information_value_plan
from app.workflows.reply_quality.operational_next_step import select_operational_next_step
from app.workflows.reply_quality.pipeline import build_and_render_coworker_reply
from app.workflows.reply_quality.service_playbooks import get_reply_playbook
from app.workflows.safe_ack_eligibility import evaluate_safe_ack_eligibility

_SOLAR_INPUT = {
    "subject": "Offertförfrågan solcellsinstallation Uppsala",
    "message_text": "Hej, jag behöver hjälp med solcellsinstallation i Uppsala.",
    "sender": {"email": "customer@example.com"},
}


def _eligibility(input_data=None):
    return evaluate_safe_ack_eligibility(
        detected_job_type="lead",
        risk_detected=False,
        risk_categories=[],
        extraction_issues=[],
        input_data=input_data or _SOLAR_INPUT,
        recommendation=None,
        recommendation_raw="manual_review",
        low_confidence=True,
        used_fallback=False,
    )


class TestCoworkerFeatureFlag:
    def test_disabled_by_default_in_test_env(self, monkeypatch):
        monkeypatch.delenv("DIGITAL_COWORKER_REPLY_ENABLED", raising=False)
        monkeypatch.setenv("ENV", "test")
        from app.workflows.reply_quality.feature_flag import (
            LIVE_EVAL_TENANT,
            is_digital_coworker_reply_enabled,
        )

        assert is_digital_coworker_reply_enabled(tenant_id=LIVE_EVAL_TENANT) is False

    def test_enabled_when_env_flag_set(self, monkeypatch):
        monkeypatch.setenv("DIGITAL_COWORKER_REPLY_ENABLED", "true")
        from app.workflows.reply_quality.feature_flag import (
            LIVE_EVAL_TENANT,
            is_digital_coworker_reply_enabled,
        )

        assert is_digital_coworker_reply_enabled(tenant_id=LIVE_EVAL_TENANT) is True


class TestRenderingAudit:
    def test_audit_covers_send_scenarios(self):
        records = audit_legacy_reply_path()
        audited_ids = {r.scenario_id for r in records}
        assert audited_ids == set(SEND_SCENARIO_IDS)

    def test_legacy_path_is_deterministic_without_llm(self):
        records = audit_legacy_reply_path()
        assert records
        assert all(r.renderer_type == "legacy_safe_ack_v1" for r in records)
        assert all(r.llm_used is False for r in records)


class TestServicePlaybooks:
    def test_solar_and_battery_select_different_families(self):
        solar = get_reply_playbook("solar_installation")
        battery = get_reply_playbook("battery_storage")
        assert solar.service_family != battery.service_family

    def test_support_does_not_use_sales_next_step(self):
        step = select_operational_next_step(
            service_type="solar_service",
            business_intent="support_status",
            thread_state="continuation",
        )
        assert step.step_id in {
            "collect_symptom_facts",
            "provide_status_acknowledgement",
            "confirm_case_receipt_only",
        }

    def test_status_request_next_step(self):
        step = select_operational_next_step(
            service_type="generic_support",
            business_intent="support_status",
        )
        assert step.service_family == "job_status"


class TestInformationValue:
    def test_known_city_not_reasked(self):
        playbook = get_reply_playbook("solar_installation")
        next_step = select_operational_next_step(service_type="solar_installation", business_intent="lead")
        plan = build_information_value_plan(
            playbook=playbook,
            next_step=next_step,
            input_data=_SOLAR_INPUT,
            entities={"city": "Uppsala", "email": "customer@example.com"},
            known_fact_fields=("address",),
        )
        assert "address" in plan.excluded_questions or "address" in plan.already_known_facts

    def test_name_deprioritized(self):
        playbook = get_reply_playbook("solar_installation")
        next_step = select_operational_next_step(service_type="solar_installation", business_intent="lead")
        plan = build_information_value_plan(
            playbook=playbook,
            next_step=next_step,
            input_data=_SOLAR_INPUT,
            entities={"email": "customer@example.com"},
        )
        assert "contact_name" not in plan.selected_questions


class TestCoworkerPipeline:
    def test_distinct_services_produce_distinct_bodies(self):
        solar_missing = build_missing_fact_plan(
            input_data=_SOLAR_INPUT,
            entities={"city": "Uppsala", "email": "customer@example.com"},
            lead_type="solar_installation",
        )
        ev_input = {
            "subject": "Laddbox villa",
            "message_text": "Hej, jag vill installera laddbox i villan i Uppsala.",
            "sender": {"email": "customer@example.com"},
        }
        ev_missing = build_missing_fact_plan(
            input_data=ev_input,
            entities={"city": "Uppsala", "email": "customer@example.com"},
            lead_type="ev_charger",
        )
        eligibility = _eligibility()
        solar = build_and_render_coworker_reply(
            greeting="Hej,",
            signature_name="Niklas",
            missing_fact_plan=solar_missing,
            eligibility=eligibility,
            input_data=_SOLAR_INPUT,
            entities={"city": "Uppsala", "email": "customer@example.com"},
        )
        ev = build_and_render_coworker_reply(
            greeting="Hej,",
            signature_name="Niklas",
            missing_fact_plan=ev_missing,
            eligibility=_eligibility(ev_input),
            input_data=ev_input,
            entities={"city": "Uppsala", "email": "customer@example.com"},
        )
        assert solar and ev
        solar_body, _, _, _ = solar
        ev_body, _, _, _ = ev
        assert solar_body != ev_body
        assert "sol" in solar_body.lower()
        assert "ladd" in ev_body.lower()
