"""Fail-closed live LLM reservation gates for profile semi-auto PTB-SEM runs."""

from __future__ import annotations

from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.constants import ALLOWED_AI_MODES, ALLOWED_TRANSPORT_MODES
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.evaluation.profile_testbot.campaign.scenario_gate import (
    require_profile_testbot_live_execution_authorized,
)
from app.evaluation.profile_testbot.campaign.semi_auto_manifest import is_locked_ptb_sem_scenario_id
from app.evaluation.profile_testbot.constants import BLOCKED_TENANTS, LIVE_EVAL_TENANT_ID


def validate_profile_testbot_live_llm_reservation(snapshot: TrustedLiveEvalSnapshot) -> None:
    """Authorize a trusted live_eval snapshot before reserving live LLM operations."""
    if snapshot.ai_mode != "live_llm":
        raise LiveEvalSafetyError("profile testbot live LLM reservation requires ai_mode live_llm")
    if snapshot.transport_mode != "live_gmail":
        raise LiveEvalSafetyError(
            "profile testbot live LLM reservation requires transport_mode live_gmail"
        )
    if snapshot.transport_mode not in ALLOWED_TRANSPORT_MODES:
        raise LiveEvalSafetyError(f"transport_mode {snapshot.transport_mode!r} is not allowed")
    if snapshot.ai_mode not in ALLOWED_AI_MODES:
        raise LiveEvalSafetyError(f"ai_mode {snapshot.ai_mode!r} is not allowed")

    config = get_live_eval_config()
    if not config.enabled:
        raise LiveEvalSafetyError("LIVE_EVAL_ALLOWED=yes required")
    if snapshot.tenant_id != LIVE_EVAL_TENANT_ID:
        raise LiveEvalSafetyError("profile testbot live LLM reservation requires TENANT_LIVE_EVAL")
    if snapshot.tenant_id in BLOCKED_TENANTS:
        raise LiveEvalSafetyError(f"tenant {snapshot.tenant_id!r} is blocked for live eval")
    if config.tenant_ids and snapshot.tenant_id not in config.tenant_ids:
        raise LiveEvalSafetyError(f"tenant_id {snapshot.tenant_id!r} is not in LIVE_EVAL_TENANT_IDS")

    scenario_id = (snapshot.scenario_id or "").strip()
    if not is_locked_ptb_sem_scenario_id(scenario_id):
        raise LiveEvalSafetyError(
            f"LLM operation reservation not defined for {scenario_id!r}"
        )

    require_profile_testbot_live_execution_authorized()
