"""Locked constants for inbox quality qualification (Todo J)."""

from __future__ import annotations

LIVE_QUALITY_CANARY_CAMPAIGN_TYPE = "inbox-quality-live-canary"
LIVE_QUALITY_CAMPAIGN_TYPE = "inbox-quality-live-campaign"

LIVE_QUALITY_CANARY_TARGET = 12
LIVE_QUALITY_CANARY_SEND_MAX = 6
LIVE_QUALITY_CANARY_HOLD_MIN = 6
LIVE_QUALITY_CANARY_FAMILY_MIN = 8

LIVE_QUALITY_CAMPAIGN_TARGET = 32
LIVE_QUALITY_CAMPAIGN_SEND_MAX = 16
LIVE_QUALITY_CAMPAIGN_FAMILY_MIN = 12

PTB_SEM_0024_SCENARIO_ID = "PTB-SEM-0024"

SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND = frozenset(
    {
        "send_after_approval",
        "automatic_safe_send",
    }
)

NO_SEND_BEHAVIORS = frozenset(
    {
        "hold",
        "reject",
        "no_reply",
        "observe_only",
        "draft_for_approval",
    }
)
