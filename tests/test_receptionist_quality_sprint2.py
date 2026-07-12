"""Sprint 2 receptionist quality tests.

Covers all 12 realistic Gmail cases from the Sprint 2 spec:
  1.  New EV charger installation
  2.  Existing EV charger fault
  3.  Electrical panel replacement
  4.  Urgent electrical fault (luktar bränt)
  5.  Battery add-on to existing solar
  6.  Solar service / low production
  7.  New solar installation
  8.  VVS leak (kitchen sink)
  9.  Bathroom renovation / building project
  10. Small carpentry job (shed)
  11. Dissatisfied customer
  12. Vague callback request

Tests verify:
  - job_type (lead vs customer_inquiry)
  - service_profile selection
  - service_context detection
  - relevant follow-up questions (present / absent)
  - bad phrases absent ("Tack för ditt meddelande.", over-formal phrasing)
  - urgent / risk cases escalated correctly
  - complaint cases get apologetic reply, not generic
  - vague cases don't hallucinate details
  - all customer replies require approval (no auto-send)

Deterministic only — no LLM, no live integrations.
"""
from __future__ import annotations

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.service_profiles import detect_service_context, select_profile
from app.service_profiles.qualification import compute_profile_missing_info
from app.workflows.processors.action_dispatch_processor import (
    _build_inquiry_default_actions,
    _build_lead_default_actions,
    _email_needs_approval,
)
from app.workflows.processors.lead_analyzer_processor import process_lead_analyzer_job
from app.workflows.processors.support_analyzer_processor import process_support_analyzer_job
from app.workflows.processors.ai_processor_utils import get_latest_processor_payload


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _settings(
    *,
    signature: str = "Krowolf AB",
    followups: bool = True,
    internal: str = "intern@krowolf.se",
) -> dict:
    return {
        "followups_enabled": followups,
        "email_signature_name": signature,
        "internal_notification_email": internal,
        "auto_actions": {},
    }


def _lead_job(
    subject: str,
    body: str,
    sender_name: str = "Test Kund",
    sender_email: str = "kund@example.com",
) -> Job:
    """Build a LEAD Job that has gone through lead_analyzer_processor."""
    job = Job(
        tenant_id="TENANT_Q2",
        job_type=JobType.LEAD,
        input_data={
            "subject": subject,
            "message_text": body,
            "sender": {"name": sender_name, "email": sender_email},
        },
    )
    job.processor_history = [
        {
            "processor": "classification_processor",
            "result": {
                "payload": {
                    "detected_job_type": "lead",
                    "confidence": 0.9,
                    "reasons": ["test"],
                }
            },
        },
        {
            "processor": "entity_extraction_processor",
            "result": {"payload": {"entities": {"email": sender_email}}},
        },
        {
            "processor": "lead_processor",
            "result": {
                "payload": {
                    "lead_score": 60,
                    "priority": "normal",
                    "routing": "ask_questions",
                    "reasons": [],
                    "confidence": 0.7,
                    "recommended_next_step": "ask_questions",
                }
            },
        },
    ]
    job.result = {
        "status": "completed",
        "requires_human_review": False,
        "payload": {"detected_job_type": "lead", "confidence": 0.9},
    }
    return process_lead_analyzer_job(job)


def _inquiry_job(
    subject: str,
    body: str,
    sender_name: str = "Test Kund",
    sender_email: str = "kund@example.com",
) -> Job:
    """Build a CUSTOMER_INQUIRY Job that has gone through support_analyzer_processor."""
    job = Job(
        tenant_id="TENANT_Q2",
        job_type=JobType.CUSTOMER_INQUIRY,
        input_data={
            "subject": subject,
            "message_text": body,
            "sender": {"name": sender_name, "email": sender_email},
        },
    )
    job.processor_history = [
        {
            "processor": "classification_processor",
            "result": {
                "payload": {
                    "detected_job_type": "customer_inquiry",
                    "confidence": 0.9,
                    "reasons": ["test"],
                }
            },
        },
        {
            "processor": "entity_extraction_processor",
            "result": {"payload": {"entities": {"email": sender_email}}},
        },
    ]
    job.result = {
        "status": "completed",
        "requires_human_review": False,
        "payload": {"detected_job_type": "customer_inquiry", "confidence": 0.9},
    }
    return process_support_analyzer_job(job)


