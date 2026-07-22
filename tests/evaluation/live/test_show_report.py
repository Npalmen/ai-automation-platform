"""Defensive show-report redaction tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_show_report_redacts_nested_sensitive(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.evaluation.live.config import get_live_eval_config
    from app.evaluation.live.journal import ensure_run_directory

    get_live_eval_config.cache_clear()
    run_id = "run-show-report"
    directory = ensure_run_directory(run_id)
    payload = {
        "evaluation_run_id": run_id,
        "nested": {
            "refresh_token": "secret-refresh",
            "body_text": "full body should not appear",
            "items": [{"prompt": "system prompt"}],
        },
        "sender_gmail_message_id": "msg123",
    }
    (directory / "report.json").write_text(json.dumps(payload), encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_live_eval.py"), "show-report", "--run-id", run_id],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    get_live_eval_config.cache_clear()
    assert completed.returncode == 0, completed.stderr
    out = json.loads(completed.stdout)
    assert "refresh_token" not in completed.stdout.lower()
    assert "full body" not in completed.stdout
    assert "nested" in out


def test_show_report_invalid_json(tmp_path, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.evaluation.live.config import get_live_eval_config
    from app.evaluation.live.journal import ensure_run_directory

    get_live_eval_config.cache_clear()
    run_id = "run-bad-json"
    directory = ensure_run_directory(run_id)
    (directory / "report.json").write_text("{not-json", encoding="utf-8")

    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_live_eval.py"), "show-report", "--run-id", run_id],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    get_live_eval_config.cache_clear()
    assert completed.returncode == 1
    assert completed.stdout.strip() == ""
