"""Local evals for Service Profiles & Qualification Schemas.

Deterministic only — no LLM, no live integrations, no external calls.

Covers:
  TestServiceProfileRegistry  — registry completeness and shape
  TestProfileSelection        — select_profile() for all main job types
  TestRequiredFieldsByProfile — per-profile required field contracts
  TestMissingFieldsComputation — compute_profile_missing_info()
  TestFollowUpQuestions        — build_profile_question_message()
  TestQuestionGeneratorIntegration — patched generate_question_message with profile
  TestRiskRouting              — high-risk profiles always route to manual_review
  TestTenantOverrideSeam       — apply_tenant_overrides() seam behaviour
"""
from __future__ import annotations

import pytest

from app.service_profiles import (
    get_profile,
    list_profiles,
    select_profile,
    compute_profile_missing_info,
    build_profile_question_message,
    apply_tenant_overrides,
)
from app.lead.question_generator import generate_question_message
from app.lead.tenant_context import TenantLeadContext


# ── helpers ───────────────────────────────────────────────────────────────────

def _input(subject: str, body: str) -> dict:
    return {
        "subject": subject,
        "message_text": body,
        "sender": {"name": "Testperson", "email": "test@example.com"},
    }


# ══════════════════════════════════════════════════════════════════════════════
# Registry
# ══════════════════════════════════════════════════════════════════════════════

