"""Profile-aware deterministic renderer and validation (Todos E-F)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflows.reply_candidate_safety import assess_reply_candidate_safety
from app.workflows.reply_quality.customer_surface import compose_question_block
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.provenance import (
    DETERMINISTIC_RENDERER,
    RENDERER_POLICY_VERSION,
    ReplyRenderProvenance,
    hash_body,
    hash_plan,
)
from app.workflows.reply_quality.reply_language import localized_closing
from app.workflows.reply_quality.surface_contract import validate_customer_surface

TEMPLATE_VERSION = "digital_coworker_natural_v3"


@dataclass(frozen=True)
class RenderResult:
    body: str
    provenance: ReplyRenderProvenance
    validation: dict[str, Any]


def _lang(plan: CustomerReplyPlanV2) -> str:
    return "en" if (plan.language or "sv").lower().startswith("en") else "sv"


def render_deterministic_coworker_reply(plan: CustomerReplyPlanV2) -> str:
    language = _lang(plan)
    closing = localized_closing(language=language)
    signature = f"\n\n{closing}\n{plan.signature_name}" if plan.signature_name else ""

    acknowledgement = plan.acknowledgement_statement.strip()
    questions = tuple(plan.question_surface_labels)
    question_block = compose_question_block(
        questions,
        language=language,
        service_family=plan.service_family,
    )

    if plan.service_family == "job_status" and plan.case_reference_phrase and not questions:
        body_middle = (
            f"{acknowledgement}\n\n{plan.next_step_statement}"
        )
    elif question_block:
        body_middle = f"{acknowledgement}\n\n{question_block}\n\n{plan.next_step_statement}"
    else:
        body_middle = f"{acknowledgement}\n\n{plan.next_step_statement}"

    return f"{plan.greeting}\n\n{body_middle}{signature}"


def _render_safe_fallback(plan: CustomerReplyPlanV2) -> str:
    language = _lang(plan)
    closing = localized_closing(language=language)
    signature = f"\n\n{closing}\n{plan.signature_name}" if plan.signature_name else ""
    ack = (
        "Thank you for your message. We have received it and will get back to you."
        if language == "en"
        else "Tack för ditt meddelande. Vi har tagit emot det och återkommer."
    )
    return f"{plan.greeting}\n\n{ack}\n\n{plan.next_step_statement}{signature}"


def validate_rendered_reply(
    *,
    plan: CustomerReplyPlanV2,
    body: str,
) -> dict[str, Any]:
    issues: list[str] = []
    surface = validate_customer_surface(body, expected_language=_lang(plan))
    issues.extend(surface.get("issues") or [])

    normalized = body.lower()
    if "kompletteringen" in normalized and "continuation_with_new_facts" not in plan.evidence:
        issues.append("acknowledgement:unsupported_completion_claim")

    safety = assess_reply_candidate_safety(body)
    if not safety.get("passed"):
        issues.extend(safety.get("violations") or [])

    return {
        "passed": not issues and safety.get("passed", False),
        "issues": issues,
        "safety": safety,
        "surface": surface,
    }


def render_coworker_reply_with_validation(
    plan: CustomerReplyPlanV2,
    *,
    draft_body: str | None = None,
    sent_body: str | None = None,
) -> RenderResult:
    fallback_reason: str | None = plan.fallback_reason
    body = render_deterministic_coworker_reply(plan)
    validation = validate_rendered_reply(plan=plan, body=body)

    if not validation["passed"]:
        fallback_reason = ",".join(validation["issues"][:3]) or "validation_failed"
        body = _render_safe_fallback(plan)
        validation = validate_rendered_reply(plan=plan, body=body)

    provenance = ReplyRenderProvenance(
        renderer_type=DETERMINISTIC_RENDERER,
        llm_used=False,
        model_id=None,
        prompt_version=None,
        template_version=TEMPLATE_VERSION,
        use_fallback=bool(fallback_reason),
        fallback_reason=fallback_reason,
        plan_hash=hash_plan(plan.to_dict()),
        body_hash=hash_body(body),
        draft_body_hash=hash_body(draft_body) if draft_body else None,
        sent_body_hash=hash_body(sent_body) if sent_body else None,
        policy_version=RENDERER_POLICY_VERSION,
    )
    return RenderResult(body=body, provenance=provenance, validation=validation)
