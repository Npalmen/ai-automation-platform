"""Hermetic live runner state machine tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.evaluation.live.runner import LiveEvalRunner


def test_runner_unresolved_send_on_transport_failure(live_eval_env, monkeypatch, tmp_path):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    runner = LiveEvalRunner(
        base_url="http://localhost:8010",
        admin_api_key="key",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
    )
    with patch.object(
        runner.observer, "runtime_readiness", return_value={"env": "test", "build_git_sha": ""}
    ), patch.object(runner.observer, "register_run"), patch.object(
        runner.observer, "get_run", return_value={"config_hash": "abc", "expires_at": None}
    ), patch(
        "app.evaluation.live.runner.run_sender_readiness",
        return_value=MagicMock(ready=True, issues=[]),
    ), patch(
        "app.evaluation.live.runner.send_scenario_email",
        side_effect=RuntimeError("network"),
    ), patch(
        "app.evaluation.live.runner.reconcile_sent_message",
        return_value=None,
    ), patch.object(runner.observer, "complete_run"):
        code = runner.run()
    get_live_eval_config.cache_clear()
    assert code == 4
