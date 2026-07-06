"""Local evals for Swedish extraction & qualification quality.

Scenarios are synthetic Swedish installation/service company messages.
Deterministic only — no LLM, no live integrations, no external calls.

Covers:
  Focus 1  — address / location extraction
  Focus 2  — service / work type detection
  Focus 3  — contact details and customer type
  Focus 4  — lead qualification (completeness, missing fields, next action)
  Focus 5  — support qualification (urgency, safety, escalation)
  Focus 6  — invoice / economy (OCR, org number, risk level)
  Focus 7  — routing hints
  Focus 8  — missing fields reporting
"""
from __future__ import annotations

import pytest

from app.lead.analyzer import analyze_lead
from app.lead.missing_info import compute_missing_info
from app.lead.next_action import decide_next_action
from app.lead.scorer import score_lead
from app.support.analyzer import analyze_support
from app.workflows.processors.ai_processor_utils import (
    extract_phone,
    extract_invoice_amount,
    extract_invoice_number,
    extract_due_date,
    extract_swedish_location,
    extract_org_number,
    extract_ocr_number,
    detect_invoice_risk_level,
)
from app.workflows.intelligence_safety import assess_content_risk


# ── helpers ───────────────────────────────────────────────────────────────────

def _input(subject: str, body: str, *, email: str = "kund@example.com", phone: str | None = None) -> dict:
    sender: dict = {"name": "Testperson", "email": email}
    if phone:
        sender["phone"] = phone
    return {"subject": subject, "message_text": body, "sender": sender}


# ══════════════════════════════════════════════════════════════════════════════
# Focus 1 — Swedish address and location extraction
# ══════════════════════════════════════════════════════════════════════════════

class TestAddressExtraction:
    def test_villa_with_full_address(self):
        text = "Hej, vi vill ha offert på laddbox till villa på Solvägen 12, 753 20 Uppsala."
        loc = extract_swedish_location(text)
        assert loc["street_address"] == "Solvägen 12"
        assert loc["postal_code"] == "753 20"
        assert loc["city"] == "Uppsala"
        assert loc["property_type"] == "villa"

    def test_brf_with_street_and_city(self):
        text = "Gäller BRF Solgläntan på Storgatan 4 i Enköping."
        loc = extract_swedish_location(text)
        assert loc["street_address"] == "Storgatan 4"
        assert loc["city"] == "Enköping"
        assert loc["property_type"] == "brf"

    def test_lantbruk_utanfor_stad(self):
        text = "Vi har en gård utanför Örsundsbro och vill installera batteri."
        loc = extract_swedish_location(text)
        assert loc["city"] == "Örsundsbro"
        assert loc["property_type"] == "lantbruk"

    def test_fastighetsbeteckning(self):
        text = "Fastighetsbeteckning Uppsala Nåntuna 12:3."
        loc = extract_swedish_location(text)
        assert "Uppsala Nåntuna 12:3" in loc.get("property_designation", "")

    def test_address_with_postal_code_only(self):
        text = "Adressen är Industrivägen 5B, 753 50 Uppsala."
        loc = extract_swedish_location(text)
        assert loc["postal_code"] == "753 50"
        assert loc["city"] == "Uppsala"

    def test_city_after_preposition(self):
        text = "Vi befinner oss i Västerås och behöver hjälp."
        loc = extract_swedish_location(text)
        assert loc["city"] == "Västerås"

    def test_no_address_returns_empty_dict(self):
        text = "Hej, vad kostar en laddbox?"
        loc = extract_swedish_location(text)
        assert loc == {}

    def test_multiword_street_name(self):
        text = "Leveransadress: Norra Strandvägen 3, 753 30 Uppsala."
        loc = extract_swedish_location(text)
        assert "Norra Strandvägen 3" in loc.get("street_address", "")
        assert loc["postal_code"] == "753 30"


# ══════════════════════════════════════════════════════════════════════════════
# Focus 2 — Service / work type detection
# ══════════════════════════════════════════════════════════════════════════════

