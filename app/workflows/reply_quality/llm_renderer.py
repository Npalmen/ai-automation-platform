"""Constrained LLM renderer and hermetic composer for coworker replies."""

from __future__ import annotations

import json
import os
from typing import Any

from app.workflows.reply_quality.customer_surface import localized_next_step
from app.workflows.reply_quality.llm_reply_parser import LLMReplyParseError, parse_llm_reply_output
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.reply_language import localized_closing

PROMPT_VERSION = "coworker_constrained_llm_v4"
MODEL_ID = "gpt-4o-mini"
TEMPLATE_VERSION = "digital_coworker_constrained_llm_v4"
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
    return {
        "language": plan.language,
        "pronoun_register": pronoun,
        "greeting": plan.greeting,
        "acknowledgement_statement": plan.acknowledgement_statement,
        "approved_questions": list(plan.question_surface_labels),
        "selected_question_ids": list(plan.selected_questions),
        "next_step_statement": plan.next_step_statement,
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
    else:
        pronoun_rule = _PRONOUN_RULES_SV.get(register, _PRONOUN_RULES_SV["ni"])

    return (
        "Compose a natural customer email reply using ONLY the approved fields in the JSON payload.\n"
        'Return JSON: {"reply_body": "<full email text>"}\n'
        "Hard rules:\n"
        f"- Language: {plan.language}. {pronoun_rule}\n"
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


def _join_questions_sv(questions: tuple[str, ...], register: str) -> str:
    if not questions:
        return ""
    if len(questions) == 1:
        q = questions[0].rstrip(".?")
        if q.lower().startswith(("vilken ", "which ", "vad ", "what ", "när ", "when ")):
            return q if q.endswith("?") else q + "?"
        if register == "du":
            return f"Kan du skicka {q}?"
        return f"Kan ni skicka {q}?"
    joined = ", ".join(q.rstrip(".?") for q in questions[:-1])
    last = questions[-1].rstrip(".?")
    if register == "du":
        return f"Kan du skicka {joined} och {last}?"
    return f"Kan ni skicka {joined} och {last}?"


def _render_question_block(plan: CustomerReplyPlanV2) -> str:
    language = "en" if (plan.language or "sv").lower().startswith("en") else "sv"
    register = plan.salutation_strategy or ("du" if plan.service_family == "existing_installation_support" else "ni")
    labels = list(plan.question_surface_labels)
    fields = list(plan.selected_questions)
    if "address" in fields and plan.location_phrase:
        idx = fields.index("address")
        labels[idx] = _compose_address_question(plan) or labels[idx]
    questions = tuple(labels)
    if language == "en":
        return _join_questions_en(questions)
    return _join_questions_sv(questions, register)


def _join_questions_en(questions: tuple[str, ...]) -> str:
    if not questions:
        return ""
    if len(questions) == 1:
        return f"Could you please send {questions[0].rstrip('.')}?"
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
        ack = _support_acknowledgement(plan)
        questions = tuple(plan.question_surface_labels)
        if language == "en":
            q_block = _join_questions_en(questions) if questions else ""
            next_step = (
                "Once we have that information, we will review the details and decide how to handle the case."
                if questions
                else plan.next_step_statement
            )
        else:
            q_block = _render_question_block(plan) if questions else ""
            next_step = (
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


def render_constrained_llm_reply(plan: CustomerReplyPlanV2) -> tuple[str, dict[str, Any]]:
    """Render via constrained LLM path. Hermetic composer only when live is disabled or fails."""
    payload = build_constrained_llm_payload(plan)
    use_live = os.environ.get("DIGITAL_COWORKER_LLM_RENDER", "").lower() in {"1", "true", "live"}
    retry_attempts = max(1, int(os.environ.get("LLM_RETRY_ATTEMPTS", "1")))
    meta: dict[str, Any] = {
        "prompt_version": PROMPT_VERSION,
        "model_id": MODEL_ID if use_live else None,
        "template_version": TEMPLATE_VERSION,
        "invocation_attempted": use_live,
        "live_call": False,
        "provider_outcome": "skipped",
        "validation_outcome": None,
        "payload_hash": json.dumps(payload, sort_keys=True)[:64],
    }
    if use_live:
        try:
            from app.ai.llm.client import get_llm_client

            client = get_llm_client()
            prompt = build_constrained_llm_prompt(plan)
            result = client.generate_json_detailed(
                prompt,
                model=MODEL_ID,
                retry_attempts=retry_attempts,
            )
            parsed = parse_llm_reply_output(result.output)
            meta.update(
                {
                    "live_call": True,
                    "provider_outcome": "success",
                    "returned_model": result.returned_model,
                    "finish_reason": result.finish_reason,
                    "usage": result.usage,
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
                }
            )
        except Exception as exc:
            meta.update(
                {
                    "live_call": True,
                    "live_call_failed": True,
                    "provider_outcome": "failed",
                    "provider_error_type": type(exc).__name__,
                }
            )
    body = compose_constrained_reply_hermetic(plan)
    meta["composer"] = "hermetic_constrained_v4"
    return body, meta
