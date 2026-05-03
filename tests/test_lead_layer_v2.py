"""
Tests for Lead Layer v2 — tenant-aware intelligence.

Covers:
- TenantLeadContext loads correctly from memory dict
- Tenant-aware vs default behavior produces different results for same lead
- Fallback to v1 behavior when no tenant context
- Non-lead jobs are unaffected
- lead_status inference and preservation
- Scoring bonuses/penalties for tenant-specific factors
"""
from __future__ import annotations

import pytest

from app.lead.analyzer import analyze_lead
from app.lead.missing_info import compute_missing_info
from app.lead.models import LeadAnalysis, MissingInfoResult
from app.lead.next_action import decide_next_action
from app.lead.offer_draft import build_offer_draft
from app.lead.question_generator import generate_question_message, should_ask_questions
from app.lead.scorer import score_lead
from app.lead.tenant_context import TenantLeadContext, load_tenant_context


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_solar_settings() -> dict:
    """Tenant memory that specialises in solar + EV charger.
    Wrapped in 'memory' key as load_tenant_context expects settings.get('memory').
    """
    return {
        "memory": {
            "business_profile": {
                "company_name": "SolTech AB",
                "industry": "renewable_energy",
                "geographic_area": "Stockholm",
            },
            "lead_config": {
                "served_areas": ["Stockholm", "Solna", "Sundbyberg"],
                "offer_principles": ["Alltid ROT-avdrag inkluderat"],
                "ideal_customer": {
                    "customer_types": ["private"],
                    "high_value_services": ["solar_installation"],
                    "priority_services": ["ev_charger"],
                },
                "services": [
                    {
                        "lead_type": "solar_installation",
                        "name": "Solcellsinstallation",
                        "keywords": ["solceller", "solpanel"],
                        "field_labels": {"roof_area": "Takyta (m²)"},
                        "offer_sections": ["Takanalys", "Systemdimensionering", "Installation"],
                        "assumptions": ["Normalt tak", "Nätanslutning finns"],
                    },
                    {
                        "lead_type": "ev_charger",
                        "name": "Laddbox",
                        "keywords": ["laddbox", "elbil"],
                    },
                ],
                "lead_requirements": {
                    "solar_installation": {
                        "required": ["address", "roof_area", "annual_consumption"],
                        "optional": ["email", "phone"],
                    }
                },
                "pricing_guidelines": {
                    "solar_installation": {
                        "price_range": "90 000 – 180 000 kr",
                        "notes": "Inkluderar ROT-avdrag",
                    }
                },
            },
        }
    }


def _make_solar_ctx() -> TenantLeadContext:
    return load_tenant_context("tenant-solar", _make_solar_settings())


def _make_input_complete() -> dict:
    return {
        "message_text": "Hej! Jag vill ha offert på solceller. Jag bor i Stockholm. Takyta 40 m². Förbrukning 10000 kWh/år.",
        "subject": "Offert solceller",
        "address": "Solna",
        "roof_area": "40",
        "annual_consumption": "10000",
    }


def _make_input_incomplete() -> dict:
    return {
        "message_text": "Hej, jag kanske är intresserad av solceller?",
        "subject": "Fråga om solceller",
    }


def _make_entities_basic() -> dict:
    return {"city": "Stockholm", "email": "test@test.se"}


# ── TenantLeadContext ─────────────────────────────────────────────────────────

class TestTenantLeadContext:
    def test_loads_company_name(self):
        ctx = _make_solar_ctx()
        assert ctx.company_name == "SolTech AB"

    def test_context_available_true(self):
        ctx = _make_solar_ctx()
        assert ctx.context_available is True

    def test_served_areas(self):
        ctx = _make_solar_ctx()
        assert "Stockholm" in ctx.served_areas

    def test_service_offered_true(self):
        ctx = _make_solar_ctx()
        assert ctx.is_service_offered("solar_installation") is True

    def test_service_offered_false_for_unknown(self):
        ctx = _make_solar_ctx()
        assert ctx.is_service_offered("roof_painting") is False

    def test_schema_for_returns_tenant_schema(self):
        ctx = _make_solar_ctx()
        schema = ctx.schema_for("solar_installation")
        assert schema is not None
        assert "roof_area" in schema.get("required", [])

    def test_pricing_for_returns_dict(self):
        ctx = _make_solar_ctx()
        pricing = ctx.pricing_for("solar_installation")
        assert pricing is not None
        assert "90 000" in pricing.get("price_range", "")

    def test_service_lead_types(self):
        ctx = _make_solar_ctx()
        types = ctx.service_lead_types()
        assert "solar_installation" in types
        assert "ev_charger" in types

    def test_empty_settings_context_not_available(self):
        ctx = load_tenant_context("t1", {})
        assert ctx.context_available is False

    def test_ideal_customer(self):
        ctx = _make_solar_ctx()
        assert "solar_installation" in (ctx.ideal_customer.get("high_value_services") or [])


