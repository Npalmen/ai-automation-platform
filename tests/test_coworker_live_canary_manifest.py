"""Coworker live canary manifest contract tests (Gate R3)."""

from __future__ import annotations

from app.evaluation.profile_testbot.qualification.coworker_live_canary_manifest import (
    COWORKER_LIVE_CANARY_FAMILY_MIN,
    COWORKER_LIVE_CANARY_HOLD_MIN,
    COWORKER_LIVE_CANARY_MULTI_TURN_MIN,
    COWORKER_LIVE_CANARY_SEND_MAX,
    COWORKER_LIVE_CANARY_TARGET,
    build_coworker_live_canary_manifest,
    validate_coworker_live_canary_budget,
)


class TestCoworkerLiveCanaryManifest:
    def test_locked_manifest_meets_r3_budget(self):
        manifest = build_coworker_live_canary_manifest()
        assert manifest.scenario_count == COWORKER_LIVE_CANARY_TARGET
        assert manifest.send_budget <= COWORKER_LIVE_CANARY_SEND_MAX
        assert manifest.hold_reject_no_reply_count >= COWORKER_LIVE_CANARY_HOLD_MIN
        assert manifest.multi_turn_count >= COWORKER_LIVE_CANARY_MULTI_TURN_MIN
        assert len(manifest.family_distribution) >= COWORKER_LIVE_CANARY_FAMILY_MIN
        assert validate_coworker_live_canary_budget(manifest.scenarios) == []
