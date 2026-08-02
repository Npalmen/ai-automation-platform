"""Versioned service playbooks for digital coworker replies (Todo B)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PLAYBOOK_VERSION = "reply_service_playbook_v1"

SERVICE_FAMILIES: tuple[str, ...] = (
    "solar_installation",
    "battery_installation",
    "ev_charger",
    "solar_battery_combined",
    "existing_installation_support",
    "job_status",
    "general_consultation",
    "complaint_warranty",
    "unknown_service",
)


@dataclass(frozen=True)
class ReplyServicePlaybook:
    playbook_id: str
    version: str
    service_family: str
    supported_intents: tuple[str, ...]
    next_step_options: tuple[str, ...]
    required_facts_by_next_step: dict[str, tuple[str, ...]]
    optional_high_value_facts: tuple[str, ...]
    forbidden_email_questions: tuple[str, ...]
    question_priority: tuple[str, ...]
    maximum_questions_first_reply: int
    maximum_questions_followup: int
    allowed_acknowledgement_modes: tuple[str, ...]
    reply_examples: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "playbook_id": self.playbook_id,
            "version": self.version,
            "service_family": self.service_family,
            "supported_intents": list(self.supported_intents),
            "next_step_options": list(self.next_step_options),
            "required_facts_by_next_step": {
                k: list(v) for k, v in self.required_facts_by_next_step.items()
            },
            "optional_high_value_facts": list(self.optional_high_value_facts),
            "forbidden_email_questions": list(self.forbidden_email_questions),
            "question_priority": list(self.question_priority),
            "maximum_questions_first_reply": self.maximum_questions_first_reply,
            "maximum_questions_followup": self.maximum_questions_followup,
            "allowed_acknowledgement_modes": list(self.allowed_acknowledgement_modes),
            "reply_examples": list(self.reply_examples),
        }


def _pb(
    family: str,
    *,
    intents: tuple[str, ...],
    next_steps: tuple[str, ...],
    required: dict[str, tuple[str, ...]],
    priority: tuple[str, ...],
    optional: tuple[str, ...] = (),
    forbidden: tuple[str, ...] = ("personnummer", "bank_account"),
    first_max: int = 4,
    follow_max: int = 3,
) -> ReplyServicePlaybook:
    return ReplyServicePlaybook(
        playbook_id=f"reply_{family}_v1",
        version=PLAYBOOK_VERSION,
        service_family=family,
        supported_intents=intents,
        next_step_options=next_steps,
        required_facts_by_next_step=required,
        optional_high_value_facts=optional,
        forbidden_email_questions=forbidden,
        question_priority=priority,
        maximum_questions_first_reply=first_max,
        maximum_questions_followup=follow_max,
        allowed_acknowledgement_modes=(
            "receipt_acknowledgement",
            "information_request",
            "support_acknowledgement",
            "status_acknowledgement",
        ),
        reply_examples=(),
    )


_PLAYBOOKS: dict[str, ReplyServicePlaybook] = {
    "solar_installation": _pb(
        "solar_installation",
        intents=("lead", "lead_new"),
        next_steps=("collect_minimum_site_facts", "clarify_service_scope"),
        required={
            "collect_minimum_site_facts": (
                "address",
                "property_type",
                "roof_type",
                "annual_consumption",
            ),
            "clarify_service_scope": ("requested_service", "address"),
        },
        priority=(
            "address",
            "property_type",
            "roof_type",
            "annual_consumption",
            "battery_interest",
            "existing_installation",
            "attachment",
        ),
        optional=("battery_interest", "existing_installation"),
    ),
    "battery_storage": _pb(
        "battery_installation",
        intents=("lead", "lead_new"),
        next_steps=("collect_minimum_site_facts", "clarify_service_scope"),
        required={
            "collect_minimum_site_facts": (
                "existing_installation",
                "current_inverter",
                "intended_purpose",
                "address",
            ),
        },
        priority=(
            "existing_installation",
            "current_inverter",
            "intended_purpose",
            "address",
            "annual_consumption",
            "battery_preference",
            "existing_solar_system",
        ),
    ),
    "battery_installation": _pb(
        "battery_installation",
        intents=("lead", "lead_new"),
        next_steps=("collect_minimum_site_facts",),
        required={
            "collect_minimum_site_facts": (
                "existing_installation",
                "existing_solar_system",
                "current_inverter",
                "address",
            ),
        },
        priority=(
            "existing_installation",
            "existing_solar_system",
            "current_inverter",
            "intended_purpose",
            "address",
            "annual_consumption",
        ),
    ),
    "ev_charger_installation": _pb(
        "ev_charger",
        intents=("lead", "lead_new"),
        next_steps=("collect_minimum_site_facts",),
        required={
            "collect_minimum_site_facts": (
                "property_type",
                "address",
                "charging_points",
                "main_fuse",
            ),
        },
        priority=(
            "property_type",
            "address",
            "charging_points",
            "main_fuse",
            "load_balancing_need",
            "housing_association_context",
        ),
    ),
    "solar_battery_combined_install": _pb(
        "solar_battery_combined",
        intents=("lead", "lead_new"),
        next_steps=("collect_minimum_site_facts",),
        required={
            "collect_minimum_site_facts": (
                "address",
                "roof_type",
                "annual_consumption",
                "energy_priority_goal",
            ),
        },
        priority=(
            "address",
            "roof_type",
            "annual_consumption",
            "energy_priority_goal",
            "battery_preference",
            "property_type",
            "attachment",
        ),
        optional=("battery_preference",),
    ),
    "ev_charger_fault": _pb(
        "existing_installation_support",
        intents=("support_status", "support_complaint"),
        next_steps=("route_to_manual_technical_review", "collect_symptom_facts"),
        required={
            "collect_symptom_facts": (
                "system_type",
                "symptom",
                "when_started",
                "safety_state",
            ),
        },
        priority=(
            "system_type",
            "symptom",
            "when_started",
            "error_code",
            "safety_state",
            "case_reference",
            "attachment",
        ),
    ),
    "solar_service": _pb(
        "existing_installation_support",
        intents=("support_status", "support_complaint"),
        next_steps=("collect_symptom_facts", "route_to_manual_technical_review"),
        required={
            "collect_symptom_facts": ("system_type", "symptom", "when_started"),
        },
        priority=(
            "system_type",
            "symptom",
            "when_started",
            "error_code",
            "safety_state",
            "attachment",
        ),
    ),
    "generic_support": _pb(
        "existing_installation_support",
        intents=("support_status",),
        next_steps=("collect_symptom_facts", "confirm_case_receipt_only"),
        required={"collect_symptom_facts": ("issue_summary", "system_type")},
        priority=("issue_summary", "system_type", "when_started", "case_reference"),
    ),
    "generic_lead": _pb(
        "general_consultation",
        intents=("lead", "lead_new", "ambiguous_short"),
        next_steps=("clarify_service_scope", "collect_contact_preference"),
        required={"clarify_service_scope": ("requested_service", "address")},
        priority=("requested_service", "address", "project_description", "phone_or_email"),
    ),
    "unknown": _pb(
        "unknown_service",
        intents=("ambiguous_short", "ambiguous_mixed"),
        next_steps=("clarify_service_scope",),
        required={"clarify_service_scope": ("requested_service",)},
        priority=("requested_service", "address", "issue_summary"),
        first_max=3,
    ),
}

_STATUS_PLAYBOOK = _pb(
    "job_status",
    intents=("support_status",),
    next_steps=("provide_status_acknowledgement",),
    required={"provide_status_acknowledgement": ("case_reference", "customer_identifier")},
    priority=("case_reference", "customer_identifier", "status_dimension"),
    first_max=2,
)

_COMPLAINT_PLAYBOOK = _pb(
    "complaint_warranty",
    intents=("support_complaint",),
    next_steps=("route_to_manual_technical_review", "confirm_case_receipt_only"),
    required={
        "route_to_manual_technical_review": (
            "original_case",
            "issue_description",
            "discovery_time",
        ),
    },
    priority=(
        "original_case",
        "issue_description",
        "discovery_time",
        "evidence",
        "safety_relevance",
    ),
    forbidden=("personnummer", "bank_account", "technical_guarantee"),
)

_CONSULTATION_PLAYBOOKS: dict[str, ReplyServicePlaybook] = {
    "consultation_solar_vs_battery": _pb(
        "general_consultation",
        intents=("lead", "lead_new"),
        next_steps=("clarify_service_scope",),
        required={"clarify_service_scope": ("annual_consumption", "existing_installation", "intended_purpose")},
        priority=(
            "annual_consumption",
            "existing_installation",
            "intended_purpose",
            "property_type",
            "address",
            "battery_preference",
        ),
        first_max=4,
    ),
    "consultation_energy_storage": _pb(
        "general_consultation",
        intents=("lead", "lead_new"),
        next_steps=("clarify_service_scope",),
        required={"clarify_service_scope": ("existing_installation", "intended_purpose", "annual_consumption")},
        priority=(
            "existing_installation",
            "intended_purpose",
            "annual_consumption",
            "current_inverter",
            "address",
            "property_type",
        ),
        first_max=4,
    ),
    "consultation_charger_vs_solar": _pb(
        "general_consultation",
        intents=("lead", "lead_new"),
        next_steps=("clarify_service_scope",),
        required={
            "clarify_service_scope": (
                "annual_consumption",
                "ev_ownership_or_plan",
                "charging_need",
            ),
        },
        priority=(
            "annual_consumption",
            "ev_ownership_or_plan",
            "charging_need",
            "existing_installation",
            "energy_priority_goal",
            "address",
            "property_type",
        ),
        first_max=4,
    ),
    "consultation_booking": _pb(
        "general_consultation",
        intents=("lead", "lead_new"),
        next_steps=("collect_contact_preference",),
        required={"collect_contact_preference": ("preferred_call_times",)},
        priority=(
            "preferred_call_times",
            "consultation_focus",
            "preferred_contact_method",
        ),
        first_max=3,
        follow_max=2,
    ),
}


def get_consultation_playbook(consultation_intent: str) -> ReplyServicePlaybook:
    return _CONSULTATION_PLAYBOOKS.get(consultation_intent, _PLAYBOOKS["generic_lead"])


def map_service_type_to_family(service_type: str, *, business_intent: str | None = None) -> str:
    if business_intent in {"support_status"} and service_type in {"generic_support", "solar_service"}:
        return "job_status"
    if business_intent in {"support_complaint"}:
        return "complaint_warranty"
    playbook = _PLAYBOOKS.get(service_type)
    if playbook is None:
        return "unknown_service"
    return playbook.service_family


def get_reply_playbook(
    service_type: str,
    *,
    business_intent: str | None = None,
) -> ReplyServicePlaybook:
    if business_intent in {"support_complaint"}:
        return _COMPLAINT_PLAYBOOK
    if business_intent in {"support_status"} and service_type in {"generic_support"}:
        return _STATUS_PLAYBOOK
    if business_intent in {"support_status"} and service_type in {
        "solar_service",
        "ev_charger_fault",
        "generic_support",
    }:
        if service_type == "generic_support":
            return _STATUS_PLAYBOOK
        return _PLAYBOOKS.get("solar_service") or _PLAYBOOKS["generic_support"]
    playbook = _PLAYBOOKS.get(service_type)
    if playbook is not None:
        return playbook
    return _PLAYBOOKS["unknown"]
