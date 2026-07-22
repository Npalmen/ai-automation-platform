"""OAuth seed script guard tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_oauth_seed_dry_run(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "seed_live_eval_gmail_oauth.py"),
            "--tenant-id",
            "TENANT_LIVE_EVAL",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={
            **dict(__import__("os").environ),
            "ENV": "test",
            "LIVE_EVAL_ALLOWED": "yes",
            "LIVE_EVAL_TENANT_IDS": "TENANT_LIVE_EVAL",
        },
    )
    payload = json.loads(completed.stdout)
    assert payload["mode"] == "dry_run"
    assert "refresh_token" not in completed.stdout.lower()


def test_oauth_seed_apply_blocked_without_seed_allowed(monkeypatch):
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "seed_live_eval_gmail_oauth.py"),
            "--tenant-id",
            "TENANT_LIVE_EVAL",
            "--apply",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={
            **dict(__import__("os").environ),
            "ENV": "test",
            "LIVE_EVAL_ALLOWED": "yes",
            "LIVE_EVAL_TENANT_IDS": "TENANT_LIVE_EVAL",
        },
    )
    assert completed.returncode == 1
