"""Forensic audit of legacy safe-ack rendering path (Todo A)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.quality_dataset import generate_quality_dataset
from app.workflows.missing_fact_plan import build_missing_fact_plan
from app.workflows.reply_planning import build_customer_reply_plan, render_customer_reply
from app.workflows.reply_candidate_safety import assess_reply_candidate_safety
from app.workflows.safe_ack_eligibility import evaluate_safe_ack_eligibility
from app.workflows.reply_quality.provenance import LEGACY_RENDERER, hash_body, hash_plan

SEND_SCENARIO_IDS: tuple[str, ...] = (
    "PTB-Q96-0000",
    "PTB-Q96-0003",
    "PTB-Q96-0012",
    "PTB-Q96-0015",
    "PTB-Q96-0018",
)


@dataclass
class ReplyPathAuditRecord:
    scenario_id: str
    family: str
    renderer_type: str
    llm_used: bool
    use_fallback: bool
    fallback_reason: str | None
    template_version: str
    plan_fields_populated: dict[str, Any]
    selected_questions: list[str]
    service_type: str
    draft_body_excerpt: str
    body_hash: str
    plan_hash: str
    safety_passed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "family": self.family,
            "renderer_type": self.renderer_type,
            "llm_used": self.llm_used,
            "use_fallback": self.use_fallback,
            "fallback_reason": self.fallback_reason,
            "template_version": self.template_version,
            "plan_fields_populated": self.plan_fields_populated,
            "selected_questions": self.selected_questions,
            "service_type": self.service_type,
            "draft_body_excerpt": self.draft_body_excerpt,
            "body_hash": self.body_hash,
            "plan_hash": self.plan_hash,
            "safety_passed": self.safety_passed,
        }


def audit_legacy_reply_path(
    *,
    profile_id: str = "niklas-demo-live-eval-v1",
    seed: int = 0,
) -> list[ReplyPathAuditRecord]:
    profile = load_customer_profile(profile_id)
    scenarios = {s.scenario_id: s for s in generate_quality_dataset(profile, seed=seed)}
    records: list[ReplyPathAuditRecord] = []

    for scenario_id in SEND_SCENARIO_IDS:
        scenario = scenarios.get(scenario_id)
        if scenario is None:
            continue
        input_data = {
            "subject": scenario.input.subject,
            "message_text": scenario.input.message_text,
            "sender": {
                "name": scenario.input.sender_name,
                "email": scenario.input.sender_email,
            },
        }
        entities = {"email": scenario.input.sender_email}
        missing = build_missing_fact_plan(input_data=input_data, entities=entities)
        eligibility = evaluate_safe_ack_eligibility(
            detected_job_type="lead",
            risk_detected=False,
            risk_categories=[],
            extraction_issues=[],
            input_data=input_data,
            recommendation=None,
            recommendation_raw="manual_review",
            low_confidence=True,
            used_fallback=False,
        )
        reply_plan = build_customer_reply_plan(
            greeting="Hej,",
            signature_name="Niklas",
            missing_fact_plan=missing,
            eligibility=eligibility,
            entities=entities,
        )
        assert reply_plan is not None
        body = render_customer_reply(reply_plan)
        safety = assess_reply_candidate_safety(body)
        use_fallback = False
        fallback_reason = None
        if not safety.get("passed"):
            body = render_customer_reply(reply_plan, use_fallback=True)
            use_fallback = True
            fallback_reason = "reply_candidate_safety_failed"

        records.append(
            ReplyPathAuditRecord(
                scenario_id=scenario_id,
                family=scenario.family,
                renderer_type=LEGACY_RENDERER,
                llm_used=False,
                use_fallback=use_fallback,
                fallback_reason=fallback_reason,
                template_version="safe_ack_incomplete_lead_v1",
                plan_fields_populated=reply_plan.to_dict(),
                selected_questions=list(reply_plan.missing_questions),
                service_type=missing.service_type,
                draft_body_excerpt=body[:240],
                body_hash=hash_body(body),
                plan_hash=hash_plan(reply_plan.to_dict()),
                safety_passed=bool(assess_reply_candidate_safety(body).get("passed")),
            )
        )
    return records