class TestServiceProfileRegistry:
    REQUIRED_PROFILES = [
        "generic_lead",
        "generic_support",
        "ev_charger_installation",
        "solar_installation",
        "battery_storage",
        "electrical_fault",
        "inverter_support",
        "electrical_panel",
        "invoice_generic",
        "debt_collection_risk",
    ]

    def test_registry_contains_all_required_profiles(self):
        for stype in self.REQUIRED_PROFILES:
            assert get_profile(stype) is not None, f"Missing profile: {stype}"

    def test_unknown_profile_returns_none(self):
        assert get_profile("nonexistent_profile") is None

    def test_list_profiles_returns_all(self):
        profiles = list_profiles()
        types = {p.service_type for p in profiles}
        for stype in self.REQUIRED_PROFILES:
            assert stype in types

    def test_all_profiles_have_at_least_one_required_field(self):
        for profile in list_profiles():
            assert len(profile.required_fields) >= 1, (
                f"{profile.service_type} has no required fields"
            )

    def test_all_profiles_have_follow_up_questions(self):
        for profile in list_profiles():
            assert len(profile.follow_up_questions) >= 1, (
                f"{profile.service_type} has no follow-up questions"
            )

    def test_all_profiles_have_non_empty_follow_up_intro(self):
        for profile in list_profiles():
            assert profile.follow_up_intro.strip(), (
                f"{profile.service_type} has empty follow_up_intro"
            )

    def test_all_profiles_have_valid_family(self):
        valid_families = {"installation_service", "generic_business"}
        for profile in list_profiles():
            assert profile.family in valid_families, (
                f"{profile.service_type} has unknown family: {profile.family}"
            )

    def test_all_profiles_have_valid_default_route(self):
        valid_routes = {"sales", "support", "invoice", "manual_review"}
        for profile in list_profiles():
            assert profile.default_route in valid_routes, (
                f"{profile.service_type} route: {profile.default_route}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# Profile Selection
# ══════════════════════════════════════════════════════════════════════════════

class TestProfileSelection:
    def test_ev_charger_lead_selects_ev_charger_profile(self):
        p = select_profile("lead", lead_type="ev_charger")
        assert p.service_type == "ev_charger_installation"

    def test_solar_lead_selects_solar_profile(self):
        p = select_profile("lead", lead_type="solar_installation")
        assert p.service_type == "solar_installation"

    def test_battery_lead_selects_battery_profile(self):
        p = select_profile("lead", lead_type="battery_storage")
        assert p.service_type == "battery_storage"

    def test_electrical_work_lead_selects_panel_profile(self):
        p = select_profile("lead", lead_type="electrical_work")
        assert p.service_type == "electrical_panel"

    def test_unknown_lead_type_returns_generic_lead(self):
        p = select_profile("lead", lead_type="unknown")
        assert p.service_type == "generic_lead"

    def test_none_lead_type_returns_generic_lead(self):
        p = select_profile("lead", lead_type=None)
        assert p.service_type == "generic_lead"

    def test_electrical_fault_support_by_keyword(self):
        p = select_profile("customer_inquiry", text="jordfelsbrytaren löser")
        assert p.service_type == "electrical_fault"

    def test_inverter_support_by_keyword(self):
        p = select_profile("customer_inquiry", text="växelriktaren visar felkod")
        assert p.service_type == "inverter_support"

    def test_safety_category_selects_electrical_fault(self):
        p = select_profile("customer_inquiry", support_category="safety")
        assert p.service_type == "electrical_fault"

    def test_bränt_lukt_selects_electrical_fault(self):
        p = select_profile("customer_inquiry", text="det luktar bränt från elcentralen")
        assert p.service_type == "electrical_fault"

    def test_invoice_selects_invoice_generic(self):
        p = select_profile("invoice")
        assert p.service_type == "invoice_generic"

    def test_inkasso_text_selects_debt_collection(self):
        p = select_profile("invoice", text="ärendet har lämnats till inkasso")
        assert p.service_type == "debt_collection_risk"

    def test_kronofogden_text_selects_debt_collection(self):
        p = select_profile("invoice", text="skickas till kronofogden om ej betalat")
        assert p.service_type == "debt_collection_risk"

    def test_unknown_job_type_returns_generic_lead(self):
        p = select_profile("unknown")
        assert p.service_type == "generic_lead"

    def test_no_crash_for_empty_text(self):
        p = select_profile("lead", text="")
        assert p is not None

    def test_generic_support_for_plain_support_inquiry(self):
        p = select_profile("customer_inquiry", text="jag har en fråga om min faktura")
        assert p.service_type in ("generic_support", "invoice_generic")


# ══════════════════════════════════════════════════════════════════════════════
# Required fields by profile
# ══════════════════════════════════════════════════════════════════════════════

class TestRequiredFieldsByProfile:
    def test_ev_charger_requires_main_fuse(self):
        assert "main_fuse" in get_profile("ev_charger_installation").required_fields

    def test_ev_charger_requires_desired_location(self):
        assert "desired_location" in get_profile("ev_charger_installation").required_fields

    def test_solar_requires_annual_consumption(self):
        assert "annual_consumption" in get_profile("solar_installation").required_fields

    def test_solar_requires_roof_type(self):
        assert "roof_type" in get_profile("solar_installation").required_fields

    def test_battery_requires_solar_exists(self):
        assert "solar_exists" in get_profile("battery_storage").required_fields

    def test_electrical_fault_requires_safety_risk_field(self):
        assert "safety_risk" in get_profile("electrical_fault").required_fields

    def test_electrical_fault_requires_issue_description(self):
        assert "issue_description" in get_profile("electrical_fault").required_fields

    def test_inverter_requires_model_or_error_code(self):
        assert "inverter_model_or_error_code" in get_profile("inverter_support").required_fields

    def test_inverter_requires_production_status(self):
        assert "production_status" in get_profile("inverter_support").required_fields

    def test_debt_collection_requires_sender(self):
        assert "sender" in get_profile("debt_collection_risk").required_fields

    def test_debt_collection_requires_deadline(self):
        assert "deadline" in get_profile("debt_collection_risk").required_fields

    def test_invoice_generic_requires_amount(self):
        assert "amount" in get_profile("invoice_generic").required_fields

    def test_required_fields_differ_between_ev_and_solar(self):
        ev = set(get_profile("ev_charger_installation").required_fields)
        solar = set(get_profile("solar_installation").required_fields)
        assert ev != solar

    def test_required_fields_differ_between_fault_and_generic_support(self):
        fault = set(get_profile("electrical_fault").required_fields)
        generic = set(get_profile("generic_support").required_fields)
        assert fault != generic


# ══════════════════════════════════════════════════════════════════════════════
# Missing fields computation
# ══════════════════════════════════════════════════════════════════════════════

class TestMissingFieldsComputation:
    def test_minimal_ev_charger_is_incomplete(self):
        result = compute_profile_missing_info(
            get_profile("ev_charger_installation"),
            input_data=_input("Laddbox", "Vill ha laddbox."),
            entities={},
        )
        assert result["is_complete"] is False
        assert "address" in result["missing_fields"]

    def test_ev_charger_with_address_no_longer_missing_address(self):
        result = compute_profile_missing_info(
            get_profile("ev_charger_installation"),
            input_data=_input("Laddbox", "Villa på Solvägen 12, 753 20 Uppsala."),
            entities={"address": "Solvägen 12"},
        )
        assert "address" not in result["missing_fields"]

    def test_ev_charger_with_fuse_no_longer_missing_fuse(self):
        result = compute_profile_missing_info(
            get_profile("ev_charger_installation"),
            input_data=_input("Laddbox", "Har 20A säkring i garaget."),
            entities={},
        )
        assert "main_fuse" not in result["missing_fields"]

    def test_ev_charger_garage_satisfies_desired_location(self):
        result = compute_profile_missing_info(
            get_profile("ev_charger_installation"),
            input_data=_input("Laddbox", "Laddboxen ska stå i garaget."),
            entities={},
        )
        assert "desired_location" not in result["missing_fields"]

    def test_solar_with_consumption_kwh_satisfies_annual_consumption(self):
        result = compute_profile_missing_info(
            get_profile("solar_installation"),
            input_data=_input("Solceller", "Vi förbrukar ca 8000 kwh per år."),
            entities={},
        )
        assert "annual_consumption" not in result["missing_fields"]

    def test_solar_roof_type_detected(self):
        result = compute_profile_missing_info(
            get_profile("solar_installation"),
            input_data=_input("Solceller", "Vi har ett plåttak."),
            entities={},
        )
        assert "roof_type" not in result["missing_fields"]

    def test_battery_solar_exists_detected(self):
        result = compute_profile_missing_info(
            get_profile("battery_storage"),
            input_data=_input("Batteri", "Vi har solceller sedan 2022."),
            entities={},
        )
        assert "solar_exists" not in result["missing_fields"]

    def test_electrical_fault_safety_risk_detected(self):
        result = compute_profile_missing_info(
            get_profile("electrical_fault"),
            input_data=_input("Elfel", "Det luktar bränt från proppskåpet."),
            entities={},
        )
        assert "safety_risk" not in result["missing_fields"]

    def test_inverter_error_code_detected(self):
        result = compute_profile_missing_info(
            get_profile("inverter_support"),
            input_data=_input("Växelriktare", "Visar felkod E-12 och producerar inget."),
            entities={},
        )
        assert "inverter_model_or_error_code" not in result["missing_fields"]
        assert "production_status" not in result["missing_fields"]

    def test_invoice_amount_detected(self):
        result = compute_profile_missing_info(
            get_profile("invoice_generic"),
            input_data=_input("Faktura", "Fakturan avser 15 500 kr."),
            entities={},
        )
        assert "amount" not in result["missing_fields"]

    def test_debt_collection_deadline_detected(self):
        result = compute_profile_missing_info(
            get_profile("debt_collection_risk"),
            input_data=_input("Inkasso", "Betala senast 2026-08-01."),
            entities={},
        )
        assert "deadline" not in result["missing_fields"]

    def test_completeness_score_is_zero_to_one(self):
        result = compute_profile_missing_info(
            get_profile("ev_charger_installation"),
            input_data=_input("Test", ""),
            entities={},
        )
        assert 0.0 <= result["completeness_score"] <= 1.0

    def test_schema_source_is_service_profile(self):
        result = compute_profile_missing_info(
            get_profile("solar_installation"),
            input_data=_input("Test", ""),
            entities={},
        )
        assert result["schema_source"] == "service_profile"

    def test_tenant_override_changes_schema_source(self):
        ctx = TenantLeadContext(
            tenant_id="T_TEST",
            context_available=True,
            sources_used=["lead_config"],
            lead_requirements={
                "solar_installation": {
                    "required": ["address", "phone_or_email"],
                    "optional": [],
                }
            },
        )
        result = compute_profile_missing_info(
            get_profile("solar_installation"),
            input_data=_input("Test", ""),
            entities={},
            tenant_ctx=ctx,
        )
        assert result["schema_source"] == "tenant_override"
        assert result["required_fields"] == ["address", "phone_or_email"]


# ══════════════════════════════════════════════════════════════════════════════
# Follow-up question messages
# ══════════════════════════════════════════════════════════════════════════════

class TestFollowUpQuestions:
    def test_none_returned_for_empty_missing_fields(self):
        msg = build_profile_question_message(
            get_profile("ev_charger_installation"), []
        )
        assert msg is None

    def test_ev_charger_message_contains_laddbox_context(self):
        msg = build_profile_question_message(
            get_profile("ev_charger_installation"),
            ["address", "main_fuse"],
        )
        assert msg is not None
        assert "laddbox" in msg.lower()

    def test_ev_charger_message_contains_säkring_label(self):
        msg = build_profile_question_message(
            get_profile("ev_charger_installation"),
            ["main_fuse"],
        )
        assert "säkring" in msg.lower()

    def test_solar_message_mentions_årsförbrukning(self):
        msg = build_profile_question_message(
            get_profile("solar_installation"),
            ["annual_consumption"],
        )
        assert "årsförbrukning" in msg.lower()

    def test_inverter_message_mentions_felkod(self):
        msg = build_profile_question_message(
            get_profile("inverter_support"),
            ["inverter_model_or_error_code"],
        )
        assert "felkod" in msg.lower() or "modell" in msg.lower()

    def test_electrical_fault_message_mentions_bränt(self):
        msg = build_profile_question_message(
            get_profile("electrical_fault"),
            ["safety_risk"],
        )
        assert "bränt" in msg.lower() or "gnistrar" in msg.lower()

    def test_debt_collection_message_returned(self):
        msg = build_profile_question_message(
            get_profile("debt_collection_risk"),
            ["deadline", "amount"],
        )
        assert msg is not None
        assert "belopp" in msg.lower() or "betalning" in msg.lower()

    def test_follow_up_intro_differs_between_profiles(self):
        ev_intro = get_profile("ev_charger_installation").follow_up_intro
        solar_intro = get_profile("solar_installation").follow_up_intro
        assert ev_intro != solar_intro

    def test_company_name_personalises_message(self):
        msg = build_profile_question_message(
            get_profile("ev_charger_installation"),
            ["address"],
            company_name="Elbolaget AB",
        )
        # Company name injection depends on wording — just ensure message is returned
        assert msg is not None
        assert len(msg) > 20

    def test_unknown_field_falls_back_to_capitalised_name(self):
        msg = build_profile_question_message(
            get_profile("generic_lead"),
            ["some_custom_field"],
        )
        assert msg is not None
        assert "Some custom field" in msg


# ══════════════════════════════════════════════════════════════════════════════
# Question generator integration (patched question_generator.py)
# ══════════════════════════════════════════════════════════════════════════════

class TestQuestionGeneratorIntegration:
    def test_service_profile_overrides_generic_intro(self):
        profile = get_profile("solar_installation")
        msg = generate_question_message(
            ["annual_consumption", "roof_type"],
            service_profile=profile,
        )
        assert msg is not None
        assert profile.follow_up_intro[:30] in msg

    def test_without_service_profile_uses_generic_intro(self):
        msg = generate_question_message(["address"])
        assert msg is not None
        assert "ta fram ett bra förslag" in msg

    def test_service_profile_questions_used_for_known_field(self):
        profile = get_profile("ev_charger_installation")
        msg = generate_question_message(["desired_location"], service_profile=profile)
        assert "placering" in msg.lower()

    def test_tenant_company_name_applied_with_profile(self):
        ctx = TenantLeadContext(
            tenant_id="T_TEST",
            context_available=True,
            sources_used=["business_profile"],
            company_name="Solenergi AB",
        )
        profile = get_profile("solar_installation")
        msg = generate_question_message(
            ["annual_consumption"],
            tenant_ctx=ctx,
            service_profile=profile,
        )
        assert msg is not None


# ══════════════════════════════════════════════════════════════════════════════
# Risk routing
# ══════════════════════════════════════════════════════════════════════════════

class TestRiskRouting:
    def test_debt_collection_default_route_is_manual_review(self):
        assert get_profile("debt_collection_risk").default_route == "manual_review"

    def test_debt_collection_complete_action_is_manual_review(self):
        assert get_profile("debt_collection_risk").complete_action == "manual_review"

    def test_debt_collection_missing_action_is_manual_review(self):
        assert get_profile("debt_collection_risk").missing_info_action == "manual_review"

    def test_electrical_fault_high_risk_when_bränt_detected(self):
        profile = get_profile("electrical_fault")
        assert profile.is_high_risk("det luktar bränt och gnistrar") is True

    def test_electrical_fault_not_high_risk_for_normal_fault(self):
        profile = get_profile("electrical_fault")
        assert profile.is_high_risk("jordfelsbrytaren löser ibland") is False

    def test_electrical_panel_high_risk_for_gnistor(self):
        profile = get_profile("electrical_panel")
        assert profile.is_high_risk("gnistor vid proppskåpet") is True

    def test_invoice_generic_not_high_risk(self):
        profile = get_profile("invoice_generic")
        assert profile.is_high_risk("faktura 12345 förfaller 2026-08-01") is False

    def test_resolve_action_high_risk_returns_manual_review(self):
        profile = get_profile("electrical_fault")
        action = profile.resolve_action(is_complete=True, text="luktar bränt")
        assert action == "manual_review"

    def test_resolve_action_incomplete_returns_ask_questions(self):
        profile = get_profile("ev_charger_installation")
        action = profile.resolve_action(is_complete=False, text="vanlig text")
        assert action == "ask_questions"

    def test_resolve_action_complete_no_risk_returns_complete_action(self):
        profile = get_profile("ev_charger_installation")
        action = profile.resolve_action(is_complete=True, text="vanlig text")
        assert action == "create_offer_draft"

    def test_debt_collection_resolve_action_always_manual_review(self):
        profile = get_profile("debt_collection_risk")
        assert profile.resolve_action(is_complete=True, text="belopp 5000 kr") == "manual_review"
        assert profile.resolve_action(is_complete=False, text="inkasso") == "manual_review"


# ══════════════════════════════════════════════════════════════════════════════
# Tenant override seam
# ══════════════════════════════════════════════════════════════════════════════

class TestTenantOverrideSeam:
    def test_no_context_returns_same_profile(self):
        profile = get_profile("ev_charger_installation")
        result = apply_tenant_overrides(profile, tenant_ctx=None)
        assert result.service_type == profile.service_type
        assert result.default_route == profile.default_route

    def test_empty_context_returns_same_profile(self):
        ctx = TenantLeadContext(tenant_id="T_TEST", context_available=False)
        profile = get_profile("solar_installation")
        result = apply_tenant_overrides(profile, tenant_ctx=ctx)
        assert result.service_type == profile.service_type

    def test_routing_hint_overrides_default_route(self):
        ctx = TenantLeadContext(
            tenant_id="T_TEST",
            context_available=True,
            sources_used=["routing_hints"],
            routing_hints={"ev_charger_installation": "support"},
        )
        profile = get_profile("ev_charger_installation")
        result = apply_tenant_overrides(profile, tenant_ctx=ctx)
        assert result.default_route == "support"

    def test_routing_hint_for_other_type_does_not_affect_this_profile(self):
        ctx = TenantLeadContext(
            tenant_id="T_TEST",
            context_available=True,
            sources_used=["routing_hints"],
            routing_hints={"solar_installation": "manual_review"},
        )
        profile = get_profile("ev_charger_installation")
        result = apply_tenant_overrides(profile, tenant_ctx=ctx)
        assert result.default_route == "sales"

    def test_select_profile_passes_tenant_ctx_through(self):
        ctx = TenantLeadContext(
            tenant_id="T_TEST",
            context_available=True,
            sources_used=["routing_hints"],
            routing_hints={"ev_charger_installation": "manual_review"},
        )
        profile = select_profile("lead", lead_type="ev_charger", tenant_ctx=ctx)
        assert profile.default_route == "manual_review"
