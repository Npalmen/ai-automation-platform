"""Regression tests for observe campaign scenario filtering."""

from __future__ import annotations

import pytest

from app.evaluation.live.campaign.registry import clear_campaign_registry_cache
from app.evaluation.live.campaign.runner import run_observe_campaign


@pytest.fixture(autouse=True)
def _clear_registry():
    clear_campaign_registry_cache()
    yield
    clear_campaign_registry_cache()


@pytest.fixture
def observe_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    monkeypatch.setenv("LIVE_EVAL_MAX_SCENARIOS_PER_RUN", "1")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_SENDS", "1")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_REPLIES", "0")
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_run_observe_campaign_accepts_scenario_ids(observe_env, monkeypatch):
    captured_scenario_ids: list[str] = []

    class _FakeRunner:
        def __init__(self, **kwargs):
            captured_scenario_ids.append(kwargs["scenario_id"])

        def run(self):
            return 0

        @property
        def observer(self):
            class _Observer:
                def get_observation(self, _run_id):
                    return {"job": {}}

            return _Observer()

    monkeypatch.setattr("app.evaluation.live.campaign.runner.LiveEvalRunner", _FakeRunner)
    monkeypatch.setattr(
        "app.evaluation.live.campaign.runner.validate_no_production_resources",
        lambda **kwargs: [],
    )

    result = run_observe_campaign(
        base_url="http://127.0.0.1:8010",
        admin_api_key="key",
        scenario_ids=("TBS03_invoice_observe", "TBS04_unknown_observe"),
    )

    assert captured_scenario_ids == [
        "TBS03_invoice_observe",
        "TBS04_unknown_observe",
    ]
    assert result.overall_status == "passed"
    assert result.sends == 2
    assert result.selected_scenario_budget is not None
    assert result.selected_scenario_budget.selected_scenario_count == 2


def test_observe_subset_overall_passes_when_two_of_two(observe_env, monkeypatch):
    class _FakeRunner:
        def __init__(self, **_kwargs):
            pass

        def run(self):
            return 0

        @property
        def observer(self):
            class _Observer:
                def get_observation(self, _run_id):
                    return {"job": {}}

            return _Observer()

    monkeypatch.setattr("app.evaluation.live.campaign.runner.LiveEvalRunner", _FakeRunner)
    monkeypatch.setattr(
        "app.evaluation.live.campaign.runner.validate_no_production_resources",
        lambda **kwargs: [],
    )

    result = run_observe_campaign(
        base_url="http://127.0.0.1:8010",
        admin_api_key="key",
        scenario_ids=("TBS03_invoice_observe", "TBS04_unknown_observe"),
    )

    assert result.overall_status == "passed"
    assert len(result.scenario_results) == 2


def test_observe_subset_failure_when_runner_fails(observe_env, monkeypatch):
    class _FakeRunner:
        def __init__(self, **_kwargs):
            pass

        def run(self):
            return 1

        @property
        def observer(self):
            class _Observer:
                def get_observation(self, _run_id):
                    return {"job": {}}

            return _Observer()

    monkeypatch.setattr("app.evaluation.live.campaign.runner.LiveEvalRunner", _FakeRunner)
    monkeypatch.setattr(
        "app.evaluation.live.campaign.runner.validate_no_production_resources",
        lambda **kwargs: [],
    )

    result = run_observe_campaign(
        base_url="http://127.0.0.1:8010",
        admin_api_key="key",
        scenario_ids=("TBS03_invoice_observe", "TBS04_unknown_observe"),
    )

    assert result.overall_status == "failed"


def test_observe_full_campaign_still_runs_five_without_filter(observe_env, monkeypatch):
    captured_scenario_ids: list[str] = []

    class _FakeRunner:
        def __init__(self, **kwargs):
            captured_scenario_ids.append(kwargs["scenario_id"])

        def run(self):
            return 0

        @property
        def observer(self):
            class _Observer:
                def get_observation(self, _run_id):
                    return {"job": {}}

            return _Observer()

    monkeypatch.setattr("app.evaluation.live.campaign.runner.LiveEvalRunner", _FakeRunner)
    monkeypatch.setattr(
        "app.evaluation.live.campaign.runner.validate_no_production_resources",
        lambda **kwargs: [],
    )

    result = run_observe_campaign(
        base_url="http://127.0.0.1:8010",
        admin_api_key="key",
    )

    assert len(captured_scenario_ids) == 5
    assert result.sends == 5
    assert result.overall_status == "passed"
