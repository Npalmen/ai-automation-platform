"""CLI smoke tests for 2G batch runner."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _run_cli(mode: str, output_dir: Path) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    return subprocess.run(
        [
            sys.executable,
            "scripts/run_2g_batch.py",
            "--mode",
            mode,
            "--output-dir",
            str(output_dir),
            "--baseline-git-sha",
            "deadbeef",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_pr_batch_smoke(tmp_path: Path):
    output_dir = tmp_path / "pr"
    proc = _run_cli("pr", output_dir)
    assert proc.returncode == 0, proc.stderr
    report = json.loads((output_dir / "2g_batch_report.json").read_text(encoding="utf-8"))
    assert report["scenario_count"] == 60
    assert report["overall_status"] == "passed"
    assert (output_dir / "2g_failures.json").exists()
    assert (output_dir / "2g_coverage_report.json").exists()


def test_cli_main_batch_smoke(tmp_path: Path):
    output_dir = tmp_path / "main"
    proc = _run_cli("main", output_dir)
    assert proc.returncode == 0, proc.stderr
    report = json.loads((output_dir / "2g_batch_report.json").read_text(encoding="utf-8"))
    assert report["scenario_count"] == 160
    assert report["overall_status"] == "passed"
