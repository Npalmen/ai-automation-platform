"""Convert profile scenarios to live campaign scenarios."""

from __future__ import annotations

import hashlib
import json

from app.evaluation.live.campaign.schemas import CampaignBudget, CampaignEmailInput, CampaignScenario
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


def profile_scenario_to_campaign(scenario: ProfileScenario) -> CampaignScenario:
    content_hash = hashlib.sha256(
        json.dumps(scenario.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    budgets = CampaignBudget(
        gmail_sends=1 if scenario.expected_send_behavior in {"send_after_approval", "automatic_safe_send"} else 0,
        gmail_replies=1 if scenario.expected_send_behavior in {"send_after_approval", "automatic_safe_send"} else 0,
        external_writes=0,
    )
    expected_approval: dict = {}
    if scenario.expected_send_behavior == "send_after_approval":
        expected_approval = {
            "operator_plan": [
                {"decision": "approve", "action_type": "send_customer_auto_reply"},
            ],
            "expected_reply": True,
            "test_variant": "positive_approve",
        }
    elif scenario.expected_send_behavior in {"hold", "reject"}:
        expected_approval = {
            "operator_plan": [],
            "expected_reply": False,
            "test_variant": "negative_hold",
        }
    return CampaignScenario(
        scenario_id=scenario.scenario_id,
        scenario_version="profile-v1",
        mode=scenario.mode,
        campaign_type=f"profile-{scenario.campaign_phase}",
        job_type=str(scenario.expected_classification.get("job_type") or "unknown"),
        service_profile="electrical",
        synthetic_customer_id=f"cust-{scenario.scenario_id.lower()}",
        thread_id=f"thread-{scenario.scenario_id.lower()}",
        label="krowolf-live-eval",
        email=CampaignEmailInput(
            subject=scenario.input.subject,
            message_text=scenario.input.message_text,
            sender_name=scenario.input.sender_name,
            sender_email=scenario.input.sender_email,
        ),
        campaign_types=frozenset({f"profile-{scenario.campaign_phase}"}),
        expected_classification=dict(scenario.expected_classification),
        expected_routing={
            "queue": scenario.expected_route.get("queue"),
            "final_job_status": scenario.expected_route.get("final_job_status"),
        },
        expected_approval=expected_approval,
        budgets=budgets,
        content_hash=content_hash,
    )
