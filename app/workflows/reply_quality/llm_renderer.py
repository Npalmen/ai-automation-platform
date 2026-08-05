"""Constrained LLM renderer and hermetic composer for coworker replies."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from app.workflows.reply_quality.customer_surface import localized_next_step, pronoun_surface_contract
from app.workflows.reply_quality.question_surface_composition import compose_customer_question_block
from app.workflows.reply_quality.llm_reply_parser import LLMReplyParseError, parse_llm_reply_output
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.reply_language import localized_closing

PROMPT_VERSION = "coworker_constrained_llm_v5"
MODEL_ID = "gpt-4o-mini"
TEMPLATE_VERSION = "digital_coworker_constrained_llm_v5"
RENDERER_POLICY_VERSION = "constrained_llm_renderer_v1"

_PRONOUN_RULES_SV = {
    "du": "Use ONLY informal du/dig/din/ditt/dina — never ni/er/ert/era.",
    "ni": "Use ONLY formal ni/er/ert/era — never du/dig/din/ditt/dina.",
}
_PRONOUN_RULES_EN = {
    "you": "Use consistent second-person you/your throughout.",
}


def build_constrained_llm_payload(plan: CustomerReplyPlanV2) -> dict[str, Any]:
    """Surface-safe payload allowed into the constrained LLM renderer."""
    pronoun = plan.salutation_strategy or ("du" if plan.language == "sv" else "you")
    pronoun_contract = pronoun_surface_contract(register=pronoun, language=plan.language)
    from app.workflows.reply_quality.next_step_surface import build_next_step_surface

    next_surface = build_next_step_surface(
        step_id=plan.response_objective,
        service_family=plan.service_family,
        business_intent=plan.business_intent,
        thread_state=plan.thread_context.thread_state,
        is_continuation=plan.thread_context.is_continuation,
        has_questions=bool(plan.question_surface_labels),
        language=plan.language,
        scenario_family=plan.scenario_family,
        mentions_attachment_gap=any("missing_attachment" in e for e in plan.evidence),
    )
    return {
        "language": plan.language,
        "pronoun_register": pronoun,
        "pronoun_allowed_forms": list(pronoun_contract["allowed"]),
        "pronoun_forbidden_forms": list(pronoun_contract["forbidden"]),
        "greeting": plan.greeting,
        "acknowledgement_statement": plan.acknowledgement_statement,
        "approved_questions": list(plan.question_surface_labels),
        "selected_question_ids": list(plan.selected_questions),
        "next_step_statement": plan.next_step_statement,
        "next_step_contract": next_surface.to_dict(),
        "signature_name": plan.signature_name,
        "service_family": plan.service_family,
        "response_objective": plan.response_objective,
        "location_phrase": plan.location_phrase,
        "case_reference_phrase": plan.case_reference_phrase,
        "commitment_constraints": list(plan.commitment_constraints),
        "facts_allowed_to_reference": list(plan.verified_facts),
        "facts_not_allowed_to_repeat": list(plan.facts_not_allowed_to_repeat),
        "thread_summary": plan.thread_context.summary,
    }


def build_constrained_llm_prompt(plan: CustomerReplyPlanV2) -> str:
    payload = build_constrained_llm_payload(plan)
    language = (plan.language or "sv").lower()
    register = plan.salutation_strategy or ("du" if language.startswith("sv") else "you")
    if language.startswith("en"):
        pronoun_rule = _PRONOUN_RULES_EN.get(register, _PRONOUN_RULES_EN["you"])
        pronoun_detail = ""
    else:
        pronoun_rule = _PRONOUN_RULES_SV.get(register, _PRONOUN_RULES_SV["ni"])
        contract = pronoun_surface_contract(register=register, language=plan.language)
        allowed = ", ".join(contract["allowed"])
        forbidden = ", ".join(contract["forbidden"])
        pronoun_detail = (
            f" Allowed forms: {allowed}. Forbidden forms: {forbidden}. "
            "Apply consistently in acknowledgement, questions, next step, and closing."
        )

    return (
        "Compose a natural customer email reply using ONLY the approved fields in the JSON payload.\n"
        'Return JSON: {"reply_body": "<full email text>"}\n'
        "Hard rules:\n"
        f"- Language: {plan.language}. {pronoun_rule}{pronoun_detail}\n"
        "- Use next_step_statement verbatim in meaning; do not replace it with a generic "
        "'review conditions and get back' phrase when next_step_contract specifies a concrete step.\n"
        "- Write flowing prose paragraphs only.\n"
        "- NEVER use schema labels, field names, key:value lines, bullet lists of internal fields, "
        "or technical headings from the payload.\n"
        "- Include EVERY approved question from approved_questions as natural sentences.\n"
        "- Do not add facts, promises, or questions beyond the payload.\n"
        "- Do not repeat facts listed in facts_not_allowed_to_repeat.\n"
        "- Use greeting, acknowledgement, questions, next_step_statement, and signature naturally.\n"
        f"Payload:\n{json.dumps(payload, ensure_ascii=False)}"
    )


def _compose_address_question(plan: CustomerReplyPlanV2) -> str | None:
    if "address" not in plan.selected_questions or not plan.location_phrase:
        return None
    if (plan.language or "sv").lower().startswith("en"):
        return f"Which address in {plan.location_phrase} applies to the installation?"
    return f"Vilken adress i {plan.location_phrase} gäller installationen?"


def _is_standalone_question(text: str) -> bool:
    lowered = text.strip().lower()
    return lowered.startswith(
        (
            "vilken ",
            "vilket ",
            "which ",
            "vad ",
            "what ",
            "när ",
            "when ",
            "hur ",
            "how ",
            "kan ",
            "could ",
            "finns ",
        )
    ) or lowered.startswith("om ") and "?" in text


def _join_questions_sv(questions: tuple[str, ...], register: str) -> str:
    if not questions:
        return ""
    standalone = [_is_standalone_question(q) for q in questions]
    if len(questions) == 1:
        q = questions[0].rstrip(".?")
        if standalone[0]:
            return q if q.endswith("?") else q + "?"
        if register == "du":
            return f"Kan du skicka {q}?"
        return f"Kan ni skicka {q}?"
    if any(standalone):
        parts: list[str] = []
        for q, is_standalone in zip(questions, standalone):
            cleaned = q.rstrip(".?")
            if is_standalone:
                parts.append(cleaned if cleaned.endswith("?") else cleaned + "?")
            elif register == "du":
                parts.append(f"kan du skicka {cleaned}")
            else:
                parts.append(f"kan ni skicka {cleaned}")
        if len(parts) == 1:
            return parts[0][0].upper() + parts[0][1:] + ("?" if not parts[0].endswith("?") else "")
        body = ", ".join(parts[:-1]) + f" och {parts[-1]}"
        return body[0].upper() + body[1:] + ("?" if not body.endswith("?") else "")
    joined = ", ".join(q.rstrip(".?") for q in questions[:-1])
    last = questions[-1].rstrip(".?")
    if register == "du":
        return f"Kan du skicka {joined} och {last}?"
    return f"Kan ni skicka {joined} och {last}?"


def _render_question_block(plan: CustomerReplyPlanV2) -> str:
    language = "en" if (plan.language or "sv").lower().startswith("en") else "sv"
    register = plan.salutation_strategy or ("du" if plan.service_family in {"existing_installation_support", "complaint_warranty"} else "ni")
    labels = list(plan.question_surface_labels)
    fields = list(plan.selected_questions)
    if "address" in fields and plan.location_phrase:
        idx = fields.index("address")
        labels[idx] = _compose_address_question(plan) or labels[idx]
    return compose_customer_question_block(
        tuple(fields),
        tuple(labels),
        language=language,
        register=register,
    )


def _join_questions_en(questions: tuple[str, ...]) -> str:
    if not questions:
        return ""
    standalone = [_is_standalone_question(q) for q in questions]
    if len(questions) == 1:
        q = questions[0].rstrip(".?")
        if standalone[0]:
            return q if q.endswith("?") else q + "?"
        return f"Could you please send {q}?"
    if any(standalone):
        parts: list[str] = []
        for q, is_standalone in zip(questions, standalone):
            cleaned = q.rstrip(".?")
            if is_standalone:
                parts.append(cleaned if cleaned.endswith("?") else cleaned + "?")
            else:
                parts.append(f"could you please send {cleaned}")
        body = ", ".join(parts[:-1]) + f", and {parts[-1]}"
        return body[0].upper() + body[1:]
    joined = ", ".join(q.rstrip(".") for q in questions[:-1])
    last = questions[-1].rstrip(".")
    return f"Could you please send {joined}, and {last}?"


def _support_acknowledgement(plan: CustomerReplyPlanV2) -> str:
    if plan.language == "en":
        if "solar" in " ".join(plan.verified_facts).lower() or "sol" in plan.acknowledgement_statement.lower():
            return (
                "Thank you for getting in touch. I understand the solar installation has been performing poorly."
            )
        return "Thank you for getting in touch. I understand the charger has been performing poorly."
    if "sol" in plan.acknowledgement_statement.lower() or any(
        "solar" in f for f in plan.verified_facts
    ):
        return (
            "Tack för att du hör av dig om felet på den befintliga solcellsanläggningen."
        )
    return "Tack för att du hör av dig om felet på den befintliga laddboxen."


def compose_constrained_reply_hermetic(plan: CustomerReplyPlanV2) -> str:
    """Hermetic constrained-LLM composer: natural prose from approved plan fields only."""
    language = "en" if (plan.language or "sv").lower().startswith("en") else "sv"
    register = plan.salutation_strategy or ("du" if plan.service_family == "existing_installation_support" else "ni")
    closing = localized_closing(language=language)
    signature = f"\n\n{closing}\n{plan.signature_name}" if plan.signature_name else ""

    if plan.service_family == "existing_installation_support":
        ack = (plan.acknowledgement_statement or _support_acknowledgement(plan)).strip()
        questions = tuple(plan.question_surface_labels)
        if language == "en":
            q_block = _join_questions_en(questions) if questions else ""
            next_step = plan.next_step_statement or (
                "Once we have that information, we will review the details and decide how to handle the case."
                if questions
                else plan.next_step_statement
            )
        else:
            q_block = _render_question_block(plan) if questions else ""
            next_step = plan.next_step_statement or (
                "När vi har det går vi igenom uppgifterna och ser hur ärendet bör hanteras."
                if questions
                else plan.next_step_statement
            )
        middle = ack if not q_block else f"{ack}\n\n{q_block}\n\n{next_step}"
        return f"{plan.greeting}\n\n{middle}{signature}"

    ack = plan.acknowledgement_statement.strip()
    questions = tuple(plan.question_surface_labels)
    if plan.service_family == "job_status" and not questions:
        return f"{plan.greeting}\n\n{ack}\n\n{plan.next_step_statement}{signature}"

    if language == "en":
        q_block = _render_question_block(plan) if questions else ""
        next_step = plan.next_step_statement or localized_next_step(
            step_id="collect_minimum_site_facts",
            language=language,
            service_family=plan.service_family,
            has_questions=bool(questions),
        )
    else:
        q_block = _render_question_block(plan) if questions else ""
        next_step = plan.next_step_statement or localized_next_step(
            step_id="collect_minimum_site_facts",
            language=language,
            service_family=plan.service_family,
            has_questions=bool(questions),
        )

    if q_block:
        middle = f"{ack}\n\n{q_block}\n\n{next_step}"
    else:
        middle = f"{ack}\n\n{next_step}"
    return f"{plan.greeting}\n\n{middle}{signature}"


def render_constrained_llm_reply(
    plan: CustomerReplyPlanV2,
    *,
    require_live: bool = False,
    temperature: float | None = None,
    retry_attempts: int | None = None,
) -> tuple[str, dict[str, Any]]:
    """Render via constrained LLM path.

    Default: hermetic composer when live is disabled or fails.
    require_live=True: never fall back to hermetic; return empty body + failure meta.
    """
    payload = build_constrained_llm_payload(plan)
    payload_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    use_live = os.environ.get("DIGITAL_COWORKER_LLM_RENDER", "").lower() in {"1", "true", "live"}
    if require_live:
        use_live = True
    attempts = (
        max(1, int(retry_attempts))
        if retry_attempts is not None
        else max(1, int(os.environ.get("LLM_RETRY_ATTEMPTS", "1")))
    )
    if require_live:
        attempts = max(attempts, 2)
    temp = 0.0 if require_live and temperature is None else temperature
    meta: dict[str, Any] = {
        "prompt_version": PROMPT_VERSION,
        "model_id": MODEL_ID if use_live else None,
        "requested_model_id": MODEL_ID if use_live else None,
        "template_version": TEMPLATE_VERSION,
        "renderer_policy_version": RENDERER_POLICY_VERSION,
        "invocation_attempted": use_live,
        "live_call": False,
        "provider_outcome": "skipped" if not use_live else "pending",
        "validation_outcome": None,
        "payload_hash": payload_hash,
        "prompt_payload_hash": payload_hash,
        "provider_attempt_count": 0,
        "require_live": require_live,
    }
    if require_live and os.environ.get("DIGITAL_COWORKER_LLM_RENDER", "").lower() not in {
        "1",
        "true",
        "live",
    }:
        meta.update(
            {
                "provider_outcome": "blocked_llm_render_disabled",
                "invocation_attempted": False,
                "live_call": False,
            }
        )
        return "", meta

    if use_live:
        try:
            from app.ai.llm.client import get_llm_client

            client = get_llm_client()
            prompt = build_constrained_llm_prompt(plan)
            result = client.generate_json_detailed(
                prompt,
                model=MODEL_ID,
                retry_attempts=attempts,
                temperature=temp,
            )
            parsed = parse_llm_reply_output(result.output)
            usage = result.usage or {}
            meta.update(
                {
                    "live_call": True,
                    "provider_outcome": "success",
                    "returned_model": result.returned_model,
                    "returned_model_id": result.returned_model,
                    "finish_reason": result.finish_reason,
                    "usage": usage,
                    "prompt_tokens": int(usage.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage.get("completion_tokens") or 0),
                    "total_tokens": int(usage.get("total_tokens") or 0),
                    "provider_attempt_count": attempts,
                    "reply_body_source_key": parsed.source_key,
                }
            )
            return parsed.reply_body, meta
        except LLMReplyParseError as exc:
            meta.update(
                {
                    "live_call": True,
                    "live_call_failed": True,
                    "provider_outcome": "parse_failed",
                    "provider_error_type": type(exc).__name__,
                    "provider_error_detail": str(exc),
                    "provider_attempt_count": attempts,
                }
            )
            if require_live:
                return "", meta
        except Exception as exc:
            meta.update(
                {
                    "live_call": True,
                    "live_call_failed": True,
                    "provider_outcome": "failed",
                    "provider_error_type": type(exc).__name__,
                    "provider_attempt_count": attempts,
                }
            )
            if require_live:
                return "", meta
    if require_live:
        meta["provider_outcome"] = meta.get("provider_outcome") or "failed"
        return "", meta
    body = compose_constrained_reply_hermetic(plan)
    meta["composer"] = "hermetic_constrained_v4"
    meta["provider_outcome"] = meta.get("provider_outcome") or "skipped"
    return body, meta