class TestServiceTypeDetection:
    def test_ev_charger_lead(self):
        analysis = analyze_lead(_input("Offert laddbox", "Vill ha offert på laddbox till villan."))
        assert analysis.lead_type == "ev_charger"

    def test_solar_installation_lead(self):
        analysis = analyze_lead(_input("Solceller", "Intresserad av solcellsinstallation på huset."))
        assert analysis.lead_type == "solar_installation"

    def test_battery_storage_lead(self):
        analysis = analyze_lead(_input("Batteri", "Vill komplettera solcellerna med ett batterilager."))
        assert analysis.lead_type == "battery_storage"

    def test_electrical_work_lead(self):
        analysis = analyze_lead(_input("Elcentral", "Behöver byta elcentral, gammal säkringsdosa."))
        assert analysis.lead_type == "electrical_work"

    def test_electrical_fault_felsökning(self):
        analysis = analyze_lead(_input("Felsökning", "Behöver felsökning av elinstallationen i garaget."))
        assert analysis.lead_type == "electrical_work"

    def test_inverter_solar(self):
        analysis = analyze_lead(_input("Växelriktare", "Växelriktaren visar felkod och solcellerna producerar inget."))
        assert analysis.lead_type == "solar_installation"

    def test_jordfelsbrytare_electrical(self):
        analysis = analyze_lead(_input("Jordfelsbrytare", "Jordfelsbrytaren löser så fort vi kopplar in laddboxen."))
        assert analysis.lead_type == "electrical_work"

    def test_rooftop_cleaning(self):
        analysis = analyze_lead(_input("Taktvätt", "Taket behöver tvättas, fullt av mossa och lav."))
        assert analysis.lead_type == "roof_cleaning"


# ══════════════════════════════════════════════════════════════════════════════
# Focus 3 — Contact details and customer type
# ══════════════════════════════════════════════════════════════════════════════

class TestPhoneExtraction:
    def test_swedish_mobile_with_dashes(self):
        phone = extract_phone("", "Ring mig på 070-123 45 67 när som.")
        assert phone is not None
        assert "070" in phone

    def test_swedish_mobile_plus46(self):
        phone = extract_phone("", "Telefon: +46 70 123 45 67")
        assert phone is not None
        assert "46" in phone or "70" in phone

    def test_swedish_landline(self):
        phone = extract_phone("", "Nå mig på 018-12 34 56 på dagtid.")
        assert phone is not None
        assert "018" in phone

    def test_no_phone_returns_none(self):
        phone = extract_phone("Offertfråga", "Hej, jag undrar vad det kostar.")
        assert phone is None


class TestCustomerTypeDetection:
    def test_brf_customer_type(self):
        analysis = analyze_lead(_input(
            "BRF installation",
            "Vi är en bostadsrättsförening och vill installera laddboxar i garaget.",
        ))
        assert analysis.customer_type == "brf"

    def test_private_customer_villa(self):
        analysis = analyze_lead(_input(
            "Solceller till villa",
            "Vill ha offert på solceller till vår villa i Uppsala.",
        ))
        assert analysis.customer_type == "private"

    def test_company_customer(self):
        analysis = analyze_lead(_input(
            "Företag söker laddbox",
            "Hej, vi är ett aktiebolag och vill installera laddstolpar.",
        ))
        assert analysis.customer_type == "company"

    def test_lantbruk_customer_type(self):
        analysis = analyze_lead(_input(
            "Solceller till lantbruk",
            "Vi driver ett lantbruk utanför Uppsala och funderar på solceller.",
        ))
        assert analysis.customer_type in ("private", "company")


class TestOrgNumberExtraction:
    def test_org_number_standard_format(self):
        result = extract_org_number("", "Org.nr: 556123-4567")
        assert result == "556123-4567"

    def test_org_number_from_subject(self):
        result = extract_org_number("Faktura 556789-0123", "")
        assert result == "556789-0123"

    def test_no_org_number(self):
        result = extract_org_number("Hej", "Bara ett vanligt mejl.")
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Focus 4 — Lead qualification (completeness, missing fields, next action)
# ══════════════════════════════════════════════════════════════════════════════