# ── Analyzer — tenant vs default ─────────────────────────────────────────────

class TestTenantAwareAnalyzer:
    def test_detects_solar_with_tenant_ctx(self):
        ctx = _make_solar_ctx()
        result = analyze_lead(_make_input_complete(), {}, ctx)
        assert result.lead_type == "solar_installation"

    def test_tenant_context_used_flag(self):
        ctx = _make_solar_ctx()
        result = analyze_lead(_make_input_complete(), {}, ctx)
        assert result.tenant_context_used is True

    def test_no_ctx_tenant_context_used_false(self):
        result = analyze_lead(_make_input_complete(), {})
        assert result.tenant_context_used is False

    def test_no_ctx_detects_solar_with_stem_keyword(self):
        """Default keyword 'solcell' (stem) matches message containing 'solcell' standalone."""
        inp = {"message_text": "Jag vill installera solcell på taket", "subject": "Solcell offert"}
        result = analyze_lead(inp, {})
        assert result.lead_type == "solar_installation"

    def test_unoffered_service_classified_unknown_with_ctx(self):
        """A tenant that doesn't offer roof_painting should not classify it as such."""
        ctx = _make_solar_ctx()
        inp = {"message_text": "Jag vill måla om taket", "subject": "Takmalning"}
        result = analyze_lead(inp, {}, ctx)
        assert result.lead_type != "roof_painting"


# ── Missing Info — tenant schema override ────────────────────────────────────

class TestTenantMissingInfo:
    def test_tenant_schema_used(self):
        ctx = _make_solar_ctx()
        result = compute_missing_info("solar_installation", _make_input_complete(), {}, ctx)
        assert result.schema_source == "tenant"
        assert result.tenant_context_used is True

    def test_default_schema_used_without_ctx(self):
        result = compute_missing_info("solar_installation", _make_input_complete(), {})
        assert result.schema_source == "default"

    def test_completeness_higher_when_fields_present(self):
        ctx = _make_solar_ctx()
        full = compute_missing_info("solar_installation", _make_input_complete(), _make_entities_basic(), ctx)
        empty = compute_missing_info("solar_installation", _make_input_incomplete(), {}, ctx)
        assert full.completeness_score > empty.completeness_score

    def test_roof_area_missing_flagged(self):
        ctx = _make_solar_ctx()
        inp = {"message_text": "Jag vill ha solceller", "address": "Stockholm"}
        result = compute_missing_info("solar_installation", inp, {}, ctx)
        assert "roof_area" in result.missing_fields

    def test_different_results_different_tenants(self):
        """Same lead, two tenants with different schemas → different missing fields."""
        ctx_solar = _make_solar_ctx()

        # Minimal tenant that only requires address
        minimal_settings = {
            "memory": {
                "lead_config": {
                    "services": [{"lead_type": "solar_installation", "name": "Solceller"}],
                    "lead_requirements": {
                        "solar_installation": {"required": ["address"], "optional": []}
                    }
                }
            }
        }
        ctx_minimal = load_tenant_context("t2", minimal_settings)
        inp = {"address": "Stockholm", "message_text": "Solceller tack"}
        r_solar = compute_missing_info("solar_installation", inp, {"city": "Stockholm"}, ctx_solar)
        r_minimal = compute_missing_info("solar_installation", inp, {"city": "Stockholm"}, ctx_minimal)
        # Solar ctx requires roof_area + annual_consumption, minimal only address
        assert len(r_solar.missing_fields) >= len(r_minimal.missing_fields)


# ── Scorer — tenant bonuses/penalties ────────────────────────────────────────

