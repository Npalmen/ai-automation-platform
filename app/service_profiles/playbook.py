"""Service Playbook architecture.

A ServicePlaybook is an industry/workflow instruction set that extends the
static ServiceProfile concept with context-specific behavior:

  - Which facts matter in which service context
  - Which questions to suppress in each context
  - Which extra fields are important (beyond the base profile required_fields)
  - How to prioritize questions for the current context
  - Cross-cutting risk/complaint override rules

Five playbooks cover the primary Krowolf service domains:
  A. electrical_installation
  B. ev_charger
  C. solar_battery
  D. vvs_plumbing
  E. building_carpentry

Plus a cross-cutting complaint override that takes precedence over any industry playbook.

Public API:
    get_playbook(service_type: str) -> ServicePlaybook | None
    get_complaint_override()        -> ComplaintOverride
    PlaybookContext                 — per-context behavior
    ServicePlaybook                 — full playbook definition
    ComplaintOverride               — cross-cutting complaint override
    select_questions_from_playbook  — returns ordered list of fields to ask
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── Data models ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PlaybookContext:
    """Context-specific behaviour within a playbook.

    priority_fields:   Ask these FIRST (most important for the current situation)
    suppress_fields:   NEVER ask these in this context
    extra_fields:      Additional fields to ask that are NOT in the base profile
    reply_strategy:    Short instruction for the reply opener / tone
    """
    priority_fields: tuple[str, ...]
    suppress_fields: tuple[str, ...]
    extra_fields: tuple[str, ...]
    reply_strategy: str = ""


@dataclass(frozen=True)
class ServicePlaybook:
    """Full service playbook definition.

    id:           Matches service_type from ServiceProfile
    name:         Human-readable Swedish name
    industry:     Industry family label
    applies_when: Brief description of when this playbook applies
    contexts:     ServiceContext → PlaybookContext mapping
    """
    id: str
    name: str
    industry: str
    applies_when: str
    contexts: dict[str, PlaybookContext] = field(default_factory=dict)


@dataclass(frozen=True)
class ComplaintOverride:
    """Cross-cutting complaint override.

    When complaint signals are detected, this overrides normal industry playbooks:
    - No technical troubleshooting questions
    - Calm acknowledgment reply strategy
    - Manual handling / no normal auto-reply
    """
    trigger_keywords: tuple[str, ...]
    suppress_all_technical_fields: bool
    reply_strategy: str
    internal_flag: str


# ── Playbook definitions ──────────────────────────────────────────────────────

# A. Electrical Installation Playbook
_ELECTRICAL_PLAYBOOK = ServicePlaybook(
    id="electrical_fault",
    name="Elinstallation & felsökning",
    industry="electrical",
    applies_when="Elfel, centralbyten, uttag/belysning, jordfelsbrytare, säkringsproblem",
    contexts={
        "new_installation": PlaybookContext(
            priority_fields=("property_type", "main_fuse", "address"),
            suppress_fields=(),
            extra_fields=("current_panel_age", "project_description"),
            reply_strategy="Acknowledge installation need. Ask about property, main fuse and timeline.",
        ),
        "repair_or_fault": PlaybookContext(
            priority_fields=("issue_description", "when_started", "affected_area"),
            suppress_fields=(),
            extra_fields=("error_code",),
            reply_strategy="Acknowledge fault. Ask for detailed description and timing.",
        ),
        "urgent_issue": PlaybookContext(
            priority_fields=("safety_risk", "issue_description"),
            suppress_fields=(),
            extra_fields=(),
            reply_strategy="Safety first. Do NOT send normal auto-reply. Trigger manual_review.",
        ),
    },
)

_ELECTRICAL_PANEL_PLAYBOOK = ServicePlaybook(
    id="electrical_panel",
    name="Elcentralbyte",
    industry="electrical",
    applies_when="Centralbyten, elcentraluppgradering, säkringsskåp",
    contexts={
        "replacement": PlaybookContext(
            priority_fields=("main_fuse", "current_panel_age", "property_type"),
            suppress_fields=(),
            extra_fields=("photo_request",),
            reply_strategy="Acknowledge panel replacement. Ask for photos and current panel details.",
        ),
        "new_installation": PlaybookContext(
            priority_fields=("property_type", "main_fuse", "address"),
            suppress_fields=(),
            extra_fields=(),
            reply_strategy="Acknowledge. Ask about property and current electrical capacity.",
        ),
    },
)

# B. EV Charger Playbook
_EV_CHARGER_PLAYBOOK = ServicePlaybook(
    id="ev_charger_installation",
    name="Laddbox installation",
    industry="ev_charging",
    applies_when="Ny laddbox, laddboxinstallation, hemmaladdning, elbil laddning",
    contexts={
        "new_installation": PlaybookContext(
            priority_fields=("main_fuse", "distance_panel_to_charger"),
            suppress_fields=("desired_location",),  # suppress generic placement if parking context given
            extra_fields=("charger_preference", "distance_panel_to_charger"),
            reply_strategy=(
                "Acknowledge charger install. Use customer's parking context. "
                "Ask main fuse softly if unknown. Ask distance from panel to charging location."
            ),
        ),
        "repair_or_fault": PlaybookContext(
            priority_fields=("issue_description", "when_started", "charger_model_or_brand"),
            suppress_fields=(
                "desired_location", "charger_count", "property_type",
                "annual_consumption", "installation_timeline",
            ),
            extra_fields=("error_code",),
            reply_strategy="Acknowledge fault. Ask model, symptom and when started.",
        ),
    },
)

_EV_CHARGER_FAULT_PLAYBOOK = ServicePlaybook(
    id="ev_charger_fault",
    name="Laddbox felsökning",
    industry="ev_charging",
    applies_when="Laddbox fungerar inte, laddar inte, laddboxfel",
    contexts={
        "repair_or_fault": PlaybookContext(
            priority_fields=("issue_description", "charger_model_or_brand", "when_started"),
            suppress_fields=("desired_location", "charger_count", "property_type"),
            extra_fields=("error_code",),
            reply_strategy="Acknowledge fault. Ask model, symptom description and when it started.",
        ),
    },
)

# C. Solar & Battery Playbook
_SOLAR_INSTALLATION_PLAYBOOK = ServicePlaybook(
    id="solar_installation",
    name="Solcellsinstallation",
    industry="solar_energy",
    applies_when="Ny solcellsinstallation, nyinstallation, solceller på ny fastighet",
    contexts={
        "new_installation": PlaybookContext(
            priority_fields=("roof_type", "main_fuse", "annual_consumption"),
            suppress_fields=("inverter_brand_model", "backup_requirement"),
            extra_fields=(),
            reply_strategy="Ask about roof type/photos, main fuse, annual consumption.",
        ),
        "price_shopping": PlaybookContext(
            priority_fields=("annual_consumption", "roof_type", "address"),
            suppress_fields=(),
            extra_fields=(),
            reply_strategy="Acknowledge interest. Ask for usage info to provide accurate estimate.",
        ),
    },
)

_BATTERY_PLAYBOOK = ServicePlaybook(
    id="battery_storage",
    name="Batterilager & add-on",
    industry="solar_energy",
    applies_when="Batteri till befintliga solceller, batterilager, energilager",
    contexts={
        "add_on_existing": PlaybookContext(
            priority_fields=(
                "inverter_brand_model",
                "backup_requirement",
                "main_fuse",
            ),
            suppress_fields=(
                "property_type",
                "roof_type",
                "annual_consumption",
                "desired_location",
            ),
            extra_fields=(
                "inverter_brand_model",
                "backup_requirement",
                "photo_inverter_cabinet",
            ),
            reply_strategy=(
                "Acknowledge existing solar. Explain compatibility depends on inverter and backup needs. "
                "Ask inverter brand/model. Ask backup requirement/preference. "
                "Ask main fuse if unknown. Invite photo of inverter/cabinet."
            ),
        ),
        "new_installation": PlaybookContext(
            priority_fields=("annual_consumption", "roof_type", "main_fuse"),
            suppress_fields=("inverter_brand_model",),
            extra_fields=(),
            reply_strategy="Ask about solar system details and energy usage.",
        ),
        "repair_or_fault": PlaybookContext(
            priority_fields=("inverter_brand_model", "issue_description", "when_started"),
            suppress_fields=("property_type", "roof_type", "annual_consumption"),
            extra_fields=("error_code",),
            reply_strategy="Ask about inverter and symptoms.",
        ),
    },
)

_SOLAR_SERVICE_PLAYBOOK = ServicePlaybook(
    id="solar_service",
    name="Solceller service & låg produktion",
    industry="solar_energy",
    applies_when="Solceller producerar dåligt, service på befintliga solceller",
    contexts={
        "service_or_maintenance": PlaybookContext(
            priority_fields=("inverter_brand_model", "when_started", "production_status"),
            suppress_fields=("property_type", "roof_type"),
            extra_fields=("app_error_screenshot",),
            reply_strategy="Ask about inverter, when production dropped, and app/display status.",
        ),
        "repair_or_fault": PlaybookContext(
            priority_fields=("inverter_brand_model", "when_started", "issue_description"),
            suppress_fields=("property_type", "roof_type"),
            extra_fields=("error_code",),
            reply_strategy="Ask about inverter model, fault description and when it started.",
        ),
    },
)

# D. VVS / Plumbing Playbook
_VVS_PLAYBOOK = ServicePlaybook(
    id="vvs_service",
    name="VVS & rörmokeri",
    industry="plumbing",
    applies_when="Vattenläcka, avlopp, toalett, kran, badrum, diskbänk",
    contexts={
        "urgent_issue": PlaybookContext(
            priority_fields=("water_shut_off", "active_leak", "location_of_issue"),
            suppress_fields=("main_fuse", "electrical_safety"),  # Don't mention "bryt strömmen" unless electrical risk
            extra_fields=(),
            reply_strategy=(
                "Ask whether water is shut off. Suggest shutting off water if active leak. "
                "Ask for photo and address. Do NOT advise breaking electricity unless leak near electrical."
            ),
        ),
        "repair_or_fault": PlaybookContext(
            priority_fields=("issue_description", "location_of_issue", "water_shut_off"),
            suppress_fields=("main_fuse",),
            extra_fields=(),
            reply_strategy="Ask about leak location, severity and whether water is shut off.",
        ),
        "service_or_maintenance": PlaybookContext(
            priority_fields=("issue_description", "address"),
            suppress_fields=("main_fuse",),
            extra_fields=(),
            reply_strategy="Ask about what needs service and preferred timing.",
        ),
    },
)

# E. Building / Carpentry Playbook
_BUILDING_PLAYBOOK = ServicePlaybook(
    id="building_project",
    name="Byggnation & snickeri",
    industry="construction",
    applies_when="Förråd, altan, pergola, carport, renovering, snickeriarbete",
    contexts={
        "new_project": PlaybookContext(
            priority_fields=("project_description", "approximate_area", "desired_timing"),
            suppress_fields=("main_fuse", "electrical_safety", "water_shut_off"),
            extra_fields=(),
            reply_strategy=(
                "Acknowledge project interest. Ask about project type, dimensions and timing. "
                "No electrical or plumbing questions unless mentioned."
            ),
        ),
        "new_installation": PlaybookContext(
            priority_fields=("project_description", "approximate_area", "desired_timing"),
            suppress_fields=("main_fuse", "electrical_safety", "water_shut_off"),
            extra_fields=(),
            reply_strategy="Ask practical project scoping questions.",
        ),
        "repair_or_fault": PlaybookContext(
            priority_fields=("issue_description", "location_of_issue"),
            suppress_fields=("main_fuse",),
            extra_fields=("photo_request",),
            reply_strategy="Ask for description of damage and location.",
        ),
    },
)

# Cross-cutting Complaint Override
_COMPLAINT_OVERRIDE = ComplaintOverride(
    trigger_keywords=(
        "inte nöjd", "ej nöjd", "missnöjd", "besviken", "dålig service",
        "dåligt arbete", "ingen har ringt", "ingen ringde", "inte hört av er",
        "lovad återkoppling", "inte fått återkoppling", "klagomål",
        "reklamation", "reklamera", "oacceptabelt", "kompensation",
    ),
    suppress_all_technical_fields=True,
    reply_strategy=(
        "Acknowledge dissatisfaction calmly. "
        "Apologize for the experience / lack of follow-up without admitting liability. "
        "Say responsible person will review and return. "
        "No troubleshooting questions. "
        "Manual handling required."
    ),
    internal_flag="⚠️ KUND MISSNÖJD",
)

# ── Registry ──────────────────────────────────────────────────────────────────

_PLAYBOOK_REGISTRY: dict[str, ServicePlaybook] = {
    p.id: p
    for p in [
        _ELECTRICAL_PLAYBOOK,
        _ELECTRICAL_PANEL_PLAYBOOK,
        _EV_CHARGER_PLAYBOOK,
        _EV_CHARGER_FAULT_PLAYBOOK,
        _SOLAR_INSTALLATION_PLAYBOOK,
        _BATTERY_PLAYBOOK,
        _SOLAR_SERVICE_PLAYBOOK,
        _VVS_PLAYBOOK,
        _BUILDING_PLAYBOOK,
    ]
}


# ── Public API ────────────────────────────────────────────────────────────────


def get_playbook(service_type: str) -> ServicePlaybook | None:
    """Return the ServicePlaybook for *service_type*, or None if not found."""
    return _PLAYBOOK_REGISTRY.get(service_type)


def list_playbooks() -> list[ServicePlaybook]:
    """Return all registered ServicePlaybook objects."""
    return list(_PLAYBOOK_REGISTRY.values())


def get_complaint_override() -> ComplaintOverride:
    """Return the cross-cutting complaint override."""
    return _COMPLAINT_OVERRIDE


def is_complaint(text: str) -> bool:
    """Return True if the text contains clear complaint signals."""
    lower = text.lower()
    return any(kw in lower for kw in _COMPLAINT_OVERRIDE.trigger_keywords)


def select_questions_from_playbook(
    service_type: str,
    service_context: str,
    fact_states: dict[str, Any],
    base_missing_fields: list[str],
    max_questions: int = 4,
) -> list[str]:
    """Return an ordered list of field names to ask, respecting playbook rules.

    Args:
        service_type:      Profile service_type (e.g. "battery_storage")
        service_context:   Detected service context (e.g. "add_on_existing")
        fact_states:       Mapping of field → FactState (from detect_all_facts)
        base_missing_fields: Missing required fields from compute_profile_missing_info
        max_questions:     Maximum number of questions to return

    Returns:
        Ordered list of field names (most important first), capped at max_questions.
    """
    from app.service_profiles.facts import FactState, should_ask_field

    playbook = get_playbook(service_type)
    ctx_behavior: PlaybookContext | None = None
    if playbook and service_context in playbook.contexts:
        ctx_behavior = playbook.contexts[service_context]

    suppress = set(ctx_behavior.suppress_fields) if ctx_behavior else set()
    priority = list(ctx_behavior.priority_fields) if ctx_behavior else []
    extra = list(ctx_behavior.extra_fields) if ctx_behavior else []

    # Build candidate pool: priority + base_missing + extra
    # Maintain priority ordering: priority fields first, then missing, then extra
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(f: str) -> None:
        if f not in seen and f not in suppress:
            seen.add(f)
            candidates.append(f)

    for f in priority:
        _add(f)

    for f in base_missing_fields:
        _add(f)

    for f in extra:
        _add(f)

    # Filter: only include fields that should be asked
    # (MISSING, UNKNOWN, UNCERTAIN, PARTIAL — not CONFIRMED)
    result: list[str] = []
    for f in candidates:
        state = fact_states.get(f)
        if state is None:
            # Unknown state → assume MISSING → ask
            result.append(f)
        elif state == FactState.CONFIRMED:
            # Already known → skip
            continue
        else:
            result.append(f)

        if len(result) >= max_questions:
            break

    return result