class TestLeadQualification:
    def test_complete_lead_has_high_completeness(self):
        data = _input(
            "Offert laddbox",
            "Vill ha offert på laddbox till villa på Solvägen 12, 753 20 Uppsala. "
            "Ring mig på 070-123 45 67.",
            email="anna@example.com",
        )
        analysis = analyze_lead(data)
        missing = compute_missing_info(analysis.lead_type, data, entities={"address": "Solvägen 12", "city": "Uppsala"})
        assert "address" not in missing.missing_fields

    def test_incomplete_lead_missing_address(self):
        data = _input("Offert laddbox", "Vill ha offert på laddbox.")
        analysis = analyze_lead(data)
        missing = compute_missing_info(analysis.lead_type, data, entities={})
        assert "address" in missing.missing_fields

    def test_incomplete_lead_leads_to_ask_questions(self):
        data = _input("Offert laddbox", "Vill ha offert på laddbox.")
        analysis = analyze_lead(data)
        missing = compute_missing_info(analysis.lead_type, data, entities={})
        score = score_lead(analysis, missing, {}, data)
        action = decide_next_action(score, missing)
        assert action == "ask_questions"

    def test_address_in_text_satisfies_address_field(self):
        """If a Swedish street address appears in the text, 'address' should not be missing."""
        data = _input(
            "Offert laddbox",
            "Adressen är Solvägen 12, 753 20 Uppsala. Ring 070-111 22 33.",
        )
        analysis = analyze_lead(data)
        missing = compute_missing_info(analysis.lead_type, data, entities={})
        assert "address" not in missing.missing_fields

    def test_lead_completeness_score_improves_with_data(self):
        minimal = _input("Offert", "Vill ha offert.", email="x@y.com")
        rich = _input(
            "Offert laddbox",
            "Villa på Solvägen 12, 753 20 Uppsala. Har 16A säkring. "
            "Behöver 2 laddboxar. Ring 070-123 45 67.",
            email="kund@example.com",
        )
        analysis = analyze_lead(rich)
        m_minimal = compute_missing_info("ev_charger", minimal, entities={})
        m_rich = compute_missing_info("ev_charger", rich, entities={"address": "Solvägen 12", "city": "Uppsala"})
        assert m_rich.completeness_score > m_minimal.completeness_score


# ══════════════════════════════════════════════════════════════════════════════
# Focus 5 — Support qualification
# ══════════════════════════════════════════════════════════════════════════════

class TestSupportQualification:
    def test_jordfelsbrytare_classified_as_issue(self):
        data = _input("Jordfelsbrytare", "Jordfelsbrytaren löser så fort vi startar laddboxen.")
        analysis = analyze_support(data)
        assert analysis.ticket_type == "issue"

    def test_solar_no_production_classified_as_issue(self):
        data = _input("Solceller", "Växelriktaren visar felkod och solcellerna producerar inget.")
        analysis = analyze_support(data)
        assert analysis.ticket_type == "issue"
        assert analysis.urgency in ("high", "critical")

    def test_bränt_luktar_is_critical_safety(self):
        data = _input("Bränt lukt", "Det luktar bränt från elcentralen, lite rök.")
        analysis = analyze_support(data)
        assert analysis.urgency == "critical"
        assert analysis.requires_human is True

    def test_warranty_claim_from_previous_installation(self):
        data = _input("Garanti", "Ni installerade hos oss förra året och nu fungerar inget.")
        analysis = analyze_support(data)
        assert analysis.ticket_type == "warranty"
        assert analysis.requires_human is True

    def test_safety_risk_triggers_manual_review(self):
        data = {"subject": "Brandrisk", "message_text": "Det luktar bränt och det gnistrar från elcentralen."}
        risk = assess_content_risk(data)
        assert risk["risk_detected"] is True
        assert "safety_risk" in risk["categories"]
        assert risk["needs_human"] is True

    def test_angry_customer_complaint_requires_human(self):
        data = _input("Klagomål", "Skandal! Jag är rasande. Ni har gjort ett oacceptabelt arbete!")
        analysis = analyze_support(data)
        assert analysis.requires_human is True
        assert analysis.customer_sentiment in ("angry",)

    def test_recurring_fault_detected(self):
        data = _input(
            "Tredje gången",
            "Det här är tredje gången jag kontaktar er om samma problem.",
        )
        analysis = analyze_support(data)
        assert analysis.customer_sentiment in ("frustrated", "angry")
        assert analysis.requires_human is True

    def test_gnistor_classified_as_critical(self):
        data = _input("Gnistor", "Gnistrar kraftigt vid proppskåpet.")
        analysis = analyze_support(data)
        assert analysis.urgency == "critical"


# ══════════════════════════════════════════════════════════════════════════════
# Focus 6 — Invoice / economy fields
# ══════════════════════════════════════════════════════════════════════════════

