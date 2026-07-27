"""Read-only live Gmail forensics CLI (zero writes)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.forensics.gmail_forensics import run_live_gmail_forensics
from app.evaluation.live.forensics.report import render_forensics_markdown
from app.evaluation.live.errors import LiveEvalSafetyError


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only live Gmail forensics")
    parser.add_argument("--evaluation-run-id", required=True)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--job-id", default="")
    parser.add_argument("--campaign-run-id", default="")
    parser.add_argument("--source-workflow-run", default="")
    parser.add_argument("--provider-message-id", default="")
    parser.add_argument("--inbound-rfc-message-id", default="")
    parser.add_argument("--adapter-recipient", default="")
    parser.add_argument("--runtime-sha", default=os.environ.get("BUILD_GIT_SHA", ""))
    parser.add_argument("--report-md", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    os.environ.setdefault("LIVE_EVAL_MAX_GMAIL_SENDS", "0")
    os.environ.setdefault("LIVE_EVAL_MAX_GMAIL_REPLIES", "0")

    report = run_live_gmail_forensics(
        evaluation_run_id=args.evaluation_run_id.strip(),
        scenario_id=args.scenario_id.strip(),
        job_id=args.job_id.strip() or None,
        campaign_run_id=args.campaign_run_id.strip() or None,
        source_workflow_run=args.source_workflow_run.strip() or None,
        provider_message_id=args.provider_message_id.strip() or None,
        inbound_rfc_message_id=args.inbound_rfc_message_id.strip() or None,
        adapter_recipient=args.adapter_recipient.strip() or None,
        runtime_sha=args.runtime_sha.strip() or None,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(render_forensics_markdown(report))

    if args.report_md:
        Path(args.report_md).write_text(render_forensics_markdown(report), encoding="utf-8")

    if report.credential_role_collision:
        print(
            "OPERATOR ACTION REQUIRED — Gmail credential role collision detected",
            file=sys.stderr,
        )
        return 2
    if not report.sender_identity.read_scope_verified or not report.recipient_identity.read_scope_verified:
        print(
            "OPERATOR ACTION REQUIRED — Uppdatera Gmail OAuth read-scope för live-eval",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LiveEvalSafetyError as exc:
        print(f"FORENSICS BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
