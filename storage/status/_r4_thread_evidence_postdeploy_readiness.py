"""Postdeploy readiness after thread-evidence propagation fix (write-free)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    runtime = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=str(ROOT),
        text=True,
    ).strip()
    os.environ["R4_POSTDEPLOY_RUNTIME_SHA"] = runtime
    os.environ["R4_POSTDEPLOY_REPORT_STEM"] = "r4-thread-evidence-postdeploy-readiness"
    script = ROOT / "storage" / "status" / "_r4_pr172_postdeploy_readiness.py"
    proc = subprocess.run([sys.executable, str(script)], cwd=str(ROOT))
    return int(proc.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
