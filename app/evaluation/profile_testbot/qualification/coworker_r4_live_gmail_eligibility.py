"""Context-bound R4 reviewed-live Gmail scenario eligibility."""

from __future__ import annotations

from typing import Any

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.qualification.coworker_r4_registration_contract import (
    REVIEWED_LIVE_LLM_BODY,
    is_r4_registry_scenario,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_EXECUTE_AI_MODE,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_NO_SEND_SCENARIO_IDS,
    R4_SCENARIO_IDS,
    R4_SEND_SCENARIO_IDS,
    R4_TENANT_ID,
)

R4_LOCAL_QUARANTINE_SCENARIO_IDS = frozenset({"PTB-SEM-0024"})
R4_LIVE_TRIGGER_SCENARIO_IDS = frozenset(
    sid for sid in R4_SCENARIO_IDS if sid not in R4_LOCAL_QUARANTINE_SCENARIO_IDS
)


def is_r4_reviewed_live_gmail_context(
    *,
    transport_mode: str,
    ai_mode: str | None,
    campaign_type: str | None,
    execution_mode: str | None,
    tenant_id: str | None,
) -> bool:
    return (
        transport_mode == "live_gmail"
        and (ai_mode or "").strip() == R4_EXECUTE_AI_MODE
        and (campaign_type or "").strip() == R4_LIVE_QUALITY_CAMPAIGN_TYPE
        and (execution_mode or "").strip() == R4_EXECUTION_MODE
        and (tenant_id or "").strip() == R4_TENANT_ID
    )


def require_r4_reviewed_live_gmail_scenario_eligible(
    scenario_id: str,
    *,
    transport_mode: str,
    ai_mode: str,
    campaign_type: str | None,
    execution_mode: str | None,
    tenant_id: str,
) -> None:
    if not is_r4_reviewed_live_gmail_context(
        transport_mode=transport_mode,
        ai_mode=ai_mode,
        campaign_type=campaign_type,
        execution_mode=execution_mode,
        tenant_id=tenant_id,
    ):
        raise LiveEvalSafetyError("R4 reviewed-live Gmail context incomplete or invalid")
    if ai_mode != REVIEWED_LIVE_LLM_BODY:
        raise LiveEvalSafetyError("R4 reviewed-live requires ai_mode reviewed_live_llm_body")
    if campaign_type != R4_LIVE_QUALITY_CAMPAIGN_TYPE:
        raise LiveEvalSafetyError(
            "R4 reviewed-live requires campaign_type coworker_r4_live_quality_campaign"
        )
    if execution_mode != R4_EXECUTION_MODE:
        raise LiveEvalSafetyError(
            f"R4 reviewed-live requires execution_mode {R4_EXECUTION_MODE!r}"
        )
    if tenant_id != R4_TENANT_ID:
        raise LiveEvalSafetyError(f"R4 reviewed-live requires tenant_id {R4_TENANT_ID!r}")
    if not is_r4_registry_scenario(scenario_id):
        raise LiveEvalSafetyError(f"scenario_id {scenario_id!r} not in R4 registry")


def evaluate_r4_live_gmail_scenario_eligibility_matrix() -> dict[str, Any]:
    blockers: list[str] = []
    ready = 0
    send_ready = 0
    no_send_ready = 0
    trigger_ready = 0
    quarantine_ready = 0

    for sid in R4_SCENARIO_IDS:
        try:
            require_r4_reviewed_live_gmail_scenario_eligible(
                sid,
                transport_mode="live_gmail",
                ai_mode=R4_EXECUTE_AI_MODE,
                campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
                execution_mode=R4_EXECUTION_MODE,
                tenant_id=R4_TENANT_ID,
            )
            ready += 1
            if sid in R4_SEND_SCENARIO_IDS:
                send_ready += 1
            if sid in R4_NO_SEND_SCENARIO_IDS:
                no_send_ready += 1
            if sid in R4_LIVE_TRIGGER_SCENARIO_IDS:
                trigger_ready += 1
            if sid in R4_LOCAL_QUARANTINE_SCENARIO_IDS:
                quarantine_ready += 1
        except LiveEvalSafetyError as exc:
            blockers.append(f"{sid}:{exc}")

    return {
        "r4_live_gmail_scenario_eligibility": f"{ready}/{len(R4_SCENARIO_IDS)}",
        "r4_send_scenario_eligibility": f"{send_ready}/{len(R4_SEND_SCENARIO_IDS)}",
        "r4_no_send_scenario_eligibility": f"{no_send_ready}/{len(R4_NO_SEND_SCENARIO_IDS)}",
        "r4_live_trigger_scenario_eligibility": f"{trigger_ready}/{len(R4_LIVE_TRIGGER_SCENARIO_IDS)}",
        "r4_local_quarantine_scenario_eligibility": f"{quarantine_ready}/{len(R4_LOCAL_QUARANTINE_SCENARIO_IDS)}",
        "ready_count": ready,
        "send_ready_count": send_ready,
        "no_send_ready_count": no_send_ready,
        "trigger_ready_count": trigger_ready,
        "local_quarantine_ready_count": quarantine_ready,
        "blockers": blockers,
        "passed": ready == len(R4_SCENARIO_IDS) and not blockers,
    }
