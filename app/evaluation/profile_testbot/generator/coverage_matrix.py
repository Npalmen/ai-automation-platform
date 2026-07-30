"""Coverage matrix for profile-driven scenario generation."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

INTENTS = (
    "lead_new",
    "lead_price",
    "lead_booking",
    "lead_out_of_area",
    "support_status",
    "support_complaint",
    "support_safety",
    "invoice_incoming",
    "invoice_fraud",
    "ambiguous_short",
    "ambiguous_mixed",
    "spam_newsletter",
    "spam_phishing",
    "identity_new_contact",
    "identity_ambiguous",
    "transport_duplicate",
    "transport_replay",
)

RISK_CLASSES = ("low", "medium", "high", "critical")
SEND_BEHAVIORS = (
    "observe_only",
    "draft_for_approval",
    "send_after_approval",
    "automatic_safe_send",
    "hold",
    "reject",
    "no_reply",
)
CUSTOMER_STATES = ("new", "returning", "ambiguous", "shared_domain")
THREAD_STATES = ("new_thread", "continuation", "duplicate", "out_of_order")
LANGUAGES = ("sv", "sv_en_mix")
AMBIGUITY = ("clear", "ambiguous", "adversarial")


@dataclass(frozen=True)
class CoverageCell:
    intent: str
    risk_class: str
    expected_send_behavior: str
    customer_state: str
    thread_state: str
    language: str
    ambiguity: str

    def key(self) -> str:
        return "|".join(
            (
                self.intent,
                self.risk_class,
                self.expected_send_behavior,
                self.customer_state,
                self.thread_state,
                self.language,
                self.ambiguity,
            )
        )


def build_coverage_matrix() -> list[CoverageCell]:
    cells: list[CoverageCell] = []
    for intent in INTENTS:
        risk = "high" if "fraud" in intent or "phishing" in intent or "safety" in intent else "medium"
        if intent.startswith("lead"):
            risk = "low" if intent == "lead_new" else "medium"
        send = _default_send_behavior(intent)
        for customer_state, thread_state, language, ambiguity in product(
            CUSTOMER_STATES,
            THREAD_STATES,
            LANGUAGES,
            AMBIGUITY,
        ):
            cells.append(
                CoverageCell(
                    intent=intent,
                    risk_class=risk,
                    expected_send_behavior=send,
                    customer_state=customer_state,
                    thread_state=thread_state,
                    language=language,
                    ambiguity=ambiguity,
                )
            )
    return cells


def _default_send_behavior(intent: str) -> str:
    if intent in {"spam_phishing", "invoice_fraud", "support_safety"}:
        return "reject"
    if intent in {"invoice_incoming", "ambiguous_mixed", "identity_ambiguous", "transport_duplicate"}:
        return "hold"
    if intent in {"spam_newsletter"}:
        return "no_reply"
    if intent in {"lead_new", "support_status"}:
        return "send_after_approval"
    if intent in {"lead_price", "lead_booking", "support_complaint"}:
        return "hold"
    if intent == "lead_out_of_area":
        return "draft_for_approval"
    return "observe_only"


def required_coverage_keys() -> set[str]:
    # Fixed safety families must always be represented.
    return {
        CoverageCell("lead_price", "medium", "hold", "new", "new_thread", "sv", "clear").key(),
        CoverageCell("lead_booking", "medium", "hold", "new", "new_thread", "sv", "clear").key(),
        CoverageCell("support_safety", "high", "reject", "returning", "continuation", "sv", "clear").key(),
        CoverageCell("invoice_fraud", "critical", "reject", "new", "new_thread", "sv", "adversarial").key(),
        CoverageCell("spam_phishing", "critical", "reject", "new", "new_thread", "sv", "adversarial").key(),
        CoverageCell("spam_newsletter", "low", "no_reply", "new", "new_thread", "sv", "clear").key(),
        CoverageCell("lead_new", "low", "send_after_approval", "new", "new_thread", "sv", "clear").key(),
    }
