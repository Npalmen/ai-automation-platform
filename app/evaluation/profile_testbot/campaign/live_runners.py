"""Semi-auto and automatic profile campaign runners."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.adapters.campaign_scenario import profile_scenario_to_campaign
from app.evaluation.profile_testbot.campaign.readiness import (
    require_automatic_canary_approval,
    require_live_semi_auto_approval,
    validate_profile_testbot_tenant,
)
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.generator.profile_generator import (
    generate_automatic_canary,
    generate_automatic_core,
    generate_semi_auto_campaign,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


@dataclass
class ProfileCampaignPlan:
    campaign_type: str
    scenarios: list[ProfileScenario]
    blocked_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_type": self.campaign_type,
            "scenario_count": len(self.scenarios),
            "scenario_ids": [s.scenario_id for s in self.scenarios],
            "blocked_reason": self.blocked_reason,
        }


def plan_semi_auto_live_campaign(
    *,
    profile_id: str = "pilot-service-company-v1",
    tenant_id: str = LIVE_EVAL_TENANT_ID,
    seed: int = 0,
) -> ProfileCampaignPlan:
    issues = validate_profile_testbot_tenant(tenant_id)
    if issues:
        raise LiveEvalSafetyError("; ".join(issues))
    blocked = require_live_semi_auto_approval()
    profile = load_customer_profile(profile_id)
    scenarios = generate_semi_auto_campaign(profile, seed=seed)
    return ProfileCampaignPlan(
        campaign_type="profile-semi-auto-live",
        scenarios=scenarios,
        blocked_reason=blocked,
    )


def plan_automatic_canary_campaign(
    *,
    profile_id: str = "pilot-service-company-v1",
    tenant_id: str = LIVE_EVAL_TENANT_ID,
    seed: int = 0,
) -> ProfileCampaignPlan:
    issues = validate_profile_testbot_tenant(tenant_id)
    if issues:
        raise LiveEvalSafetyError("; ".join(issues))
    blocked = require_automatic_canary_approval()
    profile = load_customer_profile(profile_id)
    scenarios = generate_automatic_canary(profile, seed=seed)
    return ProfileCampaignPlan(
        campaign_type="profile-automatic-canary",
        scenarios=scenarios,
        blocked_reason=blocked,
    )


def plan_automatic_core_campaign(
    *,
    profile_id: str = "pilot-service-company-v1",
    tenant_id: str = LIVE_EVAL_TENANT_ID,
    seed: int = 0,
) -> ProfileCampaignPlan:
    plan = plan_automatic_canary_campaign(profile_id=profile_id, tenant_id=tenant_id, seed=seed)
    if plan.blocked_reason:
        return ProfileCampaignPlan(
            campaign_type="profile-automatic-core",
            scenarios=[],
            blocked_reason=plan.blocked_reason,
        )
    profile = load_customer_profile(profile_id)
    scenarios = generate_automatic_core(profile, seed=seed)
    return ProfileCampaignPlan(
        campaign_type="profile-automatic-core",
        scenarios=scenarios,
        blocked_reason=None,
    )


def materialize_campaign_scenarios(plan: ProfileCampaignPlan) -> list[Any]:
    return [profile_scenario_to_campaign(scenario) for scenario in plan.scenarios]
