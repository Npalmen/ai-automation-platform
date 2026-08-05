"""Profile-aware coworker renderer: constrained LLM primary, deterministic fallback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflows.reply_quality.final_text_validation import (
    build_final_customer_text_validation,
    validate_stage,
)
from app.workflows.reply_quality.llm_renderer import (
    MODEL_ID,
    PROMPT_VERSION,
    RENDERER_POLICY_VERSION as LLM_RENDERER_POLICY_VERSION,
    TEMPLATE_VERSION as LLM_TEMPLATE_VERSION,
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
from app.workflows.reply_quality.renderer_requirement import RendererRequirement
from app.workflows.reply_quality.reply_language import localized_closing

TEMPLATE_VERSION = "digital_coworker_constrained_llm_v5"


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
    requirement: RendererRequirement = RendererRequirement.DEFAULT,
) -> RenderResult:
    if requirement == RendererRequirement.CONSTRAINED_LLM_REQUIRED:
        return _render_constrained_llm_required(
            plan,
            draft_body=draft_body,
            sent_body=sent_body,
        )

    fallback_reason: str | None = plan.fallback_reason
    fallback_tier = "none"
    live_body: str | None = None
    live_validation: dict[str, Any] | None = None
    stage_results: list[dict[str, Any]] = []

    body, llm_meta = render_constrained_llm_reply(plan)
    if llm_meta.get("live_call"):
        live_body = body
        live_validation = validate_post_render_reply(plan=plan, body=body)
        stage_results.append(
            validate_stage(plan=plan, body=body, validation_stage="raw_llm")
        )
        llm_meta = {
            **llm_meta,
            "live_validation_outcome": "pass" if live_validation["passed"] else "fail",
            "live_validation_issues": list(live_validation.get("issues") or []),
            "live_body_hash": hash_body(body),
            "live_body": body,
        }

    validation = validate_post_render_reply(plan=plan, body=body)
    if not llm_meta.get("live_call"):
        stage_results.append(
            validate_stage(plan=plan, body=body, validation_stage="raw_llm")
        )

    if llm_meta.get("live_call") and live_validation and not live_validation["passed"]:
        fallback_reason = ",".join(live_validation["issues"][:3]) or "post_render_validation_failed"
        body = compose_constrained_reply_hermetic(plan)
        validation = validate_post_render_reply(plan=plan, body=body)
        stage_results.append(
            validate_stage(plan=plan, body=body, validation_stage="deterministic_fallback")
        )
        fallback_tier = "hermetic"
        llm_meta = {**llm_meta, "fallback_from_live_validation": True}

    elif not llm_meta.get("live_call") and not validation["passed"]:
        fallback_reason = ",".join(validation["issues"][:3]) or "post_render_validation_failed"
        body = compose_constrained_reply_hermetic(plan)
        validation = validate_post_render_reply(plan=plan, body=body)
        stage_results.append(
            validate_stage(plan=plan, body=body, validation_stage="deterministic_fallback")
        )
        fallback_tier = "hermetic"

    if not validation["passed"]:
        fallback_reason = fallback_reason or ",".join(validation["issues"][:3]) or "post_render_validation_failed"
        body = _render_safe_fallback(plan)
        validation = validate_post_render_reply(plan=plan, body=body)
        stage_results.append(
            validate_stage(plan=plan, body=body, validation_stage="safe_fallback")
        )
        fallback_tier = "safe"

    final_validation = build_final_customer_text_validation(
        plan=plan,
        body=body,
        stage_results=stage_results,
    )
    if not final_validation["passed"]:
        fallback_reason = fallback_reason or ",".join(final_validation["issues"][:3]) or "final_customer_text_failed"
        body = ""
        fallback_tier = "no_reply"
        validation = validate_post_render_reply(plan=plan, body=body)
        stage_results.append(
            validate_stage(plan=plan, body=body, validation_stage="no_reply")
        )
        final_validation = build_final_customer_text_validation(
            plan=plan,
            body=body,
            stage_results=stage_results,
        )

    live_success = (
        bool(llm_meta.get("live_call"))
        and fallback_tier == "none"
        and final_validation["passed"]
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
        "final_customer_text_validation": final_validation,
        "renderer_requirement": RendererRequirement.DEFAULT.value,
        "llm_meta": {
            **llm_meta,
            "validation_outcome": "pass" if final_validation.get("passed") else "fail",
            "fallback_tier": fallback_tier,
            "raw_llm_validator_failures": sum(
                1 for s in stage_results if s.get("validation_stage") == "raw_llm" and not s.get("passed")
            ),
            "deterministic_fallback_count": sum(
                1 for s in stage_results if s.get("validation_stage") == "deterministic_fallback"
            ),
            "fallback_validator_failures": sum(
                1
                for s in stage_results
                if s.get("validation_stage") in {"deterministic_fallback", "safe_fallback"} and not s.get("passed")
            ),
            "final_customer_text_validator_failures": 0 if final_validation.get("passed") else 1,
        },
    }
    return RenderResult(body=body, provenance=provenance, validation=validation)


def _render_constrained_llm_required(
    plan: CustomerReplyPlanV2,
    *,
    draft_body: str | None = None,
    sent_body: str | None = None,
) -> RenderResult:
    """Strict R4 path: live constrained LLM only; no deterministic/safe/no_reply fallback."""
    stage_results: list[dict[str, Any]] = []
    body, llm_meta = render_constrained_llm_reply(
        plan,
        require_live=True,
        temperature=0.0,
        retry_attempts=2,
    )
    blockers: list[str] = []
    if llm_meta.get("provider_outcome") != "success" or not llm_meta.get("live_call"):
        blockers.append(f"provider_outcome:{llm_meta.get('provider_outcome')}")
    if not body.strip():
        blockers.append("empty_llm_body")
    if not llm_meta.get("returned_model_id") and not llm_meta.get("returned_model"):
        blockers.append("missing_returned_model")
    if llm_meta.get("prompt_version") != PROMPT_VERSION:
        blockers.append("prompt_version_mismatch")

    validation = validate_post_render_reply(plan=plan, body=body) if body else {
        "passed": False,
        "issues": ["empty_body"],
    }
    stage_results.append(validate_stage(plan=plan, body=body, validation_stage="raw_llm"))
    if not validation.get("passed"):
        blockers.append("post_render_validation_failed")

    final_validation = build_final_customer_text_validation(
        plan=plan,
        body=body,
        stage_results=stage_results,
    )
    if not final_validation.get("passed"):
        blockers.append("final_text_validation_failed")

    ok = not blockers
    provenance = ReplyRenderProvenance(
        renderer_type=LLM_RENDERER if ok else DETERMINISTIC_RENDERER,
        llm_used=ok,
        model_id=(llm_meta.get("returned_model_id") or llm_meta.get("returned_model") or MODEL_ID)
        if ok
        else None,
        prompt_version=PROMPT_VERSION if ok else None,
        template_version=LLM_TEMPLATE_VERSION,
        use_fallback=False,
        fallback_reason=None if ok else ",".join(blockers[:3]),
        plan_hash=hash_plan(plan.to_dict()),
        body_hash=hash_body(body) if ok and body else "",
        draft_body_hash=hash_body(draft_body) if draft_body else None,
        sent_body_hash=hash_body(sent_body) if sent_body else None,
        policy_version=LLM_RENDERER_POLICY_VERSION,
    )
    if not ok:
        # Do not accept deterministic body for R4; clear body.
        body = ""
        provenance = ReplyRenderProvenance(
            renderer_type="blocked_constrained_llm_required",
            llm_used=False,
            model_id=None,
            prompt_version=PROMPT_VERSION if llm_meta.get("invocation_attempted") else None,
            template_version=LLM_TEMPLATE_VERSION,
            use_fallback=False,
            fallback_reason=",".join(blockers[:5]),
            plan_hash=hash_plan(plan.to_dict()),
            body_hash="",
            draft_body_hash=hash_body(draft_body) if draft_body else None,
            sent_body_hash=hash_body(sent_body) if sent_body else None,
            policy_version=LLM_RENDERER_POLICY_VERSION,
        )

    return RenderResult(
        body=body if ok else "",
        provenance=provenance,
        validation={
            **validation,
            "passed": ok,
            "blockers": blockers,
            "final_customer_text_validation": final_validation,
            "renderer_requirement": RendererRequirement.CONSTRAINED_LLM_REQUIRED.value,
            "llm_meta": {
                **llm_meta,
                "fallback_tier": "none",
                "fallback_used": False,
                "strict_mode": True,
                "validation_outcome": "pass" if ok else "fail",
            },
        },
    )
