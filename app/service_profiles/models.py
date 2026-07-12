"""ServiceProfile — core data model for service-type-aware qualification.

Design principles:
- Frozen dataclass: profiles are defined once at import time, never mutated.
- Each profile owns its keyword list, required/optional fields, risk flags,
  routing defaults, and Swedish follow-up question labels.
- The four-level hierarchy: general_core → family → service_profile → tenant.
  Tenant overrides are applied via apply_tenant_overrides() in qualification.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServiceProfile:
    """A qualification schema and routing descriptor for a specific service type.

    Attributes:
        service_type:       Machine-readable type key, e.g. "ev_charger_installation".
        family:             Service family: "installation_service" | "generic_business".
        keywords:           Swedish/English keyword signals that identify this service.
        required_fields:    Fields that must be present for a complete qualification.
        optional_fields:    Fields that improve quality but are not blocking.
        risk_flags:         Phrases that, if found in text, trigger high_risk_action.
        default_route:      Where complete, non-risky jobs go: "sales" | "support"
                            | "invoice" | "manual_review".
        missing_info_action: Action when required fields are missing: "ask_questions"
                            | "manual_review".
        complete_action:    Action when all required fields are present: "create_offer_draft"
                            | "create_task" | "auto_process" | "manual_review".
        high_risk_action:   Action when risk_flags are detected — always "manual_review".
        follow_up_intro:    Swedish opening sentence for the customer question message.
        follow_up_questions: Mapping of field name → Swedish label used in question message.
    """

    service_type: str
    family: str
    keywords: tuple[str, ...]
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    risk_flags: tuple[str, ...]
    default_route: str
    missing_info_action: str
    complete_action: str
    high_risk_action: str
    follow_up_intro: str
    reply_opener: str = ""
    follow_up_questions: dict[str, str] = field(default_factory=dict)

    def is_high_risk(self, text: str) -> bool:
        """Return True if any risk_flag phrase appears in *text* (case-insensitive)."""
        lower = text.lower()
        return any(flag.lower() in lower for flag in self.risk_flags)

    def resolve_action(self, is_complete: bool, text: str = "") -> str:
        """Return the recommended next action given completeness and content risk."""
        if self.is_high_risk(text):
            return self.high_risk_action
        if not is_complete:
            return self.missing_info_action
        return self.complete_action
