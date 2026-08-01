"""Reply planning, rendering and internal operator notes (Todo F).

Separates customer reply plan, deterministic rendering, and internal notes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflows.missing_fact_plan import MissingFactPlan
from app.workflows.safe_ack_eligibility import SafeAckEligibilityResult

POLICY_VERSION = "reply_planning_v1"
FALLBACK_TEMPLATE_KEY = "safe_ack_incomplete_lead_v1"

_SERVICE_DISPLAY: dict[str, str] = {
    "solar_installation": "solcellsinstallation",
    "battery_storage": "batterilager",
    "ev_charger_installation": "laddboxinstallation",
    "solar_service": "befintlig solcellsanläggning",
    "ev_charger_fault": "laddbox",
    "generic_lead": "din förfrågan",
    "generic_support": "ditt ärende",
}


@dataclass(frozen=True)
class CustomerReplyPlan:
    acknowledgement_intent: str
    verified_facts: tuple[str, ...]
    service_hint: str
    location_hint: str
    missing_questions: tuple[str, ...]
    forbidden_commitments: tuple[str, ...]
    language: str
    tone: str
    next_step_wording: str
    greeting: str
    signature_name: str
    profile_service_type: str
    fallback_template_key: str
    plan_provenance: tuple[str, ...]
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "acknowledgement_intent": self.acknowledgement_intent,
            "verified_facts": list(self.verified_facts),
            "service_hint": self.service_hint,
            "location_hint": self.location_hint,
            "missing_questions": list(self.missing_questions),
            "forbidden_commitments": list(self.forbidden_commitments),
            "language": self.language,
            "tone": self.tone,
            "next_step_wording": self.next_step_wording,
            "greeting": self.greeting,
            "signature_name": self.signature_name,
            "profile_service_type": self.profile_service_type,
            "fallback_template_key": self.fallback_template_key,
            "plan_provenance": list(self.plan_provenance),
            "policy_version": self.policy_version,
        }


@dataclass(frozen=True)
class InternalOperatorNote:
    risk_indicators: tuple[str, ...]
    threat_evidence: tuple[dict[str, Any], ...]
    extracted_facts: tuple[dict[str, Any], ...]
    conflicts: tuple[str, ...]
    recommended_manual_action: str
    hold_reason: str
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_indicators": list(self.risk_indicators),
            "threat_evidence": list(self.threat_evidence),
            "extracted_facts": list(self.extracted_facts),
            "conflicts": list(self.conflicts),
            "recommended_manual_action": self.recommended_manual_action,
            "hold_reason": self.hold_reason,
            "policy_version": self.policy_version,
            "no_customer_facing_text": True,
        }


def _resolve_service_hint(
    *,
    service_type: str,
    entities: dict[str, Any],
    fact_map: dict[str, str | None],
) -> str:
    requested = fact_map.get("requested_service") or entities.get("requested_service")
    if requested and str(requested).strip():
        value = str(requested).strip()
        lowered = value.lower()
        if lowered in {"price quote", "send price", "send price quote"}:
            return _SERVICE_DISPLAY.get(service_type, "din förfrågan")
        return value
    return _SERVICE_DISPLAY.get(service_type, "din förfrågan")


def _resolve_location_hint(entities: dict[str, Any], fact_map: dict[str, str | None]) -> str:
    for key in ("city", "address", "location"):
        value = fact_map.get(key) or entities.get(key)
        if value and str(value).strip():
            return str(value).strip()
    return ""


def build_customer_reply_plan(
    *,
    greeting: str,
    signature_name: str,
    missing_fact_plan: MissingFactPlan,
    eligibility: SafeAckEligibilityResult,
    entities: dict[str, Any] | None = None,
    fact_map: dict[str, str | None] | None = None,
    language: str = "sv",
    tone: str = "professional",
) -> CustomerReplyPlan | None:
    if not eligibility.eligible:
        return None

    entities = dict(entities or {})
    fact_map = dict(fact_map or {})

    verified: list[str] = []
    if missing_fact_plan.known_facts:
        verified.extend(missing_fact_plan.known_facts)
    location = _resolve_location_hint(entities, fact_map)
    if location:
        verified.append(f"location:{location}")

    service_hint = _resolve_service_hint(
        service_type=missing_fact_plan.service_type,
        entities=entities,
        fact_map=fact_map,
    )

    provenance = (
        f"eligibility:{eligibility.policy_version}",
        f"missing_facts:{missing_fact_plan.policy_version}",
        f"profile:{missing_fact_plan.profile_version}",
        *missing_fact_plan.rule_trace,
    )

    return CustomerReplyPlan(
        acknowledgement_intent="safe_incomplete_lead_ack",
        verified_facts=tuple(verified),
        service_hint=service_hint,
        location_hint=location,
        missing_questions=missing_fact_plan.selected_question_labels,
        forbidden_commitments=eligibility.forbidden_commitments,
        language=language,
        tone=tone,
        next_step_wording="Förfrågan granskas av oss innan vi återkommer.",
        greeting=greeting,
        signature_name=signature_name,
        profile_service_type=missing_fact_plan.service_type,
        fallback_template_key=FALLBACK_TEMPLATE_KEY,
        plan_provenance=provenance,
        policy_version=POLICY_VERSION,
    )


def render_customer_reply(plan: CustomerReplyPlan, *, use_fallback: bool = False) -> str:
    """Render customer reply text strictly from plan fields."""
    ack = "Tack för din förfrågan. Vi tittar på den och återkommer."
    if use_fallback or plan.fallback_template_key == FALLBACK_TEMPLATE_KEY and not plan.missing_questions:
        ack = "Tack för din förfrågan. Vi har tagit emot den och återkommer."

    service_line = ""
    if plan.service_hint and plan.service_hint != "din förfrågan":
        service_line = f"\n\nVi ser att du vill ha hjälp med {plan.service_hint}."
        if plan.location_hint:
            service_line = (
                f"\n\nVi ser att du vill ha hjälp med {plan.service_hint} i {plan.location_hint}."
            )
    elif plan.location_hint:
        service_line = f"\n\nVi ser att ditt ärende gäller {plan.location_hint}."

    question_block = "\n".join(f"- {item}" for item in plan.missing_questions)
    if not question_block:
        question_block = "- Namn\n- Telefonnummer\n- Adress"

    closing = f"\n\nVänliga hälsningar\n{plan.signature_name}" if plan.signature_name else ""
    return (
        f"{plan.greeting}\n\n"
        f"{ack}"
        f"{service_line}\n\n"
        "För att vi ska kunna gå vidare behöver vi:\n"
        f"{question_block}\n\n"
        f"{plan.next_step_wording}"
        f"{closing}"
    )


def build_internal_operator_note(
    *,
    threat_assessment: dict[str, Any] | None = None,
    extracted_fact_set: dict[str, Any] | None = None,
    eligibility: SafeAckEligibilityResult | None = None,
    hold_reason: str | None = None,
    risk_categories: list[str] | None = None,
) -> InternalOperatorNote:
    """Build internal-only operator note — never used as customer delivery payload."""
    threat = threat_assessment or {}
    facts = list((extracted_fact_set or {}).get("facts") or [])
    risk_indicators: list[str] = list(risk_categories or [])
    if threat.get("threat_class"):
        risk_indicators.append(f"threat:{threat['threat_class']}")
    if threat.get("detected_signals"):
        risk_indicators.extend(str(s) for s in threat["detected_signals"])

    conflicts: list[str] = []
    if eligibility and eligibility.blocker_codes:
        conflicts.extend(eligibility.blocker_codes)

    reason = hold_reason or ""
    if not reason and eligibility and eligibility.blocker_codes:
        reason = ", ".join(eligibility.blocker_codes)
    if not reason and threat.get("threat_class"):
        reason = f"threat_{threat['threat_class']}"

    recommended = "manual_review"
    if threat.get("required_routing") == "security_review":
        recommended = "security_review"
    elif threat.get("required_routing") == "reject":
        recommended = "reject_no_reply"

    return InternalOperatorNote(
        risk_indicators=tuple(sorted(set(risk_indicators))),
        threat_evidence=tuple(threat.get("evidence_spans") or ()),
        extracted_facts=tuple(facts),
        conflicts=tuple(conflicts),
        recommended_manual_action=recommended,
        hold_reason=reason,
        policy_version=POLICY_VERSION,
    )


def render_internal_operator_note(note: InternalOperatorNote) -> str:
    """Render internal operator note for handoff — not for customer delivery."""
    lines = [
        "INTERN OPERATÖRSANTECKNING — ej för kundleverans",
        f"Anledning: {note.hold_reason or 'n/a'}",
        f"Rekommenderad åtgärd: {note.recommended_manual_action}",
    ]
    if note.risk_indicators:
        lines.append(f"Riskindikatorer: {', '.join(note.risk_indicators)}")
    if note.extracted_facts:
        fact_lines = [
            f"  - {f.get('field_name')}: {f.get('normalized_value')}"
            for f in note.extracted_facts
            if f.get("fact_status") != "excluded"
        ]
        if fact_lines:
            lines.append("Extraherade fakta:")
            lines.extend(fact_lines)
    if note.conflicts:
        lines.append(f"Konflikter/blockeringar: {', '.join(note.conflicts)}")
    return "\n".join(lines)
