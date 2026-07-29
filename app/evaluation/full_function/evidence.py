"""Bind compatible prior live evidence without new live runs."""

from __future__ import annotations

from typing import Any

PRIOR_LIVE_EVIDENCE: dict[str, dict[str, Any]] = {
    "AUTOMATIC_GMAIL_CORE_QUALIFIED": {
        "workflow_run_id": "30435651905",
        "campaign_type": "automatic-gmail-core",
        "scenario_ids": [
            "TBA01_safe_lead_auto_reply",
            "TBA03_safe_general_inquiry_auto_reply",
            "TBA04_noisy_lead_auto_reply",
        ],
        "external_writes": {"gmail_reply": 3},
        "compatible_capabilities": [
            "action.send_customer_auto_reply",
            "policy.pre_write_reply_safety",
        ],
    },
    "AUTOMATIC_GMAIL_CANARY_QUALIFIED": {
        "workflow_run_id": "local-canary",
        "campaign_type": "automatic-gmail-canary",
        "scenario_ids": ["TBA01_safe_lead_auto_reply"],
        "external_writes": {"gmail_reply": 1},
        "compatible_capabilities": ["action.send_customer_auto_reply"],
    },
    "SEMI_AUTOMATIC_CAMPAIGN_QUALIFIED": {
        "workflow_run_id": "testbot-d",
        "campaign_type": "semi-automatic",
        "scenario_ids": ["TBSM01", "TBSM02"],
        "external_writes": {"gmail_reply": 0},
        "compatible_capabilities": ["approval.lifecycle", "action.send_internal_handoff"],
    },
    "OBSERVE_CAMPAIGN_QUALIFIED": {
        "workflow_run_id": "testbot-c",
        "campaign_type": "observe",
        "scenario_ids": ["TBC01"],
        "external_writes": {},
        "compatible_capabilities": [
            "intake.gmail.message",
            "classification.lead",
            "classification.support",
            "classification.invoice",
            "classification.unknown",
        ],
    },
}


def bind_live_evidence(capability_id: str) -> dict[str, Any] | None:
    for qualification, payload in PRIOR_LIVE_EVIDENCE.items():
        if capability_id in payload.get("compatible_capabilities", []):
            return {
                "qualification": qualification,
                "workflow_run_id": payload["workflow_run_id"],
                "campaign_type": payload["campaign_type"],
                "scenario_ids": list(payload.get("scenario_ids", [])),
                "external_writes": dict(payload.get("external_writes", {})),
                "new_live_writes": 0,
            }
    return None


def validate_tbg05_evidence() -> list[str]:
    failures: list[str] = []
    evidence = bind_live_evidence("action.send_customer_auto_reply")
    if evidence is None:
        failures.append("TBG05: missing compatible live evidence for customer auto reply")
        return failures
    if evidence.get("qualification") != "AUTOMATIC_GMAIL_CORE_QUALIFIED":
        failures.append("TBG05: expected AUTOMATIC_GMAIL_CORE_QUALIFIED evidence")
    if evidence.get("new_live_writes", 1) != 0:
        failures.append("TBG05: new live writes must be 0")
    return failures
