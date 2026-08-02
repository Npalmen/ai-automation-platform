"""Digital coworker reply quality dataset constants (Todo G)."""

from __future__ import annotations

COWORKER_REPLY_DATASET_VERSION = "coworker_reply_dataset_v1"
COWORKER_SCENARIO_TARGET = 120
COWORKER_FAMILY_TARGET = 15
COWORKER_SCENARIOS_PER_FAMILY = 8
COWORKER_MAX_FAMILY_SHARE = 0.12

COWORKER_FAMILIES: tuple[str, ...] = (
    "solar_installation_new",
    "solar_installation_followup",
    "battery_installation_new",
    "battery_installation_known_facts",
    "ev_charger_new",
    "ev_charger_known_facts",
    "solar_battery_combined",
    "existing_support_symptom",
    "existing_support_followup",
    "job_status_request",
    "job_status_no_contact",
    "complaint_warranty",
    "general_consultation",
    "missing_attachment",
    "multi_turn_continuation",
)
