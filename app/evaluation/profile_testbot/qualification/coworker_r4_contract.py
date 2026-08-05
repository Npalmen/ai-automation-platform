"""Fail-closed R4 registration contract (not R3 frozen)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_AI_MODE,
    R4_EXCLUDED_R3_HOLD_OVERRIDE_SCENARIOS,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_SCENARIO_IDS,
    R4_TENANT_ID,
)

_FORBIDDEN_CAMPAIGN_TYPES = frozenset(
    {
        "coworker_r3_frozen_live_canary",
        "coworker-reply-live-canary",
    }
)
_FORBIDDEN_EXECUTION_MODES = frozenset(
    {
        "r3_frozen_approved_body",
        "fixture_ai",
    }
)


@dataclass
class R4ContractResult:
    valid: bool
    blockers: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "blockers": self.blockers,
            "details": self.details,
        }


def validate_r4_registration_contract(
    *,
    tenant_id: str,
    campaign_type: str | None,
    execution_mode: str | None,
    ai_mode: str | None,
    scenario_ids: list[str] | tuple[str, ...] | None = None,
    env: str | None = None,
    automatic_gmail: bool | None = False,
    production_activation: bool | None = False,
    apply_r3_hold_override: bool | None = False,
) -> R4ContractResult:
    blockers: list[str] = []
    if tenant_id != R4_TENANT_ID:
        blockers.append(f"tenant_id must be {R4_TENANT_ID}")
    if env is not None and env != "test":
        blockers.append("ENV must be test")
    if campaign_type != R4_LIVE_QUALITY_CAMPAIGN_TYPE:
        blockers.append(f"campaign_type must be {R4_LIVE_QUALITY_CAMPAIGN_TYPE}")
    if campaign_type in _FORBIDDEN_CAMPAIGN_TYPES:
        blockers.append("R3/frozen campaign_type is forbidden for R4")
    if execution_mode != R4_EXECUTION_MODE:
        blockers.append(f"execution_mode must be {R4_EXECUTION_MODE}")
    if execution_mode in _FORBIDDEN_EXECUTION_MODES:
        blockers.append("R3 frozen / fixture execution_mode is forbidden for R4")
    if ai_mode != R4_AI_MODE:
        blockers.append(f"ai_mode must be {R4_AI_MODE}")
    if ai_mode in _FORBIDDEN_EXECUTION_MODES or ai_mode == "fixture_ai":
        blockers.append("fixture_ai is forbidden for R4")
    if automatic_gmail:
        blockers.append("automatic_gmail must be false")
    if production_activation:
        blockers.append("production_activation must be false")
    if apply_r3_hold_override:
        blockers.append(
            "R3 PTB-DCQ-0088 hold override must not be applied or generalized for R4"
        )
    if scenario_ids is not None and list(scenario_ids) != list(R4_SCENARIO_IDS):
        blockers.append("scenario_ids must match locked R4 registry")

    return R4ContractResult(
        valid=not blockers,
        blockers=blockers,
        details={
            "campaign_type": R4_LIVE_QUALITY_CAMPAIGN_TYPE,
            "execution_mode": R4_EXECUTION_MODE,
            "ai_mode": R4_AI_MODE,
            "r3_hold_override_scenarios_excluded": sorted(
                R4_EXCLUDED_R3_HOLD_OVERRIDE_SCENARIOS
            ),
            "ordinary_policy_for_complaint_risk": True,
        },
    )