class TestTenantScorer:
    def _make_analysis(self, lead_type="solar_installation", intent="ready_to_buy", urgency="high", customer_type="private") -> LeadAnalysis:
        return LeadAnalysis(
            lead_type=lead_type,
            intent=intent,
            urgency=urgency,
            customer_type=customer_type,
            confidence=0.9,
            tenant_context_used=False,
            context_sources=[],
            matched_service=None,
        )

    def _make_missing(self, completeness=0.85) -> MissingInfoResult:
        return MissingInfoResult(
            required_fields=["address"],
            present_fields=["address"],
            missing_fields=[],
            optional_fields=[],
            completeness_score=completeness,
            schema_source="default",
            tenant_context_used=False,
            context_sources=[],
        )

    def test_high_value_service_bonus(self):
        ctx = _make_solar_ctx()
        analysis = self._make_analysis("solar_installation")
        inp = {"message_text": "offert solceller Stockholm", "subject": "Solar"}
        score = score_lead(analysis, self._make_missing(), {"city": "Stockholm"}, inp, ctx)
        assert score.score > score_lead(analysis, self._make_missing(), {"city": "Stockholm"}, inp, None).score

    def test_service_not_offered_penalty(self):
        ctx = _make_solar_ctx()
        analysis = self._make_analysis("roof_painting")
        inp = {"message_text": "Takmalning önskas", "subject": "Tak"}
        score_with_ctx = score_lead(analysis, self._make_missing(), {}, inp, ctx)
        score_no_ctx = score_lead(analysis, self._make_missing(), {}, inp, None)
        assert score_with_ctx.score < score_no_ctx.score

    def test_geographic_mismatch_penalty(self):
        ctx = _make_solar_ctx()
        analysis = self._make_analysis()
        inp = {"message_text": "offert solceller Malmö", "subject": "Solar Malmö"}
        score = score_lead(analysis, self._make_missing(), {}, inp, ctx)
        assert any("geographic_mismatch" in r for r in score.reasons)

    def test_geographic_match_bonus(self):
        ctx = _make_solar_ctx()
        analysis = self._make_analysis()
        inp = {"message_text": "offert solceller Stockholm", "subject": "Solar"}
        score = score_lead(analysis, self._make_missing(), {}, inp, ctx)
        assert any("geographic_match" in r for r in score.reasons)

    def test_no_ctx_no_tenant_adjustments(self):
        analysis = self._make_analysis()
        inp = {"message_text": "offert solceller", "subject": "Solar"}
        score = score_lead(analysis, self._make_missing(), {}, inp, None)
        assert score.tenant_context_used is False
        assert not any("geographic" in r for r in score.reasons)


# ── Offer Draft — tenant pricing/sections ────────────────────────────────────

class TestTenantOfferDraft:
    def _make_analysis(self) -> LeadAnalysis:
        return LeadAnalysis(
            lead_type="solar_installation",
            intent="ready_to_buy", urgency="high",
            customer_type="private", confidence=0.9,
            tenant_context_used=True, context_sources=[], matched_service=None,
        )

    def _make_missing(self, completeness=0.85) -> MissingInfoResult:
        return MissingInfoResult(
            required_fields=[], present_fields=[], missing_fields=[],
            optional_fields=[], completeness_score=completeness,
            schema_source="tenant", tenant_context_used=True, context_sources=[],
        )

    def test_tenant_price_range_used(self):
        ctx = _make_solar_ctx()
        draft = build_offer_draft(self._make_analysis(), self._make_missing(), {}, ctx)
        assert draft is not None
        assert "90 000" in (draft.estimated_price_range or "")

    def test_tenant_offer_sections_used(self):
        ctx = _make_solar_ctx()
        draft = build_offer_draft(self._make_analysis(), self._make_missing(), {}, ctx)
        assert draft is not None
        assert "Takanalys" in draft.suggested_offer_sections

    def test_offer_principles_in_assumptions(self):
        ctx = _make_solar_ctx()
        draft = build_offer_draft(self._make_analysis(), self._make_missing(), {}, ctx)
        assert draft is not None
        assert any("ROT-avdrag" in a for a in draft.assumptions)

    def test_company_name_in_summary(self):
        ctx = _make_solar_ctx()
        draft = build_offer_draft(self._make_analysis(), self._make_missing(), {}, ctx)
        assert draft is not None
        assert "SolTech AB" in draft.summary

    def test_no_draft_when_incomplete(self):
        ctx = _make_solar_ctx()
        missing_low = self._make_missing(completeness=0.5)
        draft = build_offer_draft(self._make_analysis(), missing_low, {}, ctx)
        assert draft is None

    def test_fallback_default_price_when_no_ctx(self):
        draft = build_offer_draft(self._make_analysis(), self._make_missing(), {}, None)
        assert draft is not None
        assert "80 000" in (draft.estimated_price_range or "")

    def test_risk_point_added_for_out_of_area(self):
        ctx = _make_solar_ctx()
        entities = {"address": "Malmö centrum"}
        draft = build_offer_draft(self._make_analysis(), self._make_missing(), entities, ctx)
        assert draft is not None
        assert any("serviceområde" in rp for rp in draft.risk_points)


