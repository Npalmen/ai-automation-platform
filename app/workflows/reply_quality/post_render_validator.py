"""Post-render deterministic validation for coworker replies."""

from __future__ import annotations

import re
from typing import Any

from app.workflows.reply_candidate_safety import assess_reply_candidate_safety
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.surface_contract import (
    detect_internal_metadata_leaks,
    detect_mixed_language,
    detect_semantic_placeholders,
    detect_unlocalized_fact_labels,
    detect_unresolved_placeholders,
    validate_customer_surface,
)

POLICY_VERSION = "post_render_validator_v1"

_GENERIC_NEXT_STEP_SV = "när vi har det underlaget går vi igenom förutsättningarna och återkommer"
_GRAMMATICAL_BAD_SV = re.compile(r"\bbehöver vi vilken\b|\bbehöver vi vad\b|\bbehöver vi när\b", re.I)


def _lang(plan: CustomerReplyPlanV2) -> str:
    return "en" if (plan.language or "sv").lower().startswith("en") else "sv"


def _pronoun_violations(body: str, *, register: str, language: str) -> list[str]:
    issues: list[str] = []
    if language != "sv":
        return issues
    has_du = bool(re.search(r"\b(du|dig|din|ditt|dina)\b", body, re.I))
    has_ni = bool(re.search(r"\b(ni|er|ert|era)\b", body, re.I))
    if register == "du" and has_ni:
        issues.append("pronoun_register:ni_in_du_reply")
    if register == "ni" and has_du:
        issues.append("pronoun_register:du_in_ni_reply")
    if has_du and has_ni:
        issues.append("pronoun_register:mixed_du_ni")
    return issues


def validate_post_render_reply(
    *,
    plan: CustomerReplyPlanV2,
    body: str,
) -> dict[str, Any]:
    issues: list[str] = []
    language = _lang(plan)
    register = plan.salutation_strategy or "ni"

    surface = validate_customer_surface(body, expected_language=language)
    issues.extend(surface.get("issues") or [])
    issues.extend(detect_semantic_placeholders(body))
    issues.extend(_pronoun_violations(body, register=register, language=language))

    if _GRAMMATICAL_BAD_SV.search(body or ""):
        issues.append("grammatical_question_composition:awkward_need_phrase")

    normalized = (body or "").lower()
    for label in plan.question_surface_labels:
        if not label:
            continue
        if label.lower() in normalized:
            continue
        if plan.service_family == "job_status":
            continue
        tokens = [t for t in re.split(r"\W+", label.lower()) if len(t) > 4]
        if tokens and any(t in normalized for t in tokens[:2]):
            continue
        issues.append(f"missing_required_question:{label[:40]}")

    for fact in plan.facts_not_allowed_to_repeat:
        token = fact.replace("internal_", "").replace("_", " ")
        if token and token in normalized:
            issues.append(f"reask_known_fact:{fact}")

    if "kompletteringen" in normalized and "kompletterande information" not in (
        plan.acknowledgement_statement or ""
    ).lower():
        issues.append("acknowledgement:unsupported_completion_claim")

    safety = assess_reply_candidate_safety(body)
    if not safety.get("passed"):
        issues.extend(safety.get("violations") or [])

    return {
        "passed": not issues and safety.get("passed", True),
        "issues": issues,
        "safety": safety,
        "surface": surface,
        "policy_version": POLICY_VERSION,
    }
