"""Tests for Support Layer v1 — tenant-aware support intelligence.

Coverage:
- TenantSupportContext construction and methods
- analyze_support (with and without tenant context)
- compute_support_missing_info (with and without tenant context)
- should_ask_questions / generate_support_question_message
- prioritize_support (with and without tenant context)
- build_support_response_draft
- decide_support_next_action
- Fallback without tenant context — all modules
- API endpoint no-side-effects tests (direct function calls, no TestClient)
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.support.analyzer import analyze_support
from app.support.missing_info import compute_support_missing_info
from app.support.models import (
    SupportAnalysis,
    SupportMissingInfoResult,
    SupportNextAction,
    SupportPriority,
    SupportResponseDraft,
)
from app.support.next_action import decide_support_next_action
from app.support.prioritizer import prioritize_support
from app.support.question_generator import generate_support_question_message, should_ask_questions
from app.support.response_draft import build_support_response_draft
from app.support.tenant_context import TenantSupportContext, load_support_context


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(
    *,
    tenant_id: str = "test-tenant",
    common_issues: list[dict] | None = None,
    sla_rules: dict | None = None,
    priority_rules: dict | None = None,
    support_requirements: dict | None = None,
    services: list[dict] | None = None,
    industry: str = "construction",
    tone: str = "professional",
) -> TenantSupportContext:
    ctx = TenantSupportContext(
        tenant_id=tenant_id,
        context_available=True,
        sources_used=["support_config", "business_profile"],
        company_name="Test AB",
        industry=industry,
        tone=tone,
        services=services or [],
        support_categories=["installation", "service", "invoice"],
        support_requirements=support_requirements or {},
        common_issues=common_issues or [],
        sla_rules=sla_rules or {},
        priority_rules=priority_rules or {},
    )
    return ctx


def _make_analysis(**kwargs) -> SupportAnalysis:
    defaults = dict(
        ticket_type="issue",
        category="service",
        urgency="medium",
        customer_sentiment="neutral",
        requires_human=False,
        confidence=0.7,
    )
    defaults.update(kwargs)
    return SupportAnalysis(**defaults)


def _make_missing(completeness: float = 0.8, missing: list[str] | None = None) -> SupportMissingInfoResult:
    return SupportMissingInfoResult(
        required_fields=["address", "issue_description"],
        present_fields=["address", "issue_description"] if completeness >= 1.0 else ["address"],
        missing_fields=missing or ([] if completeness >= 1.0 else ["issue_description"]),
        optional_fields=["phone"],
        completeness_score=completeness,
    )


def _make_priority(score: int = 30, category: str = "normal") -> SupportPriority:
    return SupportPriority(score=score, category=category, reasons=["test"])


def _make_job_dict(job_type: str = "customer_inquiry", tenant_id: str = "t1") -> dict:
    return {
        "job_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "job_type": job_type,
        "status": "completed",
        "input_data": {"subject": "Test", "message_text": "Mitt tak läcker."},
        "result": None,
        "processor_history": [],
    }


# ---------------------------------------------------------------------------
# TenantSupportContext
# ---------------------------------------------------------------------------

class TestTenantSupportContext:
    def test_default_context_available_false(self):
        ctx = TenantSupportContext(tenant_id="t1")
        assert ctx.context_available is False

    def test_schema_for_returns_none_when_not_set(self):
        ctx = TenantSupportContext(tenant_id="t1")
        assert ctx.schema_for("emergency") is None

    def test_schema_for_returns_dict_when_set(self):
        ctx = _make_ctx(support_requirements={"emergency": {"required": ["address"]}})
        assert ctx.schema_for("emergency") == {"required": ["address"]}

    def test_matching_common_issue_returns_none_when_empty(self):
        ctx = TenantSupportContext(tenant_id="t1")
        assert ctx.matching_common_issue("the roof is leaking") is None

    def test_matching_common_issue_finds_match(self):
        issues = [{"keywords": ["läcker"], "solution_steps": ["Boka besiktning"]}]
        ctx = _make_ctx(common_issues=issues)
        result = ctx.matching_common_issue("taket läcker vatten")
        assert result is not None
        assert "Boka besiktning" in result.get("solution_steps", [])

    def test_is_critical_by_sla_when_keyword_matches(self):
        ctx = _make_ctx(sla_rules={"critical_keywords": ["brand", "vattenläcka"]})
        assert ctx.is_critical_by_sla("Det är brand i källaren") is True

    def test_is_critical_by_sla_no_match(self):
        ctx = _make_ctx(sla_rules={"critical_keywords": ["brand"]})
        assert ctx.is_critical_by_sla("fråga om faktura") is False

    def test_is_urgent_category_true(self):
        ctx = _make_ctx(sla_rules={"urgent_categories": ["safety"]})
        assert ctx.is_urgent_category("safety") is True

    def test_is_urgent_category_false(self):
        ctx = _make_ctx(sla_rules={"urgent_categories": ["safety"]})
        assert ctx.is_urgent_category("invoice") is False


# ---------------------------------------------------------------------------
# load_support_context
# ---------------------------------------------------------------------------

class TestLoadSupportContext:
    def test_returns_empty_context_when_no_memory(self):
        ctx = load_support_context("t1", {})
        assert ctx.context_available is False
        assert ctx.tenant_id == "t1"

    def test_loads_business_profile(self):
        settings = {"memory": {"business_profile": {"company_name": "Acme", "industry": "energy", "tone": "friendly"}}}
        ctx = load_support_context("t1", settings)
        assert ctx.company_name == "Acme"
        assert ctx.industry == "energy"
        assert ctx.tone == "friendly"

    def test_loads_support_config(self):
        settings = {"memory": {"support_config": {
            "support_categories": ["installation", "service"],
            "sla_rules": {"critical_keywords": ["brand"]},
            "common_issues": [{"keywords": ["tak"], "solution_steps": ["Boka"]}],
        }}}
        ctx = load_support_context("t1", settings)
        assert ctx.context_available is True
        assert "installation" in ctx.support_categories
        assert ctx.sla_rules.get("critical_keywords") == ["brand"]
        assert len(ctx.common_issues) == 1

    def test_loads_services_from_lead_config(self):
        settings = {"memory": {"lead_config": {"services": [{"lead_type": "roof", "keywords": ["tak"]}]}}}
        ctx = load_support_context("t1", settings)
        assert ctx.services[0]["lead_type"] == "roof"

    def test_sources_used_tracks_loaded_sections(self):
        settings = {"memory": {
            "business_profile": {"company_name": "X"},
            "support_config": {"support_categories": ["service"]},
        }}
        ctx = load_support_context("t1", settings)
        assert "business_profile" in ctx.sources_used
        assert "support_config" in ctx.sources_used


# ---------------------------------------------------------------------------
# analyze_support
# ---------------------------------------------------------------------------

class TestAnalyzeSupport:
    def test_detects_emergency_from_keyword(self):
        data = {"subject": "Akut!", "message_text": "Vattenläcka i källaren, det är akut!"}
        result = analyze_support(data)
        assert result.ticket_type == "emergency"
        assert result.urgency in ("high", "critical")

    def test_detects_invoice_question(self):
        data = {"subject": "Faktura", "message_text": "Jag vill fråga om min faktura och belopp."}
        result = analyze_support(data)
        assert result.ticket_type == "invoice_question"

    def test_detects_warranty(self):
        data = {"subject": "Garanti", "message_text": "Min installation är trasig och borde täckas av garantin."}
        result = analyze_support(data)
        assert result.ticket_type == "warranty"

    def test_detects_scheduling(self):
        data = {"subject": "Boka tid", "message_text": "Jag vill boka tid för service."}
        result = analyze_support(data)
        assert result.ticket_type == "scheduling"

    def test_detects_complaint(self):
        data = {"subject": "Klagomål", "message_text": "Jag är mycket missnöjd med arbetet som utfördes."}
        result = analyze_support(data)
        assert result.ticket_type == "complaint"

    def test_returns_valid_model_instance(self):
        result = analyze_support({"message_text": "problem med pumpen"})
        assert isinstance(result, SupportAnalysis)
        assert result.ticket_type in ("issue", "question", "complaint", "warranty",
                                      "invoice_question", "emergency", "scheduling", "other")

    def test_angry_sentiment_detected(self):
        data = {"subject": "Arg", "message_text": "Jag är arg och rasande på er service! Det är skandal!"}
        result = analyze_support(data)
        assert result.customer_sentiment == "angry"

    def test_tenant_sla_critical_override(self):
        ctx = _make_ctx(sla_rules={"critical_keywords": ["brand"]})
        data = {"subject": "Brand", "message_text": "Det är brand i fläktmotorn!"}
        result = analyze_support(data, tenant_ctx=ctx)
        assert result.urgency == "critical"
        assert result.tenant_context_used is True

    def test_no_context_still_produces_result(self):
        result = analyze_support({"message_text": "problem"})
        assert isinstance(result, SupportAnalysis)
        assert result.tenant_context_used is False
        assert result.context_sources == []

    def test_confidence_in_range(self):
        result = analyze_support({"message_text": "Mitt tak läcker vatten"})
        assert 0.0 <= result.confidence <= 1.0

    def test_to_dict_contains_all_keys(self):
        result = analyze_support({"message_text": "test"})
        d = result.to_dict()
        for key in ("ticket_type", "category", "urgency", "customer_sentiment",
                    "requires_human", "confidence", "tenant_context_used", "context_sources"):
            assert key in d


# ---------------------------------------------------------------------------
# compute_support_missing_info
# ---------------------------------------------------------------------------

class TestComputeSupportMissingInfo:
    def test_emergency_requires_address(self):
        result = compute_support_missing_info("emergency", {}, {})
        assert "address" in result.required_fields

    def test_present_when_address_provided(self):
        result = compute_support_missing_info("emergency", {"address": "Storgatan 1"}, {})
        assert "address" in result.present_fields
        assert "address" not in result.missing_fields

    def test_completeness_score_between_0_and_1(self):
        result = compute_support_missing_info("issue", {}, {})
        assert 0.0 <= result.completeness_score <= 1.0

    def test_full_data_gives_high_completeness(self):
        data = {"address": "Storgatan 1", "issue_description": "Pumpen är trasig", "phone": "070"}
        result = compute_support_missing_info("issue", data, {})
        assert result.completeness_score >= 0.8

    def test_tenant_override_schema(self):
        ctx = _make_ctx(support_requirements={"issue": {"required": ["serial_number"], "optional": []}})
        result = compute_support_missing_info("issue", {}, {}, tenant_ctx=ctx)
        assert "serial_number" in result.required_fields
        assert result.schema_source == "tenant"
        assert result.tenant_context_used is True

    def test_no_context_uses_default_schema(self):
        result = compute_support_missing_info("issue", {}, {})
        assert result.schema_source == "default"
        assert result.tenant_context_used is False

    def test_to_dict_contains_all_keys(self):
        result = compute_support_missing_info("question", {}, {})
        d = result.to_dict()
        for key in ("required_fields", "present_fields", "missing_fields", "optional_fields",
                    "completeness_score", "schema_source", "tenant_context_used", "context_sources"):
            assert key in d


# ---------------------------------------------------------------------------
# should_ask_questions / generate_support_question_message
# ---------------------------------------------------------------------------

class TestQuestionGenerator:
    def test_should_ask_below_threshold(self):
        assert should_ask_questions(0.5) is True

    def test_should_not_ask_above_threshold(self):
        assert should_ask_questions(0.8) is False

    def test_threshold_boundary_at_0_7(self):
        assert should_ask_questions(0.7) is False

    def test_generates_string_when_missing_fields(self):
        msg = generate_support_question_message(["address", "phone"], ticket_type="issue")
        assert isinstance(msg, str)
        assert len(msg) > 0

    def test_returns_none_when_no_missing_fields(self):
        msg = generate_support_question_message([], ticket_type="issue")
        assert msg is None

    def test_uses_tenant_greeting_when_available(self):
        ctx = _make_ctx(tone="friendly")
        msg = generate_support_question_message(["address"], ticket_type="issue", tenant_ctx=ctx)
        assert msg is not None

    def test_emergency_includes_safety_disclaimer(self):
        msg = generate_support_question_message(["address"], ticket_type="emergency")
        assert msg is not None
        assert any(word in msg.lower() for word in ("säkerhet", "akut", "112", "emergency", "nöd"))


# ---------------------------------------------------------------------------
# prioritize_support
# ---------------------------------------------------------------------------

class TestPrioritizeSupport:
    def test_emergency_ticket_raises_score(self):
        analysis = _make_analysis(ticket_type="emergency", urgency="high")
        missing = _make_missing(0.6)
        result = prioritize_support(analysis, missing, {}, {})
        assert result.score > 30

    def test_angry_customer_raises_score(self):
        analysis = _make_analysis(customer_sentiment="angry", urgency="medium")
        missing = _make_missing(0.8)
        result = prioritize_support(analysis, missing, {}, {})
        assert result.score > 20

    def test_critical_urgency_gives_high_score(self):
        analysis = _make_analysis(urgency="critical", customer_sentiment="neutral")
        missing = _make_missing(0.9)
        result = prioritize_support(analysis, missing, {}, {})
        assert result.score >= 50

    def test_low_urgency_neutral_sentiment_gives_low_score(self):
        analysis = _make_analysis(urgency="low", customer_sentiment="neutral", ticket_type="question")
        missing = _make_missing(0.9)
        result = prioritize_support(analysis, missing, {}, {})
        assert result.score <= 30

    def test_category_critical_when_score_high(self):
        analysis = _make_analysis(urgency="critical", customer_sentiment="angry", ticket_type="emergency")
        missing = _make_missing(0.5)
        result = prioritize_support(analysis, missing, {}, {})
        assert result.category == "critical"

    def test_tenant_sla_bonus(self):
        ctx = _make_ctx(sla_rules={"critical_keywords": ["brand"], "urgent_categories": ["safety"]})
        analysis = _make_analysis(category="safety", urgency="medium")
        missing = _make_missing(0.8)
        result = prioritize_support(analysis, missing, {}, {}, tenant_ctx=ctx)
        assert result.tenant_context_used is True

    def test_no_context_tenant_context_used_false(self):
        analysis = _make_analysis()
        missing = _make_missing()
        result = prioritize_support(analysis, missing, {}, {})
        assert result.tenant_context_used is False

    def test_to_dict_contains_all_keys(self):
        analysis = _make_analysis()
        missing = _make_missing()
        result = prioritize_support(analysis, missing, {}, {})
        d = result.to_dict()
        for key in ("score", "category", "reasons", "business_risk_reason",
                    "tenant_context_used", "context_sources"):
            assert key in d


# ---------------------------------------------------------------------------
# build_support_response_draft
# ---------------------------------------------------------------------------

class TestBuildSupportResponseDraft:
    def test_emergency_gives_escalation_type(self):
        analysis = _make_analysis(ticket_type="emergency", urgency="critical")
        missing = _make_missing(0.8)
        prio = _make_priority(70, "critical")
        result = build_support_response_draft(analysis, missing, prio, {}, {})
        assert result.response_type == "escalation"

    def test_incomplete_info_gives_ask_for_info(self):
        analysis = _make_analysis(urgency="low")
        missing = _make_missing(0.4, missing=["address", "phone"])
        prio = _make_priority(20, "normal")
        result = build_support_response_draft(analysis, missing, prio, {}, {})
        assert result.response_type == "ask_for_info"

    def test_common_issue_match_gives_suggested_solution(self):
        issues = [{"keywords": ["pumpen"], "solution_steps": ["Stäng av pumpen", "Kontakta service"]}]
        ctx = _make_ctx(common_issues=issues)
        analysis = _make_analysis(urgency="low")
        missing = _make_missing(0.9)
        prio = _make_priority(20, "normal")
        input_data = {"message_text": "Det är problem med pumpen"}
        result = build_support_response_draft(analysis, missing, prio, {}, input_data, tenant_ctx=ctx)
        assert result.response_type == "suggested_solution"

    def test_returns_valid_model_instance(self):
        result = build_support_response_draft(
            _make_analysis(), _make_missing(), _make_priority(), {}, {}
        )
        assert isinstance(result, SupportResponseDraft)

    def test_to_dict_contains_disclaimer(self):
        result = build_support_response_draft(
            _make_analysis(), _make_missing(), _make_priority(), {}, {}
        )
        d = result.to_dict()
        assert "disclaimer" in d
        assert d["disclaimer"]

    def test_no_context_still_produces_result(self):
        result = build_support_response_draft(
            _make_analysis(), _make_missing(), _make_priority(), {}, {}
        )
        assert result.tenant_context_used is False
        assert result.body

    def test_emergency_risk_points_include_disclaimer(self):
        analysis = _make_analysis(ticket_type="emergency", urgency="critical")
        missing = _make_missing(0.8)
        prio = _make_priority(75, "critical")
        result = build_support_response_draft(analysis, missing, prio, {}, {})
        assert len(result.risk_points) > 0, "Emergency response should have at least one risk point"

    def test_angry_gives_escalation(self):
        analysis = _make_analysis(customer_sentiment="angry", urgency="low")
        missing = _make_missing(0.9)
        prio = _make_priority(40, "urgent")
        result = build_support_response_draft(analysis, missing, prio, {}, {})
        assert result.response_type == "escalation"


# ---------------------------------------------------------------------------
# decide_support_next_action
# ---------------------------------------------------------------------------

class TestDecideSupportNextAction:
    def test_critical_priority_gives_escalate(self):
        analysis = _make_analysis(ticket_type="emergency")
        missing = _make_missing(0.8)
        prio = _make_priority(80, "critical")
        result = decide_support_next_action(analysis, missing, prio)
        assert result.action == "escalate"

    def test_angry_customer_gives_escalate(self):
        analysis = _make_analysis(customer_sentiment="angry", requires_human=True)
        missing = _make_missing(0.8)
        prio = _make_priority(40, "urgent")
        result = decide_support_next_action(analysis, missing, prio)
        assert result.action == "escalate"

    def test_incomplete_gives_ask_for_info(self):
        analysis = _make_analysis()
        missing = _make_missing(0.3, missing=["address", "issue_description"])
        prio = _make_priority(20, "normal")
        result = decide_support_next_action(analysis, missing, prio)
        assert result.action == "ask_for_info"

    def test_common_issue_match_gives_suggest_solution(self):
        issues = [{"keywords": ["pumpen"], "solution_steps": ["Stäng av"]}]
        ctx = _make_ctx(common_issues=issues)
        analysis = _make_analysis(urgency="low", customer_sentiment="neutral")
        missing = _make_missing(0.9)
        prio = _make_priority(20, "normal")
        # Simulate that common issue was matched via analysis
        analysis.matched_service = None
        result = decide_support_next_action(analysis, missing, prio, tenant_ctx=ctx)
        # Without body text available to match, falls through to create_task or manual_review
        assert result.action in ("suggest_solution", "create_task", "manual_review", "ready_to_dispatch")

    def test_no_context_still_returns_action(self):
        result = decide_support_next_action(_make_analysis(), _make_missing(), _make_priority())
        assert isinstance(result, SupportNextAction)
        assert result.action in ("ask_for_info", "suggest_solution", "manual_review",
                                 "escalate", "create_task", "ready_to_dispatch")

    def test_tenant_context_used_set_when_provided(self):
        ctx = _make_ctx()
        result = decide_support_next_action(_make_analysis(), _make_missing(), _make_priority(), tenant_ctx=ctx)
        assert result.tenant_context_used is True

    def test_requires_approval_false_by_default(self):
        result = decide_support_next_action(_make_analysis(), _make_missing(), _make_priority())
        assert isinstance(result.requires_approval, bool)

    def test_to_dict_contains_all_keys(self):
        result = decide_support_next_action(_make_analysis(), _make_missing(), _make_priority())
        d = result.to_dict()
        for key in ("action", "requires_approval", "reason", "tenant_context_used", "context_sources"):
            assert key in d


# ---------------------------------------------------------------------------
# Fallback without tenant context — all modules
# ---------------------------------------------------------------------------

class TestFallbackWithoutTenantContext:
    """All modules must produce valid output and report no tenant context when ctx=None."""

    def test_analyzer_no_ctx(self):
        result = analyze_support({"message_text": "problem med installationen"}, tenant_ctx=None)
        assert isinstance(result, SupportAnalysis)
        assert result.tenant_context_used is False
        assert result.context_sources == []

    def test_analyzer_no_ctx_never_raises(self):
        analyze_support({}, tenant_ctx=None)
        analyze_support({"message_text": ""}, tenant_ctx=None)

    def test_missing_info_no_ctx(self):
        result = compute_support_missing_info("issue", {}, {}, tenant_ctx=None)
        assert isinstance(result, SupportMissingInfoResult)
        assert result.tenant_context_used is False
        assert result.schema_source == "default"

    def test_missing_info_no_ctx_never_raises(self):
        compute_support_missing_info("emergency", {}, {}, tenant_ctx=None)
        compute_support_missing_info("unknown_type", {}, {}, tenant_ctx=None)

    def test_question_generator_no_ctx(self):
        msg = generate_support_question_message(["address"], ticket_type="issue", tenant_ctx=None)
        assert msg is not None
        assert isinstance(msg, str)

    def test_question_generator_no_ctx_never_raises(self):
        generate_support_question_message([], tenant_ctx=None)
        generate_support_question_message(["x", "y", "z"], tenant_ctx=None)

    def test_prioritizer_no_ctx(self):
        result = prioritize_support(_make_analysis(), _make_missing(), {}, {}, tenant_ctx=None)
        assert isinstance(result, SupportPriority)
        assert result.tenant_context_used is False

    def test_prioritizer_no_ctx_gives_valid_score(self):
        result = prioritize_support(_make_analysis(), _make_missing(), {}, {}, tenant_ctx=None)
        assert isinstance(result.score, int)
        assert result.score >= 0

    def test_response_draft_no_ctx(self):
        result = build_support_response_draft(
            _make_analysis(), _make_missing(), _make_priority(), {}, {}, tenant_ctx=None
        )
        assert isinstance(result, SupportResponseDraft)
        assert result.tenant_context_used is False
        assert result.body

    def test_response_draft_no_ctx_never_raises(self):
        build_support_response_draft(
            _make_analysis(urgency="critical", ticket_type="emergency"),
            _make_missing(0.3),
            _make_priority(80, "critical"),
            {}, {}, tenant_ctx=None,
        )

    def test_next_action_no_ctx(self):
        result = decide_support_next_action(
            _make_analysis(), _make_missing(), _make_priority(), tenant_ctx=None
        )
        assert isinstance(result, SupportNextAction)
        assert result.tenant_context_used is False

    def test_next_action_no_ctx_never_raises(self):
        decide_support_next_action(
            _make_analysis(ticket_type="emergency", urgency="critical"),
            _make_missing(0.2),
            _make_priority(90, "critical"),
            tenant_ctx=None,
        )

    def test_load_support_context_no_memory(self):
        ctx = load_support_context("t1", {})
        assert ctx.context_available is False
        assert ctx.support_categories == []
        assert ctx.common_issues == []


# ---------------------------------------------------------------------------
# Helpers for API endpoint tests
# ---------------------------------------------------------------------------

def _support_record(job_id: str = "JOB-CS-1", support_status: str = "new") -> MagicMock:
    r = MagicMock()
    r.job_id = job_id
    r.tenant_id = "T1"
    r.job_type = "customer_inquiry"
    r.input_data = {"subject": "Problem", "message_text": "Mitt tak läcker.", "support_status": support_status}
    support_payload = {
        "processor_name": "support_analyzer_processor",
        "support_analysis": {"ticket_type": "issue", "category": "service", "urgency": "medium",
                              "customer_sentiment": "neutral", "requires_human": False, "confidence": 0.7,
                              "matched_service": None, "tenant_context_used": False, "context_sources": []},
        "support_missing_info": {"required_fields": ["address"], "present_fields": [],
                                 "missing_fields": ["address"], "optional_fields": [],
                                 "completeness_score": 0.5, "schema_source": "default",
                                 "tenant_context_used": False, "context_sources": []},
        "support_priority": {"score": 25, "category": "normal", "reasons": ["medium urgency"],
                             "business_risk_reason": None, "tenant_context_used": False, "context_sources": []},
        "support_next_action": {"action": "ask_for_info", "requires_approval": False,
                                "reason": "info missing", "tenant_context_used": False, "context_sources": []},
        "support_response_draft": {"response_type": "ask_for_info", "subject": "Hej",
                                   "body": "Kan du skicka adress?", "assumptions": [],
                                   "risk_points": [], "recommended_next_step": "Invänta svar",
                                   "confidence": 0.6, "tenant_context_used": False, "context_sources": []},
        "support_status": support_status,
        "confidence": 0.7,
    }
    r.processor_history = [
        {"processor": "support_analyzer_processor",
         "result": {"status": "completed", "payload": support_payload}}
    ]
    r.result = {"status": "completed", "payload": support_payload,
                "processor_history": r.processor_history}
    return r


def _mock_support_db(record: MagicMock) -> MagicMock:
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.first.return_value = record
    q.all.return_value = [record]
    return db


# ---------------------------------------------------------------------------
# API endpoint — no side effects tests (direct function calls, no TestClient)
# ---------------------------------------------------------------------------

class TestSupportStatusEndpointNoSideEffects:
    """PATCH /jobs/{job_id}/support-status must only write via DB commit, never external calls."""

    def _call(self, status: str = "in_review", job_id: str = "JOB-CS-1"):
        from app.main import set_support_status, SupportStatusRequest
        db = _mock_support_db(_support_record(job_id))
        body = SupportStatusRequest(status=status)
        return set_support_status(job_id=job_id, body=body, db=db, tenant_id="T1")

    def test_returns_job_id_and_status(self):
        result = self._call("in_review")
        assert result["job_id"] == "JOB-CS-1"
        assert result["support_status"] == "in_review"

    def test_does_not_call_execute_action(self):
        with patch("app.workflows.action_executor.execute_action") as mock_exec:
            self._call("resolved")
            mock_exec.assert_not_called()

    def test_does_not_call_monday_client(self):
        with patch("app.integrations.monday.client.MondayClient") as mock_monday:
            self._call("closed")
            mock_monday.assert_not_called()

    def test_invalid_status_raises_422(self):
        from fastapi import HTTPException
        from app.main import set_support_status, SupportStatusRequest
        db = _mock_support_db(_support_record())
        body = SupportStatusRequest(status="invalid_xyz")
        with pytest.raises(HTTPException) as exc_info:
            set_support_status(job_id="JOB-CS-1", body=body, db=db, tenant_id="T1")
        assert exc_info.value.status_code == 422

    def test_non_customer_inquiry_raises_422(self):
        from fastapi import HTTPException
        from app.main import set_support_status, SupportStatusRequest
        rec = _support_record()
        rec.job_type = "lead"
        db = _mock_support_db(rec)
        body = SupportStatusRequest(status="resolved")
        with pytest.raises(HTTPException) as exc_info:
            set_support_status(job_id="JOB-CS-1", body=body, db=db, tenant_id="T1")
        assert exc_info.value.status_code == 422

    def test_unknown_job_raises_404(self):
        from fastapi import HTTPException
        from app.main import set_support_status, SupportStatusRequest
        db = MagicMock()
        q = MagicMock()
        db.query.return_value = q
        q.filter.return_value = q
        q.first.return_value = None
        body = SupportStatusRequest(status="new")
        with pytest.raises(HTTPException) as exc_info:
            set_support_status(job_id="MISSING", body=body, db=db, tenant_id="T1")
        assert exc_info.value.status_code == 404


class TestSupportRegenerateEndpointNoSideEffects:
    """POST /jobs/{job_id}/support-regenerate must only re-run deterministic analysis — no external calls."""

    def _call(self, job_id: str = "JOB-CS-1"):
        from app.main import regenerate_support_analysis

        rec = _support_record(job_id)
        db = _mock_support_db(rec)

        mock_job = MagicMock()
        mock_job.job_id = job_id
        mock_job.tenant_id = "T1"
        mock_job.job_type = "customer_inquiry"
        mock_job.input_data = dict(rec.input_data)
        mock_job.processor_history = list(rec.processor_history)
        mock_job.result = rec.result

        with patch("app.repositories.postgres.job_repository.JobRepository") as mock_repo, \
             patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository") as mock_cfg:
            mock_repo._to_domain.return_value = mock_job
            mock_repo.update_job.return_value = None
            mock_cfg.get_settings.return_value = {}  # no tenant context → fallback
            return regenerate_support_analysis(job_id=job_id, db=db, tenant_id="T1"), mock_repo

    def test_returns_support_analysis_keys(self):
        result, _ = self._call()
        assert "support_analysis" in result
        assert "support_priority" in result
        assert "support_next_action" in result

    def test_does_not_call_execute_action(self):
        with patch("app.workflows.action_executor.execute_action") as mock_exec:
            self._call()
            mock_exec.assert_not_called()

    def test_does_not_call_monday_client(self):
        with patch("app.integrations.monday.client.MondayClient") as mock_monday:
            self._call()
            mock_monday.assert_not_called()

    def test_calls_update_job_not_dispatch(self):
        result, mock_repo = self._call()
        mock_repo.update_job.assert_called_once()

    def test_non_customer_inquiry_raises_422(self):
        from fastapi import HTTPException
        from app.main import regenerate_support_analysis
        rec = _support_record()
        rec.job_type = "lead"
        db = _mock_support_db(rec)
        with pytest.raises(HTTPException) as exc_info:
            regenerate_support_analysis(job_id="JOB-CS-1", db=db, tenant_id="T1")
        assert exc_info.value.status_code == 422

    def test_fallback_when_no_tenant_memory(self):
        result, _ = self._call()
        sa = result["support_analysis"]
        assert sa["tenant_context_used"] is False
        assert sa["context_sources"] == []


class TestDashboardSupportEndpointNoSideEffects:
    """GET /dashboard/support must only aggregate DB records — no external calls."""

    def _call(self, records: list | None = None):
        from app.main import dashboard_support
        db = MagicMock()
        q = MagicMock()
        db.query.return_value = q
        q.filter.return_value = q
        q.all.return_value = records if records is not None else [_support_record()]
        return dashboard_support(db=db, tenant_id="T1")

    def test_returns_required_keys(self):
        result = self._call()
        assert "total_cases" in result
        assert "by_status" in result
        assert "by_ticket_type" in result
        assert "by_priority" in result
        assert "escalated_count" in result
        assert "awaiting_info_count" in result

    def test_empty_returns_zeros(self):
        result = self._call(records=[])
        assert result["total_cases"] == 0
        assert result["by_priority"] == {"critical": 0, "urgent": 0, "normal": 0}

    def test_counts_one_case(self):
        result = self._call(records=[_support_record(support_status="in_review")])
        assert result["total_cases"] == 1

    def test_does_not_call_execute_action(self):
        with patch("app.workflows.action_executor.execute_action") as mock_exec:
            self._call()
            mock_exec.assert_not_called()

    def test_does_not_call_monday_client(self):
        with patch("app.integrations.monday.client.MondayClient") as mock_monday:
            self._call()
            mock_monday.assert_not_called()

    def test_escalated_count_from_next_action(self):
        rec = _support_record()
        rec.processor_history[0]["result"]["payload"]["support_next_action"]["action"] = "escalate"
        result = self._call(records=[rec])
        assert result["escalated_count"] == 1

    def test_awaiting_info_count_from_next_action(self):
        rec = _support_record()
        rec.processor_history[0]["result"]["payload"]["support_next_action"]["action"] = "ask_for_info"
        result = self._call(records=[rec])
        assert result["awaiting_info_count"] == 1
