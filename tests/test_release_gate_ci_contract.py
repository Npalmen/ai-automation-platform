"""CI contract tests for release-gate invocation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_release_gate_module_help_exits_zero():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_release_gate_r1", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