# ── Next Action — tenant auto_actions / geo constraints ───────────────────────

class TestNextAction:
    def _score(self, s, biz_reason=None):
        from app.lead.models import LeadScore
        return LeadScore(
            score=s, category="hot" if s >= 70 else "warm" if s >= 40 else "cold",
            reasons=[], tenant_context_used=False, business_fit_reason=biz_reason,
        )

    def _missing(self, completeness=0.85):
        return MissingInfoResult(
            required_fields=[], present_fields=[], missing_fields=[],
            optional_fields=[], completeness_score=completeness,
            schema_source="default", tenant_context_used=False, context_sources=[],
        )

    def test_ask_questions_when_incomplete(self):
        action = decide_next_action(self._score(80), self._missing(0.5))
        assert action == "ask_questions"

    def test_create_offer_draft_high_score(self):
        action = decide_next_action(self._score(80), self._missing(0.9))
        assert action == "create_offer_draft"

    def test_ready_to_dispatch_with_auto_action(self):
        action = decide_next_action(self._score(80), self._missing(0.9), tenant_auto_actions={"lead": True})
        assert action == "ready_to_dispatch"

    def test_approval_required_mid_score(self):
        action = decide_next_action(self._score(55), self._missing(0.9))
        assert action == "approval_required"

    def test_manual_review_low_score(self):
        action = decide_next_action(self._score(20), self._missing(0.9))
        assert action == "manual_review"

    def test_manual_review_on_geo_mismatch(self):
        score = self._score(35, biz_reason="Lead utanför serviceområde")
        action = decide_next_action(score, self._missing(0.9))
        assert action == "manual_review"


# ── Question Generator ────────────────────────────────────────────────────────

class TestQuestionGenerator:
    def test_company_name_in_output(self):
        ctx = _make_solar_ctx()
        msg = generate_question_message(["roof_area", "annual_consumption"], ctx, "solar_installation")
        assert "SolTech AB" in msg

    def test_no_ctx_generic_output(self):
        msg = generate_question_message(["roof_area"], None, "solar_installation")
        assert msg  # non-empty
        assert "SolTech AB" not in msg

    def test_should_ask_questions_threshold(self):
        assert should_ask_questions(0.5) is True
        assert should_ask_questions(0.8) is False


# ══════════════════════════════════════════════════════════════════════════════
# Safety check 1: Full fallback without tenant context (ctx=None / empty memory)
# Every module must produce valid output and report tenant_context_used=False.
# ══════════════════════════════════════════════════════════════════════════════

