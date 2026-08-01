"""Profile-driven missing-fact policy contract (Todo E).

Deterministic, versioned selection of follow-up questions per service profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.service_profiles.models import ServiceProfile
from app.service_profiles.qualification import (
    _GENERIC_FIELD_LABELS,
    compute_playbook_questions,
    compute_profile_missing_info,
    select_profile,
)

POLICY_VERSION = "missing_fact_plan_v1"
PROFILE_VERSION = "service_profiles_v1"
DEFAULT_MAX_QUESTIONS = 4

# Fields that must never be requested in customer email.
_SENSITIVE_EMAIL_FIELDS = frozenset(
    {
        "personnummer",
        "social_security_number",
        "bank_account",
        "password",
        "credit_card",
    }
)

# Plan-facing service type aliases (evidence only).
SERVICE_TYPE_LABELS: dict[str, str] = {
    "solar_installation": "solar installation",
    "battery_storage": "battery installation",
    "ev_charger_installation": "EV charger",
    "solar_service": "existing installation support",
    "generic_support": "existing installation support",
    "ev_charger_fault": "existing installation support",
    "generic_lead": "general consultation",
    "unknown": "unknown service",
}


@dataclass(frozen=True)
class MissingFactPlan:
    service_type: str
    known_facts: tuple[str, ...]
    missing_required_facts: tuple[str, ...]
    selected_questions: tuple[str, ...]
    selected_question_labels: tuple[str, ...]
    deferred_questions: tuple[str, ...]
    sensitive_facts_blocked: tuple[str, ...]
    max_questions_applied: int
    rule_trace: tuple[str, ...]
    profile_version: str
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_type": self.service_type,
            "known_facts": list(self.known_facts),
            "missing_required_facts": list(self.missing_required_facts),
            "selected_questions": list(self.selected_questions),
            "selected_question_labels": list(self.selected_question_labels),
            "deferred_questions": list(self.deferred_questions),
            "sensitive_facts_blocked": list(self.sensitive_facts_blocked),
            "max_questions_applied": self.max_questions_applied,
            "rule_trace": list(self.rule_trace),
            "profile_version": self.profile_version,
            "policy_version": self.policy_version,
        }


def _question_label(profile: ServiceProfile, field: str) -> str:
    return (
        profile.follow_up_questions.get(field)
        or _GENERIC_FIELD_LABELS.get(field)
        or field.replace("_", " ").capitalize()
    )


def _filter_sensitive(fields: list[str]) -> tuple[list[str], list[str]]:
    allowed: list[str] = []
    blocked: list[str] = []
    for field in fields:
        if field in _SENSITIVE_EMAIL_FIELDS:
            blocked.append(field)
        else:
            allowed.append(field)
    return allowed, blocked


def build_missing_fact_plan(
    *,
    input_data: dict[str, Any],
    entities: dict[str, Any] | None = None,
    detected_job_type: str = "lead",
    lead_type: str | None = None,
    service_type: str | None = None,
    max_questions: int = DEFAULT_MAX_QUESTIONS,
    tenant_ctx: Any = None,
) -> MissingFactPlan:
    """Build a deterministic missing-fact plan from profile and known facts."""
    entities = dict(entities or {})
    text = f"{input_data.get('subject') or ''} {input_data.get('message_text') or ''}".strip()
    profile = select_profile(
        job_type=detected_job_type,
        lead_type=lead_type,
        text=text or None,
        tenant_ctx=tenant_ctx,
    )
    if service_type:
        from app.service_profiles.registry import get_profile

        override = get_profile(service_type)
        if override is not None:
            profile = override

    if profile.service_type == "generic_lead" and text:
        from app.service_profiles.registry import _REGISTRY

        lower = text.lower()
        for candidate in _REGISTRY.values():
            if candidate.service_type == "generic_lead":
                continue
            if any(kw in lower for kw in candidate.keywords):
                profile = candidate
                break

    missing_info = compute_profile_missing_info(
        profile,
        input_data,
        entities=entities,
        tenant_ctx=tenant_ctx,
    )
    playbook = compute_playbook_questions(
        profile,
        input_data,
        entities=entities,
        max_questions=max_questions,
    )

    known = tuple(sorted(missing_info.get("present_fields") or []))
    missing_required = tuple(missing_info.get("missing_fields") or [])
    selected_raw = list(playbook.get("selected_fields") or [])
    selected_raw, sensitive_blocked = _filter_sensitive(selected_raw)

    labels = [_question_label(profile, field) for field in selected_raw]
    deferred = tuple(
        f for f in missing_required if f not in selected_raw
    ) + tuple(playbook.get("suppressed_fields") or ())

    trace: list[str] = [
        f"profile={profile.service_type}",
        f"context={playbook.get('service_context')}",
        f"schema_source={missing_info.get('schema_source')}",
        f"max_questions={max_questions}",
        f"selected={','.join(selected_raw) or 'none'}",
    ]
    if playbook.get("suppressed_fields"):
        trace.append(f"suppressed={','.join(playbook['suppressed_fields'])}")

    return MissingFactPlan(
        service_type=profile.service_type,
        known_facts=known,
        missing_required_facts=missing_required,
        selected_questions=tuple(selected_raw),
        selected_question_labels=tuple(labels),
        deferred_questions=tuple(deferred),
        sensitive_facts_blocked=tuple(sensitive_blocked),
        max_questions_applied=max_questions,
        rule_trace=tuple(trace),
        profile_version=PROFILE_VERSION,
        policy_version=POLICY_VERSION,
    )
