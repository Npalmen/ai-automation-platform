"""Activation stage capability matrix for production pilot."""

from __future__ import annotations

from typing import Any

from app.production_pilot.constants import ACTIVATION_STAGES, DEFAULT_ACTIVATION_STAGE

_STAGE_MATRIX: dict[str, dict[str, Any]] = {
    "P0": {
        "gmail_intake": False,
        "observe": True,
        "classification_extraction": True,
        "manual_review": True,
        "approvals": False,
        "automatic_gmail": False,
        "shadow_intake": False,
        "shadow_matching": False,
        "shadow_promotion": False,
        "sheets_monday_visma": False,
        "scheduler_automatic": False,
        "automatic_verify": False,
        "automatic_customer_link": False,
        "automatic_merge": False,
        "gmail_reply_budget": 0,
        "non_gmail_write_budget": 0,
        "inbound_read_budget": 0,
    },
    "P1": {
        "gmail_intake": True,
        "observe": True,
        "classification_extraction": True,
        "manual_review": True,
        "approvals": False,
        "automatic_gmail": False,
        "shadow_intake": True,
        "shadow_matching": True,
        "shadow_promotion": False,
        "sheets_monday_visma": False,
        "scheduler_automatic": False,
        "automatic_verify": False,
        "automatic_customer_link": False,
        "automatic_merge": False,
        "gmail_reply_budget": 0,
        "non_gmail_write_budget": 0,
        "inbound_read_budget": None,
    },
    "P2": {
        "gmail_intake": True,
        "observe": True,
        "classification_extraction": True,
        "manual_review": True,
        "approvals": True,
        "automatic_gmail": False,
        "shadow_intake": True,
        "shadow_matching": True,
        "shadow_promotion": False,
        "sheets_monday_visma": False,
        "scheduler_automatic": False,
        "automatic_verify": False,
        "automatic_customer_link": False,
        "automatic_merge": False,
        "gmail_reply_budget": None,
        "non_gmail_write_budget": 0,
        "inbound_read_budget": None,
    },
    "P3": {
        "gmail_intake": True,
        "observe": True,
        "classification_extraction": True,
        "manual_review": True,
        "approvals": True,
        "automatic_gmail": True,
        "shadow_intake": True,
        "shadow_matching": True,
        "shadow_promotion": False,
        "sheets_monday_visma": False,
        "scheduler_automatic": False,
        "automatic_verify": False,
        "automatic_customer_link": False,
        "automatic_merge": False,
        "gmail_reply_budget": 3,
        "non_gmail_write_budget": 0,
        "inbound_read_budget": None,
    },
}


class ProductionPilotStageError(ValueError):
    """Raised when stage transition or capability check fails."""


def normalize_stage(stage: str | None) -> str:
    value = (stage or DEFAULT_ACTIVATION_STAGE).strip().upper()
    if value not in ACTIVATION_STAGES:
        raise ProductionPilotStageError(f"Unknown activation stage: {stage!r}")
    return value


def stage_capabilities(stage: str | None) -> dict[str, Any]:
    return dict(_STAGE_MATRIX[normalize_stage(stage)])


def production_pilot_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    return dict((settings or {}).get("production_pilot") or {})


def current_activation_stage(settings: dict[str, Any] | None) -> str:
    return normalize_stage(production_pilot_settings(settings).get("activation_stage"))


def validate_stage_transition(current: str, target: str) -> None:
    current_norm = normalize_stage(current)
    target_norm = normalize_stage(target)
    order = list(ACTIVATION_STAGES)
    if order.index(target_norm) < order.index(current_norm):
        raise ProductionPilotStageError(
            f"Cannot downgrade activation stage from {current_norm} to {target_norm}"
        )
    if order.index(target_norm) > order.index(current_norm) + 1:
        raise ProductionPilotStageError(
            f"Activation stage must advance one step at a time ({current_norm} -> {target_norm})"
        )