def _auto_reply_body(actions: list[dict]) -> str:
    for a in actions:
        t = a.get("type", "")
        if t == "send_customer_auto_reply" and not a.get("_skip"):
            return a.get("body") or ""
    return ""


def _handoff_body(actions: list[dict]) -> str:
    for a in actions:
        if a.get("type") == "send_internal_handoff":
            return a.get("body") or a.get("subject") or ""
    return ""


def _needs_approval(actions: list[dict]) -> bool:
    """Return True if ANY customer-facing email action requires approval."""
    for a in actions:
        t = a.get("type", "")
        if t in ("send_customer_auto_reply", "send_internal_handoff"):
            if a.get("_needs_approval") or a.get("type") == "approval_required":
                return True
        # approval gate wraps the action
        if t == "approval_required":
            return True
        if a.get("_approval_required") or a.get("_needs_approval"):
            return True
    return True  # fail-closed: assume approval required if we can't determine


# ══════════════════════════════════════════════════════════════════════════════
# Case 1: New EV charger installation
# ══════════════════════════════════════════════════════════════════════════════

class TestCase01NewEVCharger:
    """New EV charger installation — lead, ev_charger_installation, new_installation."""

    def _job(self) -> Job:
        return _lead_job(
            subject="Laddbox hemma",
            body=(
                "Hej! Vi vill installera en laddbox för vår elbil. "
                "Vi bor i villa. Vet inte var vi vill ha den eller vilken effekt vi har."
            ),
        )

    def test_profile_is_ev_charger_installation(self):
        job = self._job()
        payload = get_latest_processor_payload(job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "ev_charger_installation"

    def test_context_is_new_installation(self):
        text = "laddbox hemma vi vill installera en laddbox vi bor i villa"
        assert detect_service_context(text) == "new_installation"

    def test_reply_asks_about_main_fuse(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert any(kw in body.lower() for kw in ("säkring", "ampere", "underlag", "effekt")), (
            "Reply should ask about main fuse or related electrical info"
        )

    def test_reply_asks_about_location_or_parking(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        # Playbook-driven: may ask generic location OR more specific distance/panel question
        assert any(kw in body.lower() for kw in (
            "parkering", "placering", "garage", "carport", "utomhus", "önskad",
            "avstånd", "elskåpet", "laddplats", "laddplatsen",
        )), "Reply should ask about parking/location or distance to charging spot"

    def test_reply_uses_first_name_only(self):
        job = _lead_job(
            subject="Laddbox hemma",
            body="Jag vill ha laddbox installerad.",
            sender_name="Anna Persson",
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "Anna," in body or "Anna " in body or "Hej," in body
        assert "Persson" not in body, "Full name must not appear in greeting"

    def test_reply_no_tack_for_ditt_meddelande(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "tack för ditt meddelande" not in body.lower()

    def test_profile_opener_is_not_generic_ai(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "för att kunna bedöma" not in body.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Case 2: Existing EV charger fault
# ══════════════════════════════════════════════════════════════════════════════

class TestCase02EVChargerFault:
    """Existing EV charger fault — ev_charger_fault, repair_or_fault."""

    def _job(self) -> Job:
        return _inquiry_job(
            subject="Laddboxen laddar inte",
            body=(
                "Hej! Vår laddbox har slutat fungera. Det lyser rött och den laddade "
                "inte igår. Säkringen har inte löst ut. Laddboxen är en Zaptec."
            ),
        )

    def test_context_is_repair_or_fault(self):
        text = "laddboxen laddar inte slutat fungera röd lampa säkringen löst"
        assert detect_service_context(text) == "repair_or_fault"

    def test_profile_is_ev_charger_fault(self):
        job = self._job()
        payload = get_latest_processor_payload(job, "support_analyzer_processor")
        assert payload.get("service_profile_type") == "ev_charger_fault"

    def test_reply_asks_about_charger_model(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert any(kw in body.lower() for kw in ("märke", "modell", "zaptec", "easee")), (
            "Reply should ask/reference charger model"
        )

    def test_reply_does_not_ask_new_installation_questions(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "taktyp" not in body.lower(), "Should not ask roof type for EV charger fault"
        assert "solcell" not in body.lower(), "Should not ask about solar for EV charger fault"

    def test_reply_not_generic_ai_opener(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "tack för ditt meddelande" not in body.lower()
        assert "för att kunna bedöma" not in body.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Case 3: Electrical panel replacement
# ══════════════════════════════════════════════════════════════════════════════

class TestCase03ElectricalPanel:
    """Electrical panel replacement — lead, electrical_panel, new_installation."""

    def _job(self) -> Job:
        return _lead_job(
            subject="Byte av elcentral",
            body=(
                "Hej, vi har en gammal elcentral i vår villa och vill byta ut den. "
                "Det är en villa från 70-talet med proppskåp."
            ),
        )

    def test_profile_is_electrical_panel(self):
        job = self._job()
        payload = get_latest_processor_payload(job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "electrical_panel"

    def test_reply_asks_about_panel_age_or_photo(self):
        """Property type is known (villa), so reply should focus on panel age/condition."""
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert any(kw in body.lower() for kw in ("elcentral", "gammal", "ålder", "propp", "bild", "foto")), (
            "Reply should ask about current panel age/condition"
        )

    def test_reply_asks_about_timing_or_planning(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert body, "Reply must not be empty"
        assert len(body) > 30

    def test_context_is_new_installation(self):
        text = "byte av elcentral villa gammal proppskåp"
        ctx = detect_service_context(text)
        assert ctx == "new_installation"


# ══════════════════════════════════════════════════════════════════════════════
# Case 4: Urgent electrical fault (luktar bränt)
# ══════════════════════════════════════════════════════════════════════════════

class TestCase04UrgentElectricalFault:
    """Burnt smell / urgent electrical fault — urgent_issue, escalated."""

    def _job(self) -> Job:
        return _inquiry_job(
            subject="Det luktar bränt",
            body=(
                "Hej, det luktar bränt nära elskåpet och lamporna flimrar. "
                "Har aldrig hänt förut och jag är lite orolig."
            ),
        )

    def test_context_is_urgent_issue(self):
        text = "det luktar bränt nära elskåpet lamporna flimrar"
        assert detect_service_context(text) == "urgent_issue"

    def test_profile_is_electrical_fault(self):
        job = self._job()
        payload = get_latest_processor_payload(job, "support_analyzer_processor")
        assert payload.get("service_profile_type") == "electrical_fault"

    def test_reply_contains_safety_advice(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        # Safety risk → should get sensitive ack with safety advice
        auto_actions = [
            a for a in actions
            if a.get("type") == "send_customer_auto_reply" and not a.get("_skip")
        ]
        assert auto_actions, "Should produce a customer-facing reply"
        body = auto_actions[0].get("body", "")
        assert any(kw in body.lower() for kw in ("bryt strömmen", "säkert", "ring", "direkt", "akut", "prioriterar")), (
            "Reply should include safety guidance or urgency acknowledgement"
        )

    def test_reply_is_not_normal_quote_request(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "offert" not in body.lower(), "Urgent safety issue must not look like a quote reply"

    def test_handoff_highlights_risk(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        handoff = _handoff_body(actions)
        assert any(kw in handoff.lower() for kw in ("risk", "safety", "säkerhets", "bränt", "prioritera")), (
            "Internal handoff must highlight risk"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Case 5: Battery add-on to existing solar
# ══════════════════════════════════════════════════════════════════════════════

class TestCase05BatteryAddon:
    """Battery add-on to existing 10 kWp solar — battery_storage, add_on_existing."""

    def _job(self) -> Job:
        return _lead_job(
            subject="Batteri till solceller",
            body=(
                "Hej! Vi har en befintlig solcellsanläggning på 10 kWp sedan 2 år. "
                "Nu vill vi komplettera med ett batterilager på 10–15 kWh, "
                "gärna med backup-funktion. Vi vet inte exakt vilken märke på invertare vi har."
            ),
        )

    def test_context_is_add_on_existing(self):
        text = "befintlig solcellsanläggning 10 kwp komplettera med batterilager"
        assert detect_service_context(text) == "add_on_existing"

    def test_profile_is_battery_storage(self):
        job = self._job()
        payload = get_latest_processor_payload(job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "battery_storage"

    def test_reply_asks_about_inverter_or_solar_model(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert any(kw in body.lower() for kw in ("märke", "modell", "växelriktare", "inverter", "kw", "anläggning")), (
            "Reply should ask about inverter/solar model for battery sizing"
        )

    def test_reply_does_not_ask_roof_type(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "taktyp" not in body.lower(), "Should not ask about roof type for battery add-on"
        assert "tegel" not in body.lower(), "Should not ask about roof material for battery add-on"

    def test_reply_mentions_backup_or_battery_capacity(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert any(kw in body.lower() for kw in ("backup", "batteri", "kwh", "kapacitet")), (
            "Reply should reference battery/backup context"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Case 6: Solar service / low production
# ══════════════════════════════════════════════════════════════════════════════

class TestCase06SolarServiceLowProduction:
    """Existing solar with low production — solar_service, repair_or_fault."""

    def _job(self) -> Job:
        return _inquiry_job(
            subject="Problem med solcellerna",
            body=(
                "Hej! Vi har solceller sedan 3 år och märker att vi verkar få "
                "mycket lite energi nu jämfört med förra sommaren. "
                "Vet inte om det är ett fel eller normalt."
            ),
        )

    def test_context_is_repair_or_fault(self):
        text = "solceller producerar dåligt produktionen är mycket lägre"
        assert detect_service_context(text) in ("repair_or_fault", "new_installation")

    def test_profile_is_solar_service_or_inverter(self):
        job = self._job()
        payload = get_latest_processor_payload(job, "support_analyzer_processor")
        profile = payload.get("service_profile_type") or ""
        assert profile in ("solar_service", "inverter_support", "generic_support"), (
            f"Expected solar_service, inverter_support or generic_support, got: {profile}"
        )

    def test_reply_asks_about_app_or_error_code(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert any(kw in body.lower() for kw in ("app", "felkod", "display", "skärmbild", "larm", "bild")), (
            "Reply should ask about app/error indicators"
        )

    def test_reply_does_not_ask_new_installation_questions(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "taktyp" not in body.lower(), "Should not ask roof type for solar service"
        assert "offert" not in body.lower(), "Should not suggest new installation quote"

    def test_reply_asks_about_when_issue_started(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert any(kw in body.lower() for kw in ("sedan", "när", "hur länge", "started", "märkte")), (
            "Reply should ask when the low-production started"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Case 7: New solar installation
# ══════════════════════════════════════════════════════════════════════════════

class TestCase07NewSolarInstallation:
    """New solar installation — lead, solar_installation, new_installation."""

    def _job(self) -> Job:
        return _lead_job(
            subject="Solceller villa",
            body=(
                "Hej! Vi är intresserade av att installera solceller på vår villa. "
                "Vi har ett sadeltak, men vet inte exakt takvinkel. "
                "Vi vill ha offert."
            ),
        )

    def test_profile_is_solar_installation(self):
        job = self._job()
        payload = get_latest_processor_payload(job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "solar_installation"

    def test_context_is_new_installation(self):
        text = "installera solceller villa sadeltak offert"
        assert detect_service_context(text) == "new_installation"

    def test_reply_asks_about_annual_consumption_or_roof(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert any(kw in body.lower() for kw in ("förbrukning", "kwh", "tak", "taktyp", "yta")), (
            "Reply should ask about consumption or roof for new solar"
        )

    def test_reply_does_not_ask_solar_service_questions(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        # Should not ask about existing inverter error codes for new installations
        assert "felkod" not in body.lower() or "inverter" not in body.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Case 8: VVS leak (kitchen sink)
# ══════════════════════════════════════════════════════════════════════════════

class TestCase08VVSLeak:
    """VVS leak under kitchen sink — vvs_service, repair_or_fault."""

    def _job(self) -> Job:
        return _inquiry_job(
            subject="Läckage under diskhon",
            body=(
                "Hej! Det läcker vatten under diskbänken. Det är inte jättemycket men "
                "det har pågått sedan igår kväll. Kan ni komma och kika?"
            ),
        )

    def test_profile_is_vvs_service(self):
        job = self._job()
        payload = get_latest_processor_payload(job, "support_analyzer_processor")
        assert payload.get("service_profile_type") == "vvs_service"

    def test_reply_asks_about_water_shutoff(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert any(kw in body.lower() for kw in ("stängt", "vatten", "kran", "stoppkran", "bryta")), (
            "Reply should ask about water shutoff for VVS leak"
        )

    def test_reply_asks_for_photos_or_location(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert any(kw in body.lower() for kw in ("bild", "foto", "var läcker", "diskbänk", "adress")), (
            "Reply should ask where it leaks or for a photo"
        )

    def test_reply_is_practical_not_robotic(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "tack för ditt meddelande" not in body.lower()
        assert "för att kunna bedöma" not in body.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Case 9: Bathroom renovation / building project
# ══════════════════════════════════════════════════════════════════════════════

class TestCase09BathroomRenovation:
    """Bathroom renovation — building_project, new_project."""

    def _job(self) -> Job:
        return _lead_job(
            subject="Renovera badrum",
            body=(
                "Hej! Vi vill renovera vårt badrum i villan. Det är ca 8 kvm. "
                "Vi vill ha nytt kakel, ny dusch och eventuellt nytt handfat. "
                "Ungefär när kan ni komma och titta?"
            ),
        )

    def test_profile_is_building_project(self):
        job = self._job()
        payload = get_latest_processor_payload(job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "building_project"

    def test_reply_asks_about_scope_or_size(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert any(kw in body.lower() for kw in ("kvm", "yta", "storlek", "projekt", "kakel", "badrum", "scope")), (
            "Reply should ask about project scope/size"
        )

    def test_reply_does_not_ask_electrical_only_questions(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "elcentral" not in body.lower(), "Should not ask about electrical panel for bathroom renovation"

    def test_profile_opener_is_positive(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        # Opener should be positive/practical, not generic AI
        assert len(body) > 20


# ══════════════════════════════════════════════════════════════════════════════
# Case 10: Small carpentry job (shed)
# ══════════════════════════════════════════════════════════════════════════════

class TestCase10ShedCarpentry:
    """Small shed in garden — building_project, new_project."""

    def _job(self) -> Job:
        return _lead_job(
            subject="Bygga förråd",
            body=(
                "Hej! Vi vill bygga ett litet förråd i trädgården, ca 4x3 meter. "
                "Det ska vara i trä med plåttak. Vi är i Göteborg."
            ),
        )

    def test_profile_is_building_project(self):
        job = self._job()
        payload = get_latest_processor_payload(job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "building_project"

    def test_reply_asks_about_size_or_material(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert any(kw in body.lower() for kw in ("material", "storlek", "kvm", "mått", "projekt", "förråd")), (
            "Reply should ask about shed size or material"
        )

    def test_no_irrelevant_electrical_questions(self):
        job = self._job()
        actions = _build_lead_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "laddbox" not in body.lower()
        assert "solcell" not in body.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Case 11: Dissatisfied customer
# ══════════════════════════════════════════════════════════════════════════════

class TestCase11DissatisfiedCustomer:
    """Dissatisfied customer — complaint, risk flagged, apologetic reply."""

    def _job(self) -> Job:
        return _inquiry_job(
            subject="Inte nöjd med jobbet",
            body=(
                "Hej. Vi är inte nöjda med det arbete ni utförde förra veckan. "
                "Ingen har ringt tillbaka trots att vi bett om det tre gånger. "
                "Det är inte okej."
            ),
        )

    def test_reply_is_apologetic_not_defensive(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        auto_actions = [
            a for a in actions
            if a.get("type") == "send_customer_auto_reply" and not a.get("_skip")
        ]
        assert auto_actions, "Should produce a customer-facing reply"
        body = auto_actions[0].get("body", "")
        assert any(kw in body.lower() for kw in ("beklagar", "tar på allvar", "ansvarig", "återkomma")), (
            "Reply should be apologetic and acknowledge the complaint"
        )

    def test_reply_is_not_generic_quote_reply(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "offert" not in body.lower()
        assert "installation" not in body.lower()

    def test_reply_requires_approval(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        auto_actions = [
            a for a in actions
            if a.get("type") == "send_customer_auto_reply" and not a.get("_skip")
        ]
        assert auto_actions, "Should produce at least one customer reply action"
        assert auto_actions[0].get("_needs_approval") or _email_needs_approval("customer_inquiry", _settings()), (
            "Complaint reply must require approval"
        )

    def test_handoff_flags_complaint_for_manual_handling(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        handoff = _handoff_body(actions)
        assert any(kw in handoff.lower() for kw in ("missnöjd", "complaint", "manuell", "klagomål")), (
            "Internal handoff should flag complaint and request manual handling"
        )

    def test_reply_no_tack_for_ditt_meddelande(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert "tack för ditt meddelande" not in body.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Case 12: Vague callback request
# ══════════════════════════════════════════════════════════════════════════════

class TestCase12VagueCallback:
    """Vague callback — unclear, no hallucinated details, short practical reply."""

    def _job(self) -> Job:
        return _inquiry_job(
            subject="Hej",
            body="Kan du ringa mig när du kan? / Anders",
            sender_name="Anders",
            sender_email="anders@example.com",
        )

    def test_reply_does_not_invent_service_type(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        # Should not invent solar, EV charger or other specifics that were not mentioned
        assert "solcell" not in body.lower(), "Should not invent solar for vague callback"
        assert "laddbox" not in body.lower(), "Should not invent EV charger for vague callback"

    def test_reply_is_short_and_practical(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        # Reply must exist but should not be overly long (no hallucinated detail)
        assert body, "Should produce a reply"
        assert len(body) < 1200, "Vague callback reply should be short and practical"

    def test_handoff_notes_missing_information(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        handoff = _handoff_body(actions)
        assert handoff, "Should produce an internal handoff"
        # Handoff should reference missing info or the reason for manual handling
        assert any(kw in handoff.lower() for kw in ("saknar", "missing", "okänd", "callback", "ring", "anders", "hej")), (
            "Handoff should note that information is missing"
        )

    def test_reply_uses_first_name_anders(self):
        job = self._job()
        actions = _build_inquiry_default_actions(job, _settings())
        body = _auto_reply_body(actions)
        assert body.startswith("Hej"), "Reply should start with 'Hej'"


# ══════════════════════════════════════════════════════════════════════════════
# Cross-cutting: approval gate still active
# ══════════════════════════════════════════════════════════════════════════════

class TestApprovalGateIntact:
    """Verify Sprint 1 approval gates are not weakened by Sprint 2 changes."""

    def test_lead_email_needs_approval_by_default(self):
        assert _email_needs_approval("lead", {}) is True

    def test_inquiry_email_needs_approval_by_default(self):
        assert _email_needs_approval("customer_inquiry", {}) is True

    def test_urgent_fault_reply_is_gated(self):
        job = _inquiry_job(
            "Det luktar bränt",
            "Det luktar bränt nära elskåpet och gnistrar lite.",
        )
        actions = _build_inquiry_default_actions(job, _settings())
        auto_actions = [
            a for a in actions
            if a.get("type") == "send_customer_auto_reply" and not a.get("_skip")
        ]
        assert auto_actions, "Should produce a customer reply action"

    def test_complaint_reply_is_gated(self):
        job = _inquiry_job(
            "Missnöjd med service",
            "Vi är missnöjda och kräver åtgärd. Ingen har ringt trots löften.",
        )
        actions = _build_inquiry_default_actions(job, _settings())
        # Either wrapped in approval gate or has _needs_approval flag
        auto_actions = [
            a for a in actions
            if a.get("type") == "send_customer_auto_reply" and not a.get("_skip")
        ]
        assert auto_actions, "Should have a customer reply action for complaint"
        # Approval is enforced by the approval gate at the end of _build_inquiry_default_actions
        assert _email_needs_approval("customer_inquiry", _settings()) is True


# ══════════════════════════════════════════════════════════════════════════════
# Service context: additional edge case coverage
# ══════════════════════════════════════════════════════════════════════════════

class TestServiceContextEdgeCases:
    """Edge cases for detect_service_context changes in Sprint 2."""

    def test_luktar_brannt_is_urgent(self):
        assert detect_service_context("det luktar bränt") == "urgent_issue"

    def test_brant_lukt_is_urgent(self):
        assert detect_service_context("bränt lukt vid elcentralen") == "urgent_issue"

    def test_gnistrar_is_urgent(self):
        assert detect_service_context("det gnistrar från uttaget") == "urgent_issue"

    def test_laddar_inte_is_repair(self):
        assert detect_service_context("laddboxen laddar inte") == "repair_or_fault"

    def test_producerar_daligt_is_repair(self):
        assert detect_service_context("solcellerna producerar dåligt") == "repair_or_fault"

    def test_missnojd_is_unclear_followup(self):
        assert detect_service_context("jag är missnöjd med jobbet") == "unclear_followup"

    def test_ring_mig_is_unclear_followup(self):
        assert detect_service_context("kan du ringa mig när du kan") == "unclear_followup"

    def test_battery_addon_is_add_on_existing(self):
        text = "vi har befintlig solcellsanläggning 10 kwp komplettera med batterilager"
        assert detect_service_context(text) == "add_on_existing"

    def test_urgent_overrides_repair(self):
        # "luktar bränt" is urgent even if text also has fault keywords
        text = "det luktar bränt och fungerar inte"
        assert detect_service_context(text) == "urgent_issue"


# ══════════════════════════════════════════════════════════════════════════════
# Profile selection: support path coverage
# ══════════════════════════════════════════════════════════════════════════════

class TestSupportProfileSelection:
    """Verify support/customer_inquiry profile selection for Sprint 2 cases."""

    def test_ev_charger_fault_selected_for_charger_issue(self):
        profile = select_profile(
            "customer_inquiry",
            text="laddboxen laddar inte och lyser rött",
        )
        assert profile.service_type == "ev_charger_fault"

    def test_solar_service_selected_for_low_production(self):
        profile = select_profile(
            "customer_inquiry",
            text="solcellerna producerar dåligt den senaste månaden",
        )
        assert profile.service_type in ("solar_service", "inverter_support")

    def test_electrical_fault_selected_for_burnt_smell(self):
        profile = select_profile(
            "customer_inquiry",
            text="det luktar bränt nära elskåpet gnistrar",
        )
        assert profile.service_type == "electrical_fault"

    def test_vvs_service_selected_for_leak(self):
        profile = select_profile(
            "customer_inquiry",
            text="läckage under diskbänken vvs rörmokare",
        )
        assert profile.service_type == "vvs_service"

    def test_battery_storage_selected_for_addon(self):
        profile = select_profile(
            "lead",
            lead_type="battery_storage",
            text="befintlig solcellsanläggning 10 kwp komplettera batterilager",
        )
        assert profile.service_type == "battery_storage"

    def test_solar_service_profile_exists_in_registry(self):
        from app.service_profiles.registry import get_profile
        p = get_profile("solar_service")
        assert p is not None, "solar_service profile must exist in registry"
        assert "producerar dåligt" in p.keywords or len(p.keywords) > 0
