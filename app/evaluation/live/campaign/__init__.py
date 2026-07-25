"""Full-system testbot campaign support (isolated live Gmail scenarios)."""

from app.evaluation.live.campaign.gates import (
    campaign_enabled,
    require_campaign_scenario_allowed,
    validate_no_production_resources,
)
from app.evaluation.live.campaign.modes import CAMPAIGN_MODES, CAMPAIGN_TYPES
from app.evaluation.live.campaign.registry import (
    get_campaign_scenario,
    list_campaign_scenarios,
    load_campaign_manifest,
)

__all__ = [
    "CAMPAIGN_MODES",
    "CAMPAIGN_TYPES",
    "campaign_enabled",
    "get_campaign_scenario",
    "list_campaign_scenarios",
    "load_campaign_manifest",
    "require_campaign_scenario_allowed",
    "validate_no_production_resources",
]
