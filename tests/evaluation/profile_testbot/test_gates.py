"""Gate tests for profile testbot tenant isolation."""

from app.evaluation.live.campaign.gates import validate_no_production_resources


def test_production_pilot_tenant_blocked_in_campaign_gates():
    issues = validate_no_production_resources(tenant_id="TENANT_PRODUCTION_PILOT_01")
    assert any("TENANT_PRODUCTION_PILOT_01" in issue for issue in issues)