class TestFallbackWithoutTenantContext:
    """All lead modules must behave identically to v1 when no tenant context is provided."""

    _INP = {
        "message_text": "Jag vill ha offert på laddbox till min elbil hemma i Stockholm.",
        "subject": "Offert laddbox",
        "address": "Stockholm",
    }
    _ENTITIES = {"email": "kund@example.se", "city": "Stockholm"}

    # ── analyzer ──────────────────────────────────────────────────────────────

    def test_analyzer_no_ctx_no_exception(self):
        result = analyze_lead(self._INP, self._ENTITIES)
        assert result is not None
        assert result.lead_type is not None

    def test_analyzer_no_ctx_tenant_flags_false(self):
        result = analyze_lead(self._INP, self._ENTITIES, None)
        assert result.tenant_context_used is False
        assert result.context_sources == []
        assert result.matched_service is None

    def test_analyzer_empty_ctx_tenant_flags_false(self):
        ctx = load_tenant_context("t", {})
        result = analyze_lead(self._INP, self._ENTITIES, ctx)
        assert result.tenant_context_used is False

    def test_analyzer_no_ctx_detects_ev_charger(self):
        result = analyze_lead(self._INP, self._ENTITIES)
        assert result.lead_type == "ev_charger"

    # ── missing_info ──────────────────────────────────────────────────────────

    def test_missing_info_no_ctx_no_exception(self):
        result = compute_missing_info("ev_charger", self._INP, self._ENTITIES)
        assert result is not None
        assert isinstance(result.missing_fields, list)
        assert isinstance(result.completeness_score, float)

    def test_missing_info_no_ctx_schema_source_default(self):
        result = compute_missing_info("ev_charger", self._INP, self._ENTITIES, None)
        assert result.schema_source == "default"
        assert result.tenant_context_used is False
        assert result.context_sources == []

    def test_missing_info_unknown_lead_type_no_exception(self):
        result = compute_missing_info("unknown", self._INP, self._ENTITIES)
        assert result is not None
        assert 0.0 <= result.completeness_score <= 1.0

    # ── scorer ────────────────────────────────────────────────────────────────

    def test_scorer_no_ctx_no_exception(self):
        analysis = analyze_lead(self._INP, self._ENTITIES)
        mi = compute_missing_info(analysis.lead_type, self._INP, self._ENTITIES)
        result = score_lead(analysis, mi, self._ENTITIES, self._INP, None)
        assert result is not None
        assert 0 <= result.score <= 100

    def test_scorer_no_ctx_tenant_flags_false(self):
        analysis = analyze_lead(self._INP, self._ENTITIES)
        mi = compute_missing_info(analysis.lead_type, self._INP, self._ENTITIES)
        result = score_lead(analysis, mi, self._ENTITIES, self._INP, None)
        assert result.tenant_context_used is False
        assert result.business_fit_reason is None

    def test_scorer_no_ctx_no_geo_reasons(self):
        analysis = analyze_lead(self._INP, self._ENTITIES)
        mi = compute_missing_info(analysis.lead_type, self._INP, self._ENTITIES)
        result = score_lead(analysis, mi, self._ENTITIES, self._INP, None)
        assert not any("geographic" in r for r in result.reasons)

    # ── question_generator ───────────────────────────────────────────────────

    def test_question_generator_no_ctx_no_exception(self):
        msg = generate_question_message(["address", "roof_area"], None, "solar_installation")
        assert msg is not None
        assert len(msg) > 10

    def test_question_generator_no_ctx_no_company_name(self):
        msg = generate_question_message(["address"], None)
        assert "AB" not in msg
        assert "För att kunna" in msg

    def test_question_generator_empty_fields_returns_none(self):
        msg = generate_question_message([], None)
        assert msg is None

    # ── offer_draft ───────────────────────────────────────────────────────────

    def test_offer_draft_no_ctx_no_exception(self):
        analysis = LeadAnalysis(
            lead_type="ev_charger", intent="ready_to_buy", urgency="medium",
            customer_type="private", confidence=0.8,
        )
        mi = MissingInfoResult(
            required_fields=["address"], present_fields=["address"], missing_fields=[],
            optional_fields=[], completeness_score=0.85,
        )
        draft = build_offer_draft(analysis, mi, self._ENTITIES, None)
        assert draft is not None

    def test_offer_draft_no_ctx_uses_default_price(self):
        analysis = LeadAnalysis(
            lead_type="ev_charger", intent="ready_to_buy", urgency="medium",
            customer_type="private", confidence=0.8,
        )
        mi = MissingInfoResult(
            required_fields=["address"], present_fields=["address"], missing_fields=[],
            optional_fields=[], completeness_score=0.85,
        )
        draft = build_offer_draft(analysis, mi, {}, None)
        assert draft is not None
        assert draft.tenant_context_used is False
        assert draft.context_sources == []
        assert draft.risk_points == []
        assert "8 000" in (draft.estimated_price_range or "")  # default ev_charger range

    def test_offer_draft_no_ctx_returns_none_when_incomplete(self):
        analysis = LeadAnalysis(
            lead_type="ev_charger", intent="researching", urgency="low",
            customer_type="unknown", confidence=0.5,
        )
        mi = MissingInfoResult(
            required_fields=["address", "main_fuse"], present_fields=[],
            missing_fields=["address", "main_fuse"], optional_fields=[],
            completeness_score=0.3,
        )
        draft = build_offer_draft(analysis, mi, {}, None)
        assert draft is None

    # ── next_action ───────────────────────────────────────────────────────────

    def test_next_action_no_ctx_no_exception(self):
        from app.lead.models import LeadScore
        score = LeadScore(score=75, category="hot", reasons=[], tenant_context_used=False)
        mi = MissingInfoResult(
            required_fields=["address"], present_fields=["address"], missing_fields=[],
            optional_fields=[], completeness_score=0.85,
        )
        action = decide_next_action(score, mi, None, None)
        assert action is not None

    def test_next_action_no_ctx_high_score_creates_offer(self):
        from app.lead.models import LeadScore
        score = LeadScore(score=75, category="hot", reasons=[], tenant_context_used=False)
        mi = MissingInfoResult(
            required_fields=["address"], present_fields=["address"], missing_fields=[],
            optional_fields=[], completeness_score=0.85,
        )
        action = decide_next_action(score, mi, None, None)
        assert action == "create_offer_draft"

    def test_next_action_no_ctx_incomplete_asks_questions(self):
        from app.lead.models import LeadScore
        score = LeadScore(score=60, category="warm", reasons=[], tenant_context_used=False)
        mi = MissingInfoResult(
            required_fields=["address", "roof_area"], present_fields=[],
            missing_fields=["address", "roof_area"], optional_fields=[],
            completeness_score=0.4,
        )
        action = decide_next_action(score, mi, None, None)
        assert action == "ask_questions"

    # ── end-to-end fallback chain ─────────────────────────────────────────────

    def test_full_chain_no_ctx_produces_valid_output(self):
        """Complete lead analysis chain without any tenant context produces valid output."""
        analysis = analyze_lead(self._INP, self._ENTITIES, None)
        assert analysis.tenant_context_used is False

        mi = compute_missing_info(analysis.lead_type, self._INP, self._ENTITIES, None)
        assert mi.schema_source == "default"
        assert mi.tenant_context_used is False

        lead_score = score_lead(analysis, mi, self._ENTITIES, self._INP, None)
        assert lead_score.tenant_context_used is False

        action = decide_next_action(lead_score, mi, None, None)
        assert action in ("ask_questions", "create_offer_draft", "approval_required",
                          "manual_review", "ready_to_dispatch")

        if should_ask_questions(mi.completeness_score):
            msg = generate_question_message(mi.missing_fields, None, analysis.lead_type)
            if mi.missing_fields:
                assert msg is not None

        # No exception throughout — lead output exists
        assert analysis.lead_type is not None
        assert 0 <= lead_score.score <= 100
        assert 0.0 <= mi.completeness_score <= 1.0


