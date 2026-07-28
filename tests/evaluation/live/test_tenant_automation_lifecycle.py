"""Tenant automation lifecycle tests."""

from __future__ import annotations

from app.evaluation.live.campaign.automatic_action_contract import CANARY_AUTO_ACTIONS
from app.evaluation.live.campaign.tenant_automation_lifecycle import (
    hash_auto_actions,
    verify_automation_not_broadly_enabled,
)


def test_hash_auto_actions_is_stable():
    first = hash_auto_actions({"lead": "manual", "unknown": "manual"})
    second = hash_auto_actions({"unknown": "manual", "lead": "manual"})
    assert first == second


def test_verify_rejects_broad_auto_enablement():
    issues = verify_automation_not_broadly_enabled({"lead": "auto"})
    assert issues


def test_canary_auto_actions_only_enables_lead():
    auto_types = [job_type for job_type, mode in CANARY_AUTO_ACTIONS.items() if mode == "auto"]
    assert auto_types == ["lead"]
