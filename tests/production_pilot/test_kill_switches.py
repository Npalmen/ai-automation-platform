"""Kill switch contract tests."""

from __future__ import annotations

from app.production_pilot.kill_switches import (
    KILL_SWITCH_ACTIONS,
    apply_p0_baseline,
    disable_gmail_replies,
    disable_scheduler,
    pause_tenant_automation,
)


def test_kill_switch_registry_has_required_actions():
    required = {
        "pause_tenant_automation",
        "disable_scheduler",
        "disable_gmail_replies",
        "disable_shadow_intake",
        "disable_shadow_matching",
        "disable_shadow_promotion",
        "disable_gmail_intake",
        "enable_read_only_operator_mode",
    }
    assert required.issubset(set(KILL_SWITCH_ACTIONS))


def test_pause_tenant_automation_sets_demo_mode():
    updated = pause_tenant_automation(apply_p0_baseline())
    assert updated["automation"]["demo_mode"] is True
    assert updated["operations"]["paused"] is True


def test_disable_scheduler_sets_paused():
    updated = disable_scheduler(apply_p0_baseline())
    assert updated["scheduler"]["run_mode"] == "paused"


def test_disable_gmail_replies_blocks_auto_replies():
    updated = disable_gmail_replies(apply_p0_baseline())
    assert updated["automation"]["automatic_gmail_replies"] is False
    assert updated["production_pilot"]["gmail_reply_kill_switch"] is True