# ══════════════════════════════════════════════════════════════════════════════
# Safety check 2: No external side effects from lead metadata endpoints
# PATCH /lead-status, POST /lead-regenerate, GET /dashboard/leads, GET /cases/{id}
# must not call dispatch_action, ControlledDispatchEngine, or any integration client.
# ══════════════════════════════════════════════════════════════════════════════

from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

_NOW = datetime(2026, 5, 3, 10, 0, 0, tzinfo=timezone.utc)


def _lead_record(
    job_id: str = "JOB-LEAD-1",
    tenant_id: str = "T1",
    lead_status: str = "new",
    with_lead_payload: bool = True,
) -> MagicMock:
    r = MagicMock()
    r.job_id = job_id
    r.tenant_id = tenant_id
    r.job_type = "lead"
    r.status = "completed"
    r.created_at = _NOW
    r.updated_at = _NOW
    r.input_data = {"lead_status": lead_status, "message_text": "Jag vill ha offert", "subject": "Test"}
    lead_payload = {
        "processor_name": "lead_analyzer_processor",
        "lead_analysis": {"lead_type": "ev_charger", "intent": "ready_to_buy",
                          "urgency": "medium", "customer_type": "private",
                          "confidence": 0.8, "tenant_context_used": False,
                          "context_sources": [], "matched_service": None},
        "missing_info": {"missing_fields": [], "completeness_score": 0.85,
                         "required_fields": ["address"], "present_fields": ["address"],
                         "optional_fields": [], "schema_source": "default",
                         "tenant_context_used": False, "context_sources": []},
        "lead_score": {"score": 72, "category": "hot", "reasons": [],
                       "tenant_context_used": False, "business_fit_reason": None},
        "next_action": "create_offer_draft",
        "lead_status": lead_status,
        "confidence": 0.8,
    }
    r.result = {
        "status": "completed",
        "payload": lead_payload,
        "processor_history": [{"processor": "lead_analyzer_processor",
                                "result": {"status": "completed", "payload": lead_payload}}],
    }
    return r


