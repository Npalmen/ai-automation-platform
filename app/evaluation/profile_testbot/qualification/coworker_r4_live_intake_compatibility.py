"""Production-equivalent R4 live-trigger intake compatibility matrix."""

from __future__ import annotations

import uuid
from typing import Any

from app.evaluation.live.intake_classification_input import evaluate_gmail_intake_classification_gate
from app.evaluation.profile_testbot.campaign.send_payload import (
    build_profile_testbot_message_body,
    build_profile_testbot_subject,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.coworker_r4_live_gmail_eligibility import (
    R4_LOCAL_QUARANTINE_SCENARIO_IDS,
    R4_LIVE_TRIGGER_SCENARIO_IDS,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_no_send_intake_suppression import (
    R4_AUTHORITATIVE_INTAKE_SUPPRESSION,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_PROFILE_ID,
    R4_SEND_SCENARIO_IDS,
    resolve_r4_scenarios,
)

TERMINAL_PIPELINE_INTAKE_EXPECTED = "pipeline_intake_expected"
TERMINAL_AUTHORITATIVE_EXPECTED_SUPPRESSION = "authoritative_expected_suppression"
TERMINAL_LOCAL_QUARANTINE = "local_quarantine"
TERMINAL_UNEXPECTED_SUPPRESSION = "unexpected_suppression"
TERMINAL_AMBIGUOUS_FAILURE = "ambiguous/failure"

ATTEMPT9_FAILING_EVAL_RUN_ID = "1e768ca6-18c6-420a-b2b2-51b3e45b58dc"
ATTEMPT9_CAMPAIGN_ID = "8e0fa53a-868f-454f-b40f-2a41f94b2efe"


def _deterministic_eval_run_id(scenario_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"r4-intake-matrix:{scenario_id}"))


def _expected_terminal(scenario_id: str) -> str:
    if scenario_id in R4_LOCAL_QUARANTINE_SCENARIO_IDS:
        return TERMINAL_LOCAL_QUARANTINE
    if scenario_id in R4_AUTHORITATIVE_INTAKE_SUPPRESSION:
        return TERMINAL_AUTHORITATIVE_EXPECTED_SUPPRESSION
    if scenario_id in R4_SEND_SCENARIO_IDS:
        return TERMINAL_PIPELINE_INTAKE_EXPECTED
    if scenario_id in R4_LIVE_TRIGGER_SCENARIO_IDS:
        return TERMINAL_PIPELINE_INTAKE_EXPECTED
    return TERMINAL_AMBIGUOUS_FAILURE


def build_r4_live_trigger_intake_inputs(
    *,
    scenario,
    campaign_id: str,
    evaluation_run_id: str,
) -> tuple[str, str]:
    body = build_profile_testbot_message_body(
        scenario=scenario,
        evaluation_run_id=evaluation_run_id,
        campaign_id=campaign_id,
    )
    subject = build_profile_testbot_subject(
        scenario=scenario,
        evaluation_run_id=evaluation_run_id,
    )
    return subject, body


def evaluate_r4_live_intake_compatibility_row(
    *,
    scenario,
    campaign_id: str,
    evaluation_run_id: str | None = None,
) -> dict[str, Any]:
    run_id = evaluation_run_id or _deterministic_eval_run_id(scenario.scenario_id)
    subject, body = build_r4_live_trigger_intake_inputs(
        scenario=scenario,
        campaign_id=campaign_id,
        evaluation_run_id=run_id,
    )
    gate = evaluate_gmail_intake_classification_gate(subject, body)
    expected_terminal = _expected_terminal(scenario.scenario_id)
    actual_terminal: str
    passed = False
    blockers: list[str] = []

    if expected_terminal == TERMINAL_LOCAL_QUARANTINE:
        actual_terminal = TERMINAL_LOCAL_QUARANTINE
        passed = True
    elif expected_terminal == TERMINAL_AUTHORITATIVE_EXPECTED_SUPPRESSION:
        expected_reason = R4_AUTHORITATIVE_INTAKE_SUPPRESSION[scenario.scenario_id]
        if gate["proceeds"]:
            actual_terminal = TERMINAL_UNEXPECTED_SUPPRESSION
            blockers.append(f"expected_suppression:{expected_reason}")
        elif gate.get("skip_reason") == expected_reason:
            actual_terminal = TERMINAL_AUTHORITATIVE_EXPECTED_SUPPRESSION
            passed = True
        else:
            actual_terminal = TERMINAL_UNEXPECTED_SUPPRESSION
            blockers.append(
                f"skip_reason_mismatch:{gate.get('skip_reason')}!={expected_reason}"
            )
    elif expected_terminal == TERMINAL_PIPELINE_INTAKE_EXPECTED:
        if gate["proceeds"]:
            actual_terminal = TERMINAL_PIPELINE_INTAKE_EXPECTED
            passed = True
        else:
            actual_terminal = TERMINAL_UNEXPECTED_SUPPRESSION
            blockers.append(f"unexpected_skip:{gate.get('skip_reason')}")
    else:
        actual_terminal = TERMINAL_AMBIGUOUS_FAILURE
        blockers.append("unknown_expected_terminal")

    return {
        "scenario_id": scenario.scenario_id,
        "evaluation_run_id": run_id,
        "expected_terminal": expected_terminal,
        "actual_terminal": actual_terminal,
        "inferred_type": gate.get("inferred_type"),
        "skip_reason": gate.get("skip_reason"),
        "proceeds": gate.get("proceeds"),
        "passed": passed,
        "blockers": blockers,
    }


def evaluate_r4_live_intake_compatibility_matrix(
    *,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    profile = load_customer_profile(R4_PROFILE_ID)
    scenarios = resolve_r4_scenarios(profile, seed=42)
    by_id = {s.scenario_id: s for s in scenarios}
    campaign = campaign_id or f"r4-intake-matrix-{uuid.uuid4()}"
    rows: list[dict[str, Any]] = []
    blockers: list[str] = []
    ready = 0

    for scenario_id in sorted(R4_LIVE_TRIGGER_SCENARIO_IDS):
        scenario = by_id[scenario_id]
        row = evaluate_r4_live_intake_compatibility_row(
            scenario=scenario,
            campaign_id=campaign,
        )
        rows.append(row)
        if row["passed"]:
            ready += 1
        else:
            blockers.extend([f"{scenario_id}:{b}" for b in row["blockers"]])

    attempt9_row = evaluate_r4_live_intake_compatibility_row(
        scenario=by_id["PTB-DCQ-0007"],
        campaign_id=ATTEMPT9_CAMPAIGN_ID,
        evaluation_run_id=ATTEMPT9_FAILING_EVAL_RUN_ID,
    )

    return {
        "r4_live_intake_compatibility": f"{ready}/{len(R4_LIVE_TRIGGER_SCENARIO_IDS)}",
        "ready_count": ready,
        "live_trigger_count": len(R4_LIVE_TRIGGER_SCENARIO_IDS),
        "rows": rows,
        "ptb_dcq_0007_attempt9_regression": attempt9_row,
        "blockers": blockers,
        "passed": ready == len(R4_LIVE_TRIGGER_SCENARIO_IDS) and not blockers,
    }
