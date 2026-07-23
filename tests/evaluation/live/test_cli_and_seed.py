"""CLI and seed-script guard tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def test_validate_config_reports_issues_when_gates_missing(monkeypatch):
    monkeypatch.delenv("LIVE_EVAL_ALLOWED", raising=False)
    monkeypatch.setenv("ENV", "test")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_live_eval.py"), "validate-config"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**dict(**{k: v for k, v in __import__("os").environ.items()}), "ENV": "test"},
    )
    get_live_eval_config.cache_clear()
    assert completed.returncode == 1
    payload = json.loads(completed.stdout)
    assert payload["ready"] is False


def test_dry_run_offline(monkeypatch, tmp_path):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_live_eval.py"), "dry-run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    get_live_eval_config.cache_clear()
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["transition_count"] == 2
    assert Path(payload["report_path"]).exists()


def test_seed_script_sets_intake_cutoff_at(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    from scripts.seed_live_eval_tenant import seed_intake_cutoff_at

    cutoff = seed_intake_cutoff_at()
    assert "T" in cutoff
    assert cutoff != "2020"


def test_seed_script_defaults_to_dry_run(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "seed_live_eval_tenant.py"),
            "--tenant-id",
            "TENANT_LIVE_EVAL",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
