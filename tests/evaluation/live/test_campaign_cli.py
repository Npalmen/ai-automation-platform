"""CLI argument parsing for full-system testbot campaign runner."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "run_full_system_testbot_campaign.py"


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_run_subcommand_accepts_tenant_and_app_base_url():
    result = _run_cli(
        "run",
        "--campaign-type",
        "transport-smoke",
        "--tenant-id",
        "TENANT_LIVE_EVAL",
        "--app-base-url",
        "http://127.0.0.1:8010",
    )
    assert "unrecognized arguments" not in result.stderr
    assert result.returncode == 2
    assert "ERROR: live campaign requires --confirm-external" in result.stdout
