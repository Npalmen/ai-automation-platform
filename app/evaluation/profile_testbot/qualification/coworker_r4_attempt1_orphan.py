"""Permanent quarantine for R4 live campaign attempt 1 (never resume/reuse)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.live.errors import LiveEvalSafetyError

ORPHAN_GROUP_ID = "orphaned_r4_attempt_1"
ATTEMPT1_CAMPAIGN_ID = "fb36fd42-ce05-492e-8227-f1aad537868b"
ATTEMPT6_CAMPAIGN_ID = "298aeee7-dc72-4614-86eb-8f20566bee2f"
R4_QUARANTINED_CAMPAIGN_IDS: frozenset[str] = frozenset(
    {
        ATTEMPT1_CAMPAIGN_ID,
        "4d836572-9c27-4eac-9892-a3693801d334",
        "32c6ed26-d030-441a-af52-5b186fae1107",
        "99fa0b7f-1a6b-45aa-bec9-07f54f845de3",
        "af0c2de2-eebe-486e-bb67-3414ac59d1b9",
        ATTEMPT6_CAMPAIGN_ID,
    }
)
ATTEMPT1_FAILED_SCENARIO = "PTB-DCQ-0000"
ATTEMPT1_CLASSIFICATION = "registration_rejected_before_external_write"

# Evaluation run IDs allocated during attempt 1 before fail-closed stop.
ATTEMPT1_EVALUATION_RUN_IDS: frozenset[str] = frozenset(
    {
        "fdf8985f-14bb-406c-afc2-73eba8e59fac",
    }
)


@dataclass(frozen=True)
class R4Attempt1OrphanRecord:
    orphan_group_id: str = ORPHAN_GROUP_ID
    campaign_id: str = ATTEMPT1_CAMPAIGN_ID
    classification: str = ATTEMPT1_CLASSIFICATION
    failed_scenario: str = ATTEMPT1_FAILED_SCENARIO
    run_registration_created: bool = False
    inbound_trigger_sent: bool = False
    gmail_replies: int = 0
    gmail_drafts: int = 0
    external_writes: int = 0
    resume_forbidden: bool = True
    reuse_blocked: bool = True
    never_resume: bool = True
    never_retry: bool = True
    exclude_from_r4_pass: bool = True
    remaining_scenarios_status: str = "not_run"

    def to_dict(self) -> dict[str, Any]:
        return {
            "orphan_group_id": self.orphan_group_id,
            "campaign_id": self.campaign_id,
            "classification": self.classification,
            "failed_scenario": self.failed_scenario,
            "run_registration_created": self.run_registration_created,
            "inbound_trigger_sent": self.inbound_trigger_sent,
            "gmail_replies": self.gmail_replies,
            "gmail_drafts": self.gmail_drafts,
            "external_writes": self.external_writes,
            "resume_forbidden": self.resume_forbidden,
            "reuse_blocked": self.reuse_blocked,
            "never_resume": self.never_resume,
            "never_retry": self.never_retry,
            "exclude_from_r4_pass": self.exclude_from_r4_pass,
            "remaining_scenarios_status": self.remaining_scenarios_status,
            "evaluation_run_ids": sorted(ATTEMPT1_EVALUATION_RUN_IDS),
        }


def attempt1_orphan_record() -> R4Attempt1OrphanRecord:
    return R4Attempt1OrphanRecord()


def is_r4_attempt1_campaign_id(campaign_id: str | None) -> bool:
    return (campaign_id or "").strip().lower() == ATTEMPT1_CAMPAIGN_ID.lower()


def is_r4_attempt1_evaluation_run_id(evaluation_run_id: str | None) -> bool:
    return (evaluation_run_id or "").strip().lower() in {
        x.lower() for x in ATTEMPT1_EVALUATION_RUN_IDS
    }


def assert_r4_campaign_not_quarantined(campaign_id: str | None) -> None:
    normalized = (campaign_id or "").strip().lower()
    for quarantined in R4_QUARANTINED_CAMPAIGN_IDS:
        if normalized == quarantined.lower():
            raise LiveEvalSafetyError(
                f"campaign_id {quarantined} is permanently quarantined; resume/reuse forbidden"
            )


def assert_r4_evaluation_run_not_quarantined(evaluation_run_id: str | None) -> None:
    if is_r4_attempt1_evaluation_run_id(evaluation_run_id):
        raise LiveEvalSafetyError(
            f"evaluation_run_id {evaluation_run_id} belongs to {ORPHAN_GROUP_ID}; reuse forbidden"
        )
