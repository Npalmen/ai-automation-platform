"""Sender transport gate and readiness tests."""

from __future__ import annotations

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.gmail_transport import run_sender_readiness
from app.evaluation.live.safety import require_live_eval_external_mutation_enabled, require_scenario_allowed_for_2f2


def test_external_mutation_gate_requires_side_effect_flag(live_eval_env, monkeypatch):
    monkeypatch.delenv("EXTERNAL_SIDE_EFFECT_TESTS", raising=False)
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    with pytest.raises(LiveEvalSafetyError, match="EXTERNAL_SIDE_EFFECT_TESTS"):
        require_live_eval_external_mutation_enabled()


def test_external_mutation_gate_passes_with_flag(live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    require_live_eval_external_mutation_enabled()


def test_scenario_allowlist(live_eval_env):
    require_scenario_allowed_for_2f2("S01_lead_laddbox_quality")
    with pytest.raises(LiveEvalSafetyError):
        require_scenario_allowed_for_2f2("S99_unknown")


def test_sender_readiness_fails_without_credentials(live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    report = run_sender_readiness(
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
    )
    assert report.ready is False
    assert report.issues
