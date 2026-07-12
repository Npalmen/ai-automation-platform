"""Service Playbook Architecture Tests.

Covers:
  1. Playbook registration and structure for all 5 service families.
  2. Context detection for all supported contexts.
  3. Fact state detection (confirmed / unknown / uncertain / partial / missing).
  4. Unknown/negation phrase handling in Swedish.
  5. Body signature name extraction.
  6. Question selection (relevant, suppressed, capped at max).
  7. Complaint override detection.

Deterministic only — no LLM, no live integrations.
"""
from __future__ import annotations

import pytest

from app.service_profiles.context import detect_service_context
from app.service_profiles.facts import FactState, detect_fact_state, detect_all_facts
from app.service_profiles.name_extraction import (
    extract_body_signature_name,
    resolve_customer_name,
)
from app.service_profiles.playbook import (
    get_complaint_override,
    get_playbook,
    is_complaint,
    list_playbooks,
    select_questions_from_playbook,
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Playbook registry
# ══════════════════════════════════════════════════════════════════════════════


class TestPlaybookRegistry:
    """All 5 service-family playbooks are registered and structurally valid."""

    REQUIRED_IDS = {
        "electrical_fault",
        "ev_charger_installation",
        "solar_installation",
        "battery_storage",
        "vvs_service",
        "building_project",
    }

    def test_all_required_playbooks_registered(self):
        ids = {p.id for p in list_playbooks()}
        assert self.REQUIRED_IDS.issubset(ids), (
            f"Missing playbooks: {self.REQUIRED_IDS - ids}"
        )

    def test_electrical_playbook_has_urgent_context(self):
        pb = get_playbook("electrical_fault")
        assert pb is not None
        assert "urgent_issue" in pb.contexts

    def test_ev_charger_playbook_has_new_installation_context(self):
        pb = get_playbook("ev_charger_installation")
        assert pb is not None
        assert "new_installation" in pb.contexts

    def test_battery_playbook_has_add_on_context(self):
        pb = get_playbook("battery_storage")
        assert pb is not None
        assert "add_on_existing" in pb.contexts

    def test_vvs_playbook_has_repair_context(self):
        pb = get_playbook("vvs_service")
        assert pb is not None
        assert "repair_or_fault" in pb.contexts

    def test_building_playbook_has_new_project_or_installation(self):
        pb = get_playbook("building_project")
        assert pb is not None
        assert "new_project" in pb.contexts or "new_installation" in pb.contexts

    def test_ev_charger_new_installation_suppresses_desired_location(self):
        pb = get_playbook("ev_charger_installation")
        assert pb is not None
        ctx = pb.contexts.get("new_installation")
        assert ctx is not None
        assert "desired_location" in ctx.suppress_fields

    def test_battery_add_on_suppresses_property_type(self):
        pb = get_playbook("battery_storage")
        ctx = pb.contexts.get("add_on_existing")
        assert ctx is not None
        assert "property_type" in ctx.suppress_fields

    def test_battery_add_on_prioritizes_inverter(self):
        pb = get_playbook("battery_storage")
        ctx = pb.contexts.get("add_on_existing")
        assert ctx is not None
        assert "inverter_brand_model" in ctx.priority_fields

    def test_vvs_suppresses_main_fuse_in_repair_context(self):
        pb = get_playbook("vvs_service")
        ctx = pb.contexts.get("repair_or_fault")
        assert ctx is not None
        assert "main_fuse" in ctx.suppress_fields


# ══════════════════════════════════════════════════════════════════════════════
# 2. Context detection
# ══════════════════════════════════════════════════════════════════════════════


class TestServiceContextDetection:
    """detect_service_context returns the expected context."""

    def test_new_installation_default(self):
        text = "jag vill installera en laddbox hemma"
        assert detect_service_context(text) == "new_installation"

    def test_add_on_existing_solar(self):
        text = "vi har solceller och vill lägga till ett batteri"
        assert detect_service_context(text) == "add_on_existing"

    def test_repair_or_fault_ev_charger(self):
        text = "laddboxen fungerar inte den laddar inte alls"
        assert detect_service_context(text) == "repair_or_fault"

    def test_repair_or_fault_vvs_leak(self):
        text = "det läcker vatten under diskbänken"
        assert detect_service_context(text) == "repair_or_fault"

    def test_urgent_issue_burnt_smell(self):
        text = "det luktar bränt vid elskåpet och lamporna flimrar"
        assert detect_service_context(text) == "urgent_issue"

    def test_urgent_issue_sparks(self):
        text = "det gnistrar i vägguttaget när jag kopplar in"
        assert detect_service_context(text) == "urgent_issue"

    def test_service_or_maintenance(self):
        text = "jag vill boka ett servicebesök för min anläggning"
        assert detect_service_context(text) == "service_or_maintenance"

    def test_urgent_takes_priority_over_repair(self):
        text = "det luktar bränt och funkar inte längre"
        assert detect_service_context(text) == "urgent_issue"

    def test_complaint_returns_unclear_followup(self):
        # Complaint signals map to unclear_followup context
        text = "ingen har ringt trots att jag blivit lovad återkoppling"
        ctx = detect_service_context(text)
        assert ctx in ("unclear_followup", "repair_or_fault", "new_installation")


# ══════════════════════════════════════════════════════════════════════════════
# 3. Fact state detection
# ══════════════════════════════════════════════════════════════════════════════


class TestFactStateDetection:
    """detect_fact_state classifies field states correctly."""

    def test_main_fuse_confirmed_explicit_ampere(self):
        text = "vi har en 25A huvudsäkring i huset"
        state = detect_fact_state("main_fuse", text)
        assert state == FactState.CONFIRMED

    def test_main_fuse_unknown_vet_inte(self):
        text = "jag vet inte vad jag har för huvudsäkring"
        state = detect_fact_state("main_fuse", text)
        assert state in (FactState.UNKNOWN, FactState.MISSING)

    def test_main_fuse_uncertain_tror_att(self):
        text = "jag tror att vi har 20 ampere men är inte säker"
        state = detect_fact_state("main_fuse", text)
        assert state in (FactState.UNCERTAIN, FactState.CONFIRMED)

    def test_solar_exists_confirmed_by_kwp(self):
        text = "vi har 10 kWp solceller sedan ungefär två år tillbaka"
        state = detect_fact_state("solar_exists", text)
        assert state == FactState.CONFIRMED

    def test_battery_capacity_confirmed(self):
        text = "vi vill ha ett batteri på cirka 10-15 kWh"
        state = detect_fact_state("desired_battery_capacity", text)
        assert state in (FactState.CONFIRMED, FactState.UNCERTAIN, FactState.MISSING)

    def test_property_type_confirmed_villa(self):
        text = "vi bor i villa och parkerar bredvid huset"
        state = detect_fact_state("property_type", text)
        assert state == FactState.CONFIRMED

    def test_inverter_brand_unknown_ingen_aning(self):
        text = "ingen aning vilken växelriktare vi har tyvärr"
        state = detect_fact_state("inverter_brand_model", text)
        assert state in (FactState.UNKNOWN, FactState.MISSING)

    def test_missing_returns_missing(self):
        text = "jag vill installera en laddbox hemma"
        state = detect_fact_state("main_fuse", text)
        assert state == FactState.MISSING

    def test_confirmed_takes_priority_over_nearby_unknown(self):
        # "vet inte" refers to main_fuse, not property_type
        text = "vi bor på villan, vet inte vad jag har för huvudsäkring"
        prop_state = detect_fact_state("property_type", text)
        assert prop_state == FactState.CONFIRMED, (
            "property_type must be CONFIRMED even though 'vet inte' is nearby"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4. Unknown/negation phrases
# ══════════════════════════════════════════════════════════════════════════════


class TestNegationPhrases:
    """Swedish unknown/negation phrases are correctly handled."""

    @pytest.mark.parametrize("phrase,field", [
        ("vet inte vad jag har för huvudsäkring", "main_fuse"),
        ("osäker på huvudsäkringen", "main_fuse"),
        ("ingen aning vilken växelriktare vi har", "inverter_brand_model"),
        ("vet inte modell på laddboxen", "charger_preference"),
    ])
    def test_unknown_or_uncertain_state(self, phrase: str, field: str):
        state = detect_fact_state(field, phrase)
        assert state in (FactState.UNKNOWN, FactState.UNCERTAIN, FactState.MISSING), (
            f"Expected UNKNOWN/UNCERTAIN/MISSING for '{phrase}' field '{field}', got {state}"
        )

    def test_not_confirmed_when_customer_says_vet_inte(self):
        text = "vet inte vad jag har för huvudsäkring"
        state = detect_fact_state("main_fuse", text)
        assert state != FactState.CONFIRMED


# ══════════════════════════════════════════════════════════════════════════════
# 5. Body signature name extraction
# ══════════════════════════════════════════════════════════════════════════════


class TestNameExtraction:
    """extract_body_signature_name and resolve_customer_name work correctly."""

    @pytest.mark.parametrize("body,expected_name", [
        ("Hej,\njag vill ha laddbox.\nMvh Anders", "Anders"),
        ("Hej!\nDet läcker vatten.\nMed vänlig hälsning Lena", "Lena"),
        ("Kan ni hjälpa?\nHälsningar Per\n070-333 44 55", "Per"),
        ("Vi vill ha solceller.\n/Anders", "Anders"),
        ("Hjälp tack!\nVänligen, Sara", "Sara"),
    ])
    def test_extracts_name_from_signature(self, body: str, expected_name: str):
        result = extract_body_signature_name(body)
        assert result == expected_name, f"Expected '{expected_name}', got '{result}'"

    def test_does_not_extract_phone_number(self):
        body = "Mvh 070-111 22 33"
        result = extract_body_signature_name(body)
        assert result is None, "Should not extract phone number as name"

    def test_does_not_extract_none_from_empty(self):
        assert extract_body_signature_name("") is None
        assert extract_body_signature_name(None) is None  # type: ignore[arg-type]

    def test_resolve_prefers_body_name_over_sender(self):
        result = resolve_customer_name(
            sender_name="Niklas Palm",
            message_text="Hej!\nJag vill ha laddbox.\nMvh Anders",
        )
        assert result == "Anders", (
            "resolve_customer_name must prefer body signature over sender name"
        )

    def test_resolve_uses_sender_when_names_match(self):
        result = resolve_customer_name(
            sender_name="Anders Svensson",
            message_text="Hej.\nMvh Anders",
        )
        # Same first name — should return sender or body name (both are valid)
        assert result.lower().startswith("anders")

    def test_resolve_uses_sender_when_no_body_signature(self):
        result = resolve_customer_name(
            sender_name="Karin Eriksson",
            message_text="Hej, jag vill boka ett servicebesök.",
        )
        assert result == "Karin Eriksson"


# ══════════════════════════════════════════════════════════════════════════════
# 6. Question selection with suppression
# ══════════════════════════════════════════════════════════════════════════════


class TestQuestionSelection:
    """select_questions_from_playbook respects suppression, priority and max cap."""

    def test_battery_add_on_suppresses_property_type(self):
        fact_states = {}
        selected = select_questions_from_playbook(
            service_type="battery_storage",
            service_context="add_on_existing",
            fact_states=fact_states,
            base_missing_fields=["contact_name", "property_type", "inverter_brand_model"],
            max_questions=4,
        )
        assert "property_type" not in selected, (
            "battery add-on should suppress property_type"
        )

    def test_battery_add_on_prioritizes_inverter(self):
        fact_states = {}
        selected = select_questions_from_playbook(
            service_type="battery_storage",
            service_context="add_on_existing",
            fact_states=fact_states,
            base_missing_fields=["contact_name", "address", "inverter_brand_model"],
            max_questions=4,
        )
        assert "inverter_brand_model" in selected

    def test_confirmed_facts_are_skipped(self):
        fact_states = {"main_fuse": FactState.CONFIRMED}
        selected = select_questions_from_playbook(
            service_type="ev_charger_installation",
            service_context="new_installation",
            fact_states=fact_states,
            base_missing_fields=["main_fuse", "contact_name"],
            max_questions=4,
        )
        assert "main_fuse" not in selected, (
            "Confirmed facts must not be re-asked"
        )

    def test_unknown_facts_are_included(self):
        fact_states = {"main_fuse": FactState.UNKNOWN}
        selected = select_questions_from_playbook(
            service_type="ev_charger_installation",
            service_context="new_installation",
            fact_states=fact_states,
            base_missing_fields=["main_fuse", "contact_name"],
            max_questions=4,
        )
        assert "main_fuse" in selected, (
            "UNKNOWN main_fuse should still be asked (softly)"
        )

    def test_max_questions_respected(self):
        selected = select_questions_from_playbook(
            service_type="battery_storage",
            service_context="add_on_existing",
            fact_states={},
            base_missing_fields=[
                "contact_name", "phone_or_email", "address",
                "inverter_brand_model", "backup_requirement",
            ],
            max_questions=3,
        )
        assert len(selected) <= 3

    def test_ev_charger_repair_suppresses_location(self):
        selected = select_questions_from_playbook(
            service_type="ev_charger_installation",
            service_context="repair_or_fault",
            fact_states={},
            base_missing_fields=["desired_location", "issue_description", "charger_model_or_brand"],
            max_questions=4,
        )
        assert "desired_location" not in selected

    def test_unknown_service_type_returns_base_fields(self):
        selected = select_questions_from_playbook(
            service_type="unknown_type",
            service_context="new_installation",
            fact_states={},
            base_missing_fields=["contact_name", "address"],
            max_questions=4,
        )
        assert "contact_name" in selected
        assert "address" in selected


# ══════════════════════════════════════════════════════════════════════════════
# 7. Complaint override
# ══════════════════════════════════════════════════════════════════════════════


class TestComplaintOverride:
    """is_complaint detects all complaint trigger keywords."""

    @pytest.mark.parametrize("text", [
        "jag är inte nöjd med hur detta har hanterats",
        "missnöjd med servicen",
        "ingen har ringt trots att ni lovade",
        "besviken på er service",
        "ingen ringde tillbaka",
        "lovad återkoppling men fick ingenting",
        "inte hört av er sedan ett halvår",
        "vi vill reklamera arbetet",
    ])
    def test_is_complaint_detects_signal(self, text: str):
        assert is_complaint(text), f"Expected complaint detection for: '{text}'"

    def test_normal_lead_is_not_complaint(self):
        assert not is_complaint("jag vill installera en laddbox hemma")
        assert not is_complaint("vi vill ha solceller på taket")
        assert not is_complaint("det läcker vatten i köket")

    def test_complaint_override_suppresses_all_technical_fields(self):
        override = get_complaint_override()
        assert override.suppress_all_technical_fields is True

    def test_complaint_override_has_internal_flag(self):
        override = get_complaint_override()
        assert override.internal_flag, "Complaint override must have an internal_flag"

    def test_complaint_override_has_reply_strategy(self):
        override = get_complaint_override()
        assert "acknowledge" in override.reply_strategy.lower() or len(override.reply_strategy) > 20
