"""Read-only rollback verification after automatic Gmail canary (harness only)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.campaign.automatic_readiness import (
    AUTOMATION_PHASE_RESTORED,
    validate_automatic_automation_readiness,
)
from app.evaluation.live.campaign.tenant_automation_lifecycle import (
    LIVE_EVAL_TENANT_ID,
    snapshot_tenant_config,
    verify_automation_not_broadly_enabled,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only rollback verification for TENANT_LIVE_EVAL"
    )
    parser.add_argument("--tenant-id", default=LIVE_EVAL_TENANT_ID)
    parser.add_argument(
        "--snapshot",
        default=os.environ.get("LIVE_EVAL_AUTOMATIC_CANARY_SNAPSHOT_PATH", ""),
    )
    parser.add_argument(
        "--expected-pre-run-hash",
        default="",
        help="Optional baseline hash from failed run artifact",
    )
    args = parser.parse_args(argv)

    snapshot_path = str(args.snapshot or "").strip()
    issues: list[str] = []
    report: dict = {"tenant_id": args.tenant_id, "read_only": True}

    runtime = snapshot_tenant_config(args.tenant_id)
    report["runtime_config_hash"] = runtime.config_hash
    issues.extend(verify_automation_not_broadly_enabled(runtime.auto_actions))

    expected_hash = str(args.expected_pre_run_hash or "").strip()
    if expected_hash and runtime.config_hash != expected_hash:
        issues.append(
            "runtime config hash does not match expected pre-run baseline"
        )
    report["expected_pre_run_hash"] = expected_hash or None

    if snapshot_path:
        phase_issues, phase_matrix = validate_automatic_automation_readiness(
            automation_phase=AUTOMATION_PHASE_RESTORED,
            tenant_id=args.tenant_id,
            baseline_snapshot_path=snapshot_path,
        )
        issues.extend(phase_issues)
        report["restored_phase"] = phase_matrix
    else:
        report["restored_phase"] = {"snapshot_path_configured": False}

    report["rollback_verified"] = not issues
    report["issues"] = issues
    print(json.dumps(report, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    raise SystemExit(main())
