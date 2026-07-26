"""Synthetic email content generator for campaign scenarios."""

from __future__ import annotations

from app.evaluation.live.campaign.schemas import CampaignScenario
from app.evaluation.live.subject_parser import build_subject_with_token


def build_campaign_message_body(
    *,
    scenario: CampaignScenario,
    evaluation_run_id: str,
    campaign_run_id: str | None = None,
) -> str:
    """Build HTML body with correlation marker and scenario text."""
    marker = f"<!-- KROWOLF_EVAL:evaluation_run_id={evaluation_run_id} -->"
    customer_marker = f"<!-- KROWOLF_CUSTOMER:{scenario.synthetic_customer_id} -->"
    thread_marker = f"<!-- KROWOLF_THREAD:{scenario.thread_id} -->"
  # Avoid "campaign" in marker text — classify_email_type treats it as newsletter.
    run_marker = (
        f"<!-- KROWOLF_RUN_SCOPE:{campaign_run_id} -->"
        if campaign_run_id
        else ""
    )
    text = (scenario.email.message_text or "").strip()
    parts = [marker, customer_marker, thread_marker]
    if run_marker:
        parts.append(run_marker)
    parts.append(text)
    return "\n".join(parts)


def build_campaign_subject(
    *,
    scenario: CampaignScenario,
    evaluation_run_id: str,
    attempt_id: int = 1,
) -> str:
    return build_subject_with_token(
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario.scenario_id,
        attempt_id=attempt_id,
        base_subject=scenario.email.subject,
    )


def build_campaign_send_payload(
    *,
    scenario: CampaignScenario,
    evaluation_run_id: str,
    attempt_id: int = 1,
    campaign_run_id: str | None = None,
) -> dict[str, str]:
    return {
        "subject": build_campaign_subject(
            scenario=scenario,
            evaluation_run_id=evaluation_run_id,
            attempt_id=attempt_id,
        ),
        "body": build_campaign_message_body(
            scenario=scenario,
            evaluation_run_id=evaluation_run_id,
            campaign_run_id=campaign_run_id,
        ),
        "sender_name": scenario.email.sender_name,
        "sender_email": scenario.email.sender_email,
    }