class TestInvoiceFields:
    def test_extract_amount_swedish(self):
        amt = extract_invoice_amount("Faktura", "Fakturan avser 15 500 kr exkl. moms.")
        assert amt is not None
        assert "15 500" in amt or "15500" in amt

    def test_extract_invoice_number(self):
        inv = extract_invoice_number("Fakturanummer: INV-2026-001", "")
        assert inv == "INV-2026-001"

    def test_extract_due_date(self):
        d = extract_due_date("", "Förfallodatum 2026-08-15.")
        assert d == "2026-08-15"

    def test_extract_ocr_number(self):
        ocr = extract_ocr_number("", "OCR-nummer: 123456789012")
        assert ocr is not None
        assert "123456789012" in ocr

    def test_extract_ocr_with_spaces(self):
        ocr = extract_ocr_number("", "Betalningsref (OCR): 1234 5678 90")
        assert ocr is not None

    def test_inkasso_is_high_risk(self):
        level = detect_invoice_risk_level("Inkasso", "Ditt ärende har lämnats till inkasso.")
        assert level == "high_risk"

    def test_kronofogden_is_high_risk(self):
        level = detect_invoice_risk_level("", "Om ej betalat inom 7 dagar skickas ärendet till Kronofogden.")
        assert level == "high_risk"

    def test_betalningspåminnelse_is_medium_risk(self):
        level = detect_invoice_risk_level("Betalningspåminnelse", "Vi påminner om obetald faktura.")
        assert level == "medium_risk"

    def test_normal_invoice_is_normal_risk(self):
        level = detect_invoice_risk_level("Faktura 2026-07", "Bifogat återfinns faktura för utfört arbete.")
        assert level == "normal"

    def test_inkasso_triggers_safety_risk_in_intelligence(self):
        data = {"subject": "Inkasso", "message_text": "Ärendet har skickats till inkasso."}
        risk = assess_content_risk(data)
        assert risk["risk_detected"] is True
        assert "debt_collection" in risk["categories"]

    def test_kreditera_triggers_financial_change_risk(self):
        data = {"subject": "Kreditnota", "message_text": "Kreditera fakturan och makulera faktura 1234."}
        risk = assess_content_risk(data)
        assert risk["risk_detected"] is True
        assert "financial_change" in risk["categories"]


# ══════════════════════════════════════════════════════════════════════════════
# Focus 7 — Tenant / routing hints
# ══════════════════════════════════════════════════════════════════════════════

class TestRoutingHints:
    def test_safety_routes_to_manual_review(self):
        data = {"subject": "Säkerhetsrisk", "message_text": "Livsfarligt elarbete utfört av er tekniker."}
        risk = assess_content_risk(data)
        assert risk["route_to"] == "manual_review"

    def test_normal_lead_no_risk_route(self):
        data = {"subject": "Offert laddbox", "message_text": "Vill ha offert på laddbox."}
        risk = assess_content_risk(data)
        assert risk["risk_detected"] is False
        assert risk["route_to"] is None

    def test_debt_collection_routes_to_manual_review(self):
        data = {"subject": "Kravbrev", "message_text": "Kravbrev för obetald faktura."}
        risk = assess_content_risk(data)
        assert risk["route_to"] == "manual_review"

    def test_legal_threat_routes_to_manual_review(self):
        data = {"subject": "Juridisk åtgärd", "message_text": "Vi tar juridiskt ansvar och anmäler detta."}
        risk = assess_content_risk(data)
        assert risk["route_to"] == "manual_review"


# ══════════════════════════════════════════════════════════════════════════════
# Focus 8 — Missing fields reporting
# ══════════════════════════════════════════════════════════════════════════════

class TestMissingFieldsReporting:
    def test_ev_charger_without_address_flags_address(self):
        data = _input("Laddbox", "Vill ha laddbox, bor i villa.")
        missing = compute_missing_info("ev_charger", data, entities={})
        assert "address" in missing.missing_fields

    def test_ev_charger_without_fuse_flags_main_fuse(self):
        data = _input("Laddbox", "Adress: Solvägen 12. Behöver 1 laddbox.")
        missing = compute_missing_info("ev_charger", data, entities={"address": "Solvägen 12"})
        assert "main_fuse" in missing.missing_fields

    def test_solar_without_consumption_flags_annual_consumption(self):
        data = _input("Solceller", "Vill ha solceller på villan på Solvägen 12.")
        missing = compute_missing_info(
            "solar_installation", data, entities={"address": "Solvägen 12"}
        )
        assert "annual_consumption" in missing.missing_fields

    def test_present_fields_reported_correctly(self):
        data = _input(
            "Laddbox",
            "Villa på Solvägen 12, 753 20 Uppsala. Har 20A säkring. "
            "Behöver 1 laddbox. Vill installera i mars.",
        )
        missing = compute_missing_info(
            "ev_charger", data, entities={"address": "Solvägen 12", "city": "Uppsala"}
        )
        assert "address" not in missing.missing_fields
        assert "main_fuse" not in missing.missing_fields

    def test_completeness_score_is_zero_to_one(self):
        data = _input("Test", "")
        missing = compute_missing_info("ev_charger", data, entities={})
        assert 0.0 <= missing.completeness_score <= 1.0

    def test_unknown_lead_type_uses_fallback_schema(self):
        data = _input("Okänt ärende", "Behöver hjälp med något.")
        missing = compute_missing_info("unknown", data, entities={})
        assert isinstance(missing.missing_fields, list)
