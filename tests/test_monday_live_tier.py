"""Monday live test tier infrastructure (live E2E test count = 0).

Future live tests must:
- use @pytest.mark.monday_live
- target a dedicated Monday test board
- require explicit side-effect opt-in and cleanup

Run the live tier with:
  RUN_MONDAY_LIVE_TESTS=yes MONDAY_API_KEY=... python -m pytest -m monday_live
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_monday_live_test_count_is_zero():
    env = dict(os.environ)
    env["RUN_MONDAY_LIVE_TESTS"] = "yes"
    env["MONDAY_API_KEY"] = "test-key"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "monday_live"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 5, result.stdout + result.stderr
    assert "no tests collected" in (result.stdout + result.stderr).lower()


def test_monday_live_tier_requires_api_key():
    env = dict(os.environ)
    env["RUN_MONDAY_LIVE_TESTS"] = "yes"
    env.pop("MONDAY_API_KEY", None)
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "monday_live"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 4
    assert "MONDAY_API_KEY" in result.stderr
