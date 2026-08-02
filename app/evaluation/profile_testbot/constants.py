"""Locked constants for profile-driven live testbot."""

from __future__ import annotations

LIVE_EVAL_TENANT_ID = "TENANT_LIVE_EVAL"
BLOCKED_TENANTS = frozenset(
    {
        "T_NIKLAS_DEMO_001",
        "TENANT_PRODUCTION_PILOT_01",
    }
)

PROFILE_CAMPAIGN_HERMETIC = "profile-hermetic"
PROFILE_CAMPAIGN_SEMI_AUTO = "profile-semi-auto-live"
PROFILE_CAMPAIGN_AUTOMATIC_CANARY = "profile-automatic-canary"
PROFILE_CAMPAIGN_AUTOMATIC_CORE = "profile-automatic-core"

HERMETIC_SCENARIO_TARGET = 120
SEMI_AUTO_SCENARIO_TARGET = 40
SEMI_AUTO_SEND_AFTER_APPROVAL_MIN = 20
SEMI_AUTO_HOLD_EDGE_MIN = 20
AUTOMATIC_CANARY_TARGET = 4
AUTOMATIC_CORE_TARGET = 30

QUALIFICATION_SEMI_AUTO = "PROFILE_DRIVEN_SEMI_AUTO_GMAIL_QUALIFIED"
QUALIFICATION_SEMI_AUTO_QUALITY = "PROFILE_DRIVEN_SEMI_AUTO_QUALITY_QUALIFIED"
QUALIFICATION_AUTOMATIC = "PROFILE_DRIVEN_AUTOMATIC_GMAIL_QUALIFIED"
QUALIFICATION_PASS = "PROFILE_DRIVEN_TESTBOT_PASS"
QUALIFICATION_COWORKER_REPLY = "PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED"

ORACLE_VERSION = "profile_testbot_oracle_v1"
GENERATOR_PROMPT_VERSION = "profile_testbot_generator_v1"
GENERATOR_MODEL = "deterministic-template-v1"

SEND_BEHAVIORS = frozenset(
    {
        "observe_only",
        "draft_for_approval",
        "send_after_approval",
        "automatic_safe_send",
        "hold",
        "reject",
        "no_reply",
    }
)

OPERATOR_STOP_SEMI_AUTO = (
    "OPERATOR ACTION REQUIRED — Godkänn 40-scenario live semi-auto Gmail-kampanj"
)
OPERATOR_STOP_SEMI_AUTO_RUNNER = (
    "OPERATOR ACTION REQUIRED — Godkänn faktisk 40-scenario live semi-auto Gmail-kampanj på mergad runner-SHA"
)
OPERATOR_STOP_AUTOMATIC = (
    "OPERATOR ACTION REQUIRED — Godkänn automatic Gmail canary"
)
OPERATOR_STOP_LIVE_QUALITY = (
    "OPERATOR ACTION REQUIRED — Godkänn live inbox quality canary/campaign"
)
OPERATOR_STOP_LIVE_QUALITY_RUNNER = (
    "OPERATOR ACTION REQUIRED — Godkänn live quality execution på mergad runner-SHA"
)

QUALITY_LIVE_PROFILE_ID = "niklas-demo-live-eval-v1"
