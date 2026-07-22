"""Tests for resolved live-eval storage paths."""

from __future__ import annotations

from app.evaluation.live.paths import resolved_live_eval_root, resolved_run_directory, resolved_storage_path


def test_resolved_run_directory_uses_storage_path(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path / "ci-live-eval"))
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()

    run_dir = resolved_run_directory("run-abc")
    assert run_dir == (tmp_path / "ci-live-eval" / "live_eval" / "runs" / "run-abc").resolve()
    assert resolved_live_eval_root() == (tmp_path / "ci-live-eval" / "live_eval").resolve()
    assert resolved_storage_path() == (tmp_path / "ci-live-eval").resolve()

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