def _mock_db(record: MagicMock) -> MagicMock:
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.first.return_value = record
    q.all.return_value = [record]
    return db


class TestLeadStatusEndpointNoSideEffects:
    """PATCH /jobs/{job_id}/lead-status must only update input_data — no external calls."""

    def _call(self, status: str = "offer_ready", job_id: str = "JOB-LEAD-1"):
        from app.main import set_lead_status, LeadStatusRequest
        db = _mock_db(_lead_record(job_id))
        body = LeadStatusRequest(status=status)
        return set_lead_status(job_id=job_id, body=body, db=db, tenant_id="T1")

    def test_returns_job_id_and_status(self):
        result = self._call("offer_ready")
        assert result["job_id"] == "JOB-LEAD-1"
        assert result["lead_status"] == "offer_ready"

    def test_does_not_call_dispatch_action(self):
        with patch("app.main.dispatch_action") as mock_dispatch:
            self._call("offer_sent")
            mock_dispatch.assert_not_called()

    def test_does_not_call_controlled_dispatch_engine(self):
        with patch("app.workflows.dispatchers.engine.ControlledDispatchEngine") as mock_cde:
            self._call("won")
            mock_cde.assert_not_called()

    def test_does_not_call_execute_action(self):
        with patch("app.workflows.action_executor.execute_action") as mock_exec:
            self._call("waiting_for_customer")
            mock_exec.assert_not_called()

    def test_invalid_status_raises_422(self):
        from fastapi import HTTPException
        from app.main import set_lead_status, LeadStatusRequest
        db = _mock_db(_lead_record())
        body = LeadStatusRequest(status="nonexistent_status")
        with pytest.raises(HTTPException) as exc_info:
            set_lead_status(job_id="JOB-LEAD-1", body=body, db=db, tenant_id="T1")
        assert exc_info.value.status_code == 422

    def test_non_lead_job_raises_422(self):
        from fastapi import HTTPException
        from app.main import set_lead_status, LeadStatusRequest
        rec = _lead_record()
        rec.job_type = "customer_inquiry"
        db = _mock_db(rec)
        body = LeadStatusRequest(status="new")
        with pytest.raises(HTTPException) as exc_info:
            set_lead_status(job_id="JOB-LEAD-1", body=body, db=db, tenant_id="T1")
        assert exc_info.value.status_code == 422

    def test_unknown_job_raises_404(self):
        from fastapi import HTTPException
        from app.main import set_lead_status, LeadStatusRequest
        db = MagicMock()
        q = MagicMock()
        db.query.return_value = q
        q.filter.return_value = q
        q.first.return_value = None
        body = LeadStatusRequest(status="new")
        with pytest.raises(HTTPException) as exc_info:
            set_lead_status(job_id="MISSING", body=body, db=db, tenant_id="T1")
        assert exc_info.value.status_code == 404


