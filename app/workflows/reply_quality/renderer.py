"""Profile-aware coworker renderer: constrained LLM primary, deterministic fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflows.reply_quality.llm_renderer import (
    MODEL_ID,
    PROMPT_VERSION,
    compose_constrained_reply_hermetic,
    render_constrained_llm_reply,
)
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.post_render_validator import validate_post_render_reply
from app.workflows.reply_quality.provenance import (
    DETERMINISTIC_RENDERER,
    LLM_RENDERER,
    RENDERER_POLICY_VERSION,
    ReplyRenderProvenance,
    hash_body,
    hash_plan,
)
from app.workflows.reply_quality.reply_language import localized_closing

TEMPLATE_VERSION = "digital_coworker_constrained_llm_v4"


@dataclass(frozen=True)
class RenderResult:
    body: str
    provenance: ReplyRenderProvenance
    validation: dict[str, Any]


def _lang(plan: CustomerReplyPlanV2) -> str:
    return "en" if (plan.language or "sv").lower().startswith("en") else "sv"


def _render_safe_fallback(plan: CustomerReplyPlanV2) -> str:
    language = _lang(plan)
    closing = localized_closing(language=language)
    signature = f"\n\n{closing}\n{plan.signature_name}" if plan.signature_name else ""
    register = plan.salutation_strategy or ("du" if language == "sv" else "you")
    if language == "en":
        ack = "Thank you for your message. We have received it and will get back to you."
    elif register == "du":
        ack = "Tack för ditt meddelande. Vi har tagit emot det och återkommer."
    else:
        ack = "Tack för ert meddelande. Vi har tagit emot det och återkommer."
    return f"{plan.greeting}\n\n{ack}\n\n{plan.next_step_statement}{signature}"


def render_coworker_reply_with_validation(
    plan: CustomerReplyPlanV2,
    *,
    draft_body: str | None = None,
    sent_body: str | None = None,
) -> RenderResult:
    fallback_reason: str | None = plan.fallback_reason
    fallback_tier = "none"
    live_body: str | None = None
    live_validation: dict[str, Any] | None = None

    body, llm_meta = render_constrained_llm_reply(plan)
    if llm_meta.get("live_call"):
        live_body = body
        live_validation = validate_post_render_reply(plan=plan, body=body)
        llm_meta = {
            **llm_meta,
            "live_validation_outcome": "pass" if live_validation["passed"] else "fail",
            "live_validation_issues": list(live_validation.get("issues") or []),
            "live_body_hash": hash_body(body),
        }

    validation = validate_post_render_reply(plan=plan, body=body)

    if llm_meta.get("live_call") and live_validation and not live_validation["passed"]:
        fallback_reason = ",".join(live_validation["issues"][:3]) or "post_render_validation_failed"
        body = compose_constrained_reply_hermetic(plan)
        validation = validate_post_render_reply(plan=plan, body=body)
        fallback_tier = "hermetic"
        llm_meta = {**llm_meta, "fallback_from_live_validation": True}

    elif not llm_meta.get("live_call") and not validation["passed"]:
        fallback_reason = ",".join(validation["issues"][:3]) or "post_render_validation_failed"
        body = compose_constrained_reply_hermetic(plan)
        validation = validate_post_render_reply(plan=plan, body=body)
        fallback_tier = "hermetic"

    if not validation["passed"]:
        fallback_reason = fallback_reason or ",".join(validation["issues"][:3]) or "post_render_validation_failed"
        body = _render_safe_fallback(plan)
        validation = validate_post_render_reply(plan=plan, body=body)
        fallback_tier = "safe"

    live_success = (
        bool(llm_meta.get("live_call"))
        and fallback_tier == "none"
        and validation["passed"]
        and (live_validation is None or live_validation["passed"])
    )
    if live_success:
        renderer_type = LLM_RENDERER
        llm_used = True
        model_id = MODEL_ID
        prompt_version = PROMPT_VERSION
    else:
        renderer_type = DETERMINISTIC_RENDERER
        llm_used = False
        model_id = None
        prompt_version = PROMPT_VERSION if llm_meta.get("invocation_attempted") else None

    provenance = ReplyRenderProvenance(
        renderer_type=renderer_type,
        llm_used=llm_used,
        model_id=model_id,
        prompt_version=prompt_version,
        template_version=TEMPLATE_VERSION,
        use_fallback=fallback_tier != "none",
        fallback_reason=fallback_reason if fallback_tier != "none" else None,
        plan_hash=hash_plan(plan.to_dict()),
        body_hash=hash_body(body),
        draft_body_hash=hash_body(draft_body) if draft_body else None,
        sent_body_hash=hash_body(sent_body) if sent_body else None,
        policy_version=RENDERER_POLICY_VERSION,
    )
    validation = {
        **validation,
        "llm_meta": {
            **llm_meta,
            "validation_outcome": "pass" if validation.get("passed") else "fail",
            "fallback_tier": fallback_tier,
        },
    }
    return RenderResult(body=body, provenance=provenance, validation=validation)
