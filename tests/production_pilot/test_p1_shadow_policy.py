"""Production pilot shadow policy tests."""

from __future__ import annotations

from app.production_pilot.constants import PILOT_TENANT_ID
from app.production_pilot.kill_switches import apply_p1_activation
from app.production_pilot.shadow_policy import (
    production_pilot_shadow_intake_allowed,
    production_pilot_shadow_matching_allowed,
    production_pilot_shadow_promotion_allowed,
)
from app.services.shadow_gate import assert_shadow_intake_allowed


def test_p1_shadow_intake_allowed_without_env_flag():
    settings = apply_p1_activation()
    assert production_pilot_shadow_intake_allowed(PILOT_TENANT_ID, settings)
    assert production_pilot_shadow_matching_allowed(PILOT_TENANT_ID, settings)
    assert not production_pilot_shadow_promotion_allowed(PILOT_TENANT_ID, settings)
    assert_shadow_intake_allowed(PILOT_TENANT_ID, settings)