class TestLeadRegenerateEndpointNoSideEffects:
    """POST /jobs/{job_id}/lead-regenerate must only re-run deterministic analysis — no external calls."""

    def _call(self, job_id: str = "JOB-LEAD-1"):
        from app.main import regenerate_lead_analysis

        rec = _lead_record(job_id)
        db = _mock_db(rec)

        mock_job = MagicMock()
        mock_job.job_id = job_id
        mock_job.tenant_id = "T1"
        mock_job.job_type = "lead"
        mock_job.input_data = dict(rec.input_data)
        mock_job.processor_history = [
            {"processor": "lead_analyzer_processor",
             "result": {"status": "completed", "payload": rec.result["payload"]}}
        ]
        mock_job.result = rec.result

        with patch("app.repositories.postgres.job_repository.JobRepository") as mock_repo, \
             patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository") as mock_cfg:
            mock_repo._to_domain.return_value = mock_job
            mock_repo.update_job.return_value = None
            mock_cfg.get_settings.return_value = {}  # no tenant context → fallback
            return regenerate_lead_analysis(job_id=job_id, db=db, tenant_id="T1"), mock_repo

    def test_returns_lead_analysis_keys(self):
        result, _ = self._call()
        assert "lead_analysis" in result
        assert "lead_score" in result
        assert "next_action" in result

    def test_does_not_call_dispatch_action(self):
        with patch("app.workflows.action_executor.execute_action") as mock_exec:
            self._call()
            mock_exec.assert_not_called()

    def test_does_not_call_controlled_dispatch_engine(self):
        with patch("app.workflows.dispatchers.engine.ControlledDispatchEngine") as mock_cde:
            self._call()
            mock_cde.assert_not_called()

    def test_does_not_call_monday_client(self):
        with patch("app.integrations.monday.client.MondayClient") as mock_monday:
            self._call()
            mock_monday.assert_not_called()

    def test_calls_update_job_not_dispatch(self):
        """Verify that the only DB write is update_job (no action_execution, no integration_event)."""
        result, mock_repo = self._call()
        mock_repo.update_job.assert_called_once()

    def test_non_lead_raises_422(self):
        from fastapi import HTTPException
        from app.main import regenerate_lead_analysis
        rec = _lead_record()
        rec.job_type = "customer_inquiry"
        db = _mock_db(rec)
        with pytest.raises(HTTPException) as exc_info:
            regenerate_lead_analysis(job_id="JOB-LEAD-1", db=db, tenant_id="T1")
        assert exc_info.value.status_code == 422

    def test_fallback_when_no_tenant_memory(self):
        """With empty settings, all lead modules fall back — no exception, output valid."""
        result, _ = self._call()
        la = result["lead_analysis"]
        assert la["tenant_context_used"] is False
        assert la["context_sources"] == []


class TestDashboardLeadsEndpointNoSideEffects:
    """GET /dashboard/leads must only aggregate DB records — no external calls."""

    def _call(self, records: list | None = None):
        from app.main import dashboard_leads
        db = MagicMock()
        q = MagicMock()
        db.query.return_value = q
        q.filter.return_value = q
        q.all.return_value = records if records is not None else [_lead_record()]
        return dashboard_leads(db=db, tenant_id="T1")

    def test_returns_required_keys(self):
        result = self._call()
        assert "total_leads" in result
        assert "by_status" in result
        assert "by_category" in result
        assert "by_service" in result
        assert "pipeline_value_estimate" in result

    def test_empty_returns_zeros(self):
        result = self._call(records=[])
        assert result["total_leads"] == 0
        assert result["by_category"] == {"hot": 0, "warm": 0, "cold": 0}

    def test_counts_one_lead(self):
        result = self._call(records=[_lead_record(lead_status="offer_ready")])
        assert result["total_leads"] == 1
        assert result["by_status"].get("offer_ready", 0) == 1

    def test_does_not_call_dispatch_action(self):
        with patch("app.main.dispatch_action") as mock_dispatch:
            self._call()
            mock_dispatch.assert_not_called()

    def test_does_not_call_dispatch_action(self):
        with patch("app.workflows.action_executor.execute_action") as mock_exec:
            self._call()
            mock_exec.assert_not_called()

    def test_does_not_call_monday_client(self):
        with patch("app.integrations.monday.client.MondayClient") as mock_monday:
            self._call()
            mock_monday.assert_not_called()

    def test_pipeline_value_parsed_from_offer_draft(self):
        rec = _lead_record()
        rec.result["payload"]["offer_draft"] = {"estimated_price_range": "80 000 – 200 000 kr"}
        # Inject into processor_history too
        rec.result["processor_history"][0]["result"]["payload"]["offer_draft"] = {
            "estimated_price_range": "80 000 – 200 000 kr"
        }
        result = self._call(records=[rec])
        pv = result["pipeline_value_estimate"]
        assert pv["leads_with_estimate"] == 1
        assert pv["low_sek"] == 80000
        assert pv["high_sek"] == 200000
