#!/usr/bin/env python3
"""R3 live canary preflight for digital coworker reply quality (no Gmail sends)."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "storage" / "status"
sys.path.insert(0, str(ROOT))

from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (  # noqa: E402
    QUALIFIED_REPLY_SHA,
    R3_APPROVED_SEND_BODY_HASHES,
    assert_r3_code_equivalence,
    evaluate_coworker_r3_readiness,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (  # noqa: E402
    build_r3_diagnostic_live_render_rows,
    build_r3_frozen_execution_rows,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bodies import (  # noqa: E402
    resolve_frozen_send_bodies,
)

PROFILE_ID = "niklas-demo-live-eval-v1"
TENANT_ID = "TENANT_LIVE_EVAL"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git_sha(ref: str = "HEAD") -> str:
    proc = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "").strip()


def _redact_email(value: str | None) -> str:
    if not value:
        return ""
    local, _, domain = value.partition("@")
    if not domain:
        return "[REDACTED_EMAIL]"
    return f"{local[:2]}…@{domain}"


def _load_live_eval_env(*, runner_sha: str) -> None:
    try:
        from dotenv import dotenv_values
    except ImportError:
        dotenv_values = None  # type: ignore[assignment,misc]

    for path in (ROOT / ".env", ROOT / ".env.live-eval.local"):
        if not path.is_file():
            continue
        if dotenv_values is not None:
            for key, value in dotenv_values(path).items():
                if value is not None and str(value).strip():
                    os.environ[key] = str(value).strip()
        else:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

    os.environ["ENV"] = "test"
    os.environ["BUILD_GIT_SHA"] = runner_sha
    os.environ["BUILD_COMMIT_SHA"] = runner_sha
    os.environ["GIT_COMMIT"] = runner_sha
    os.environ["LIVE_EVAL_ALLOWED"] = "yes"
    os.environ["LIVE_GMAIL_EVAL_ALLOWED"] = "yes"
    os.environ["LIVE_LLM_EVAL_ALLOWED"] = "yes"
    os.environ["FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED"] = "yes"
    os.environ["PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED"] = "yes"
    os.environ["PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA"] = runner_sha
    os.environ["PROFILE_TESTBOT_LIVE_QUALITY_APPROVED"] = "yes"
    os.environ["PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED"] = "yes"
    os.environ["PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED_SHA"] = runner_sha
    os.environ.pop("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT", None)

    client_id = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_ID", "").strip()
    client_secret = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_SECRET", "").strip()
    if client_id:
        os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", client_id)
    if client_secret:
        os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", client_secret)

    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def _approval_operation_id(campaign_id: str, scenario_id: str) -> str:
    return f"{campaign_id}:{scenario_id}:approval"


def _reply_operation_id(scenario_id: str) -> str:
    return f"reply-op-{scenario_id.lower()}"


def _body_hash(text: str) -> str:
    from app.workflows.reply_quality.provenance import hash_body

    return hash_body(text)


def _scan_for_secrets(payload: str) -> list[str]:
    issues: list[str] = []
    if re.search(r"(?i)(refresh_token|access_token|client_secret)\s*[:=]", payload):
        issues.append("token_or_secret_pattern")
    if re.search(r"ya29\.[A-Za-z0-9_-]+", payload):
        issues.append("oauth_access_token_pattern")
    if EMAIL_RE.search(payload) and "[REDACTED_EMAIL]" not in payload:
        raw_emails = EMAIL_RE.findall(payload)
        allowed = {"sender@eval.test"}
        if any(email not in allowed for email in raw_emails):
            issues.append("unredacted_email")
    return issues


def _load_render_package():
    pkg_path = ROOT / "scripts" / "build_digital_coworker_human_review_package.py"
    spec = importlib.util.spec_from_file_location(
        "build_digital_coworker_human_review_package",
        pkg_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load human review package builder")
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = pkg
    spec.loader.exec_module(pkg)
    return pkg


def _configure_render_env() -> dict[str, str | None]:
    keys = (
        "DIGITAL_COWORKER_REPLY_ENABLED",
        "DIGITAL_COWORKER_LLM_RENDER",
        "LLM_RETRY_ATTEMPTS",
    )
    previous = {key: os.environ.get(key) for key in keys}
    os.environ["DIGITAL_COWORKER_REPLY_ENABLED"] = "true"
    os.environ["DIGITAL_COWORKER_LLM_RENDER"] = "live"
    os.environ["LLM_RETRY_ATTEMPTS"] = "1"
    return previous


def _restore_render_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def build_preflight_reports(
    *,
    phase: str,
    campaign_id: str | None = None,
    instrumentation_merge_sha: str | None = None,
) -> dict[str, Any]:
    from app.evaluation.live.config import get_live_eval_config
    from app.evaluation.profile_testbot.qualification.constants import (
        NO_SEND_BEHAVIORS,
        PTB_SEM_0024_SCENARIO_ID,
        SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND,
    )
    from app.evaluation.profile_testbot.qualification.coworker_live_canary_manifest import (
        COWORKER_LIVE_CANARY_MANIFEST_HASH,
        build_coworker_live_canary_manifest,
    )
    from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import (
        run_hermetic_coworker_reply_qualification,
    )

    if phase not in {"predeploy", "postdeploy"}:
        raise ValueError(f"unsupported phase {phase!r}")

    instrumentation_merge_sha = instrumentation_merge_sha or _git_sha("HEAD")
    runner_sha = instrumentation_merge_sha
    _load_live_eval_env(runner_sha=runner_sha)

    pkg = _load_render_package()
    render_scenario_full = pkg.render_scenario_full
    redact_text = pkg.redact_text
    renderer_label = pkg._renderer_label

    campaign_id = campaign_id or str(uuid.uuid4())
    report_sha = instrumentation_merge_sha if phase == "postdeploy" else QUALIFIED_REPLY_SHA
    short = report_sha[:7]
    scenario_stop_conditions: list[str] = []

    code_equiv = assert_r3_code_equivalence(
        repo_root=ROOT,
        instrumentation_merge_sha=instrumentation_merge_sha,
    )
    if phase == "predeploy" and not code_equiv.passed:
        scenario_stop_conditions.append(code_equiv.assertion)
        if code_equiv.unexpected_files:
            scenario_stop_conditions.append(
                "unexpected non-instrumentation files: "
                + ", ".join(code_equiv.unexpected_files)
            )

    manifest = build_coworker_live_canary_manifest(profile_id=PROFILE_ID, seed=0)
    if manifest.manifest_hash != COWORKER_LIVE_CANARY_MANIFEST_HASH:
        scenario_stop_conditions.append("manifest hash drift")

    r1 = run_hermetic_coworker_reply_qualification(profile_id=PROFILE_ID)
    if r1.overall_status != "PASS" or r1.scenario_count != 120:
        scenario_stop_conditions.append(
            f"R1 hermetic failed: status={r1.overall_status} count={r1.scenario_count}"
        )

    config = get_live_eval_config()
    recipient = sorted(config.recipient_emails)[0] if config.recipient_emails else ""

    manifest_stub = {"approved_send_body_hashes": R3_APPROVED_SEND_BODY_HASHES}
    render_rows = build_r3_frozen_execution_rows(
        manifest=manifest_stub,
        campaign_id=campaign_id,
    )
    diagnostic_rows: list[dict[str, Any]] = []
    if phase == "postdeploy":
        previous_render_env = _configure_render_env()
        try:
            diagnostic_rows = build_r3_diagnostic_live_render_rows(campaign_id=campaign_id)
        finally:
            _restore_render_env(previous_render_env)

    planned_sends = [row for row in render_rows if row["planned_gmail_send"]]
    no_send_rows = [row for row in render_rows if not row["planned_gmail_send"]]
    if len(planned_sends) != manifest.send_budget:
        scenario_stop_conditions.append(
            f"planned sends {len(planned_sends)} != budget {manifest.send_budget}"
        )
    if len(no_send_rows) != manifest.hold_reject_no_reply_count:
        scenario_stop_conditions.append(
            f"no-send count {len(no_send_rows)} != {manifest.hold_reject_no_reply_count}"
        )

    readiness = evaluate_coworker_r3_readiness(
        phase=phase,  # type: ignore[arg-type]
        profile_id=PROFILE_ID,
        tenant_id=TENANT_ID,
        instrumentation_merge_sha=instrumentation_merge_sha,
        repo_root=ROOT,
        render_rows=render_rows,
        send_budget=len(planned_sends),
        no_send_count=len(no_send_rows),
        scenario_stop_conditions=scenario_stop_conditions,
    )

    report_blob = json.dumps(
        {
            "readiness": readiness.to_dict(),
            "code_equivalence": code_equiv.to_dict(),
            "render_rows": render_rows,
        },
        ensure_ascii=False,
    )
    secret_issues = _scan_for_secrets(report_blob)
    if secret_issues:
        readiness.stop_conditions.append(f"report secret scan failed: {secret_issues}")

    if phase == "predeploy":
        readiness.predeploy_preflight_pass = not readiness.stop_conditions
    else:
        readiness.postdeploy_preflight_pass = not readiness.stop_conditions
        readiness.r3_canary_ready_for_manual_send_approval = (
            readiness.postdeploy_preflight_pass
            and readiness.runner_ready_for_live_execution
            and not readiness.human_render_rereview_required
            and not readiness.stop_conditions
        )

    STATUS.mkdir(parents=True, exist_ok=True)
    manifest_path = STATUS / f"digital-coworker-r3-canary-manifest-{short}.json"
    readiness_path = STATUS / f"digital-coworker-r3-readiness-{short}.json"
    render_path = STATUS / f"digital-coworker-r3-render-review-{short}.md"
    preflight_path = STATUS / f"digital-coworker-r3-preflight-{short}.md"

    manifest_payload = {
        "qualified_reply_sha": QUALIFIED_REPLY_SHA,
        "instrumentation_merge_sha": instrumentation_merge_sha,
        "runner_sha": runner_sha,
        "api_runtime_sha": readiness.api_runtime_sha,
        "worker_runtime_sha": readiness.worker_runtime_sha,
        "phase": phase,
        "generated_at": _utc_now(),
        "campaign_id": campaign_id,
        "profile_id": PROFILE_ID,
        "tenant_id": TENANT_ID,
        "campaign_type": manifest.campaign_type,
        "manifest_hash": manifest.manifest_hash,
        "scenario_ids": manifest.scenario_ids,
        "family_distribution": manifest.family_distribution,
        "send_budget": manifest.send_budget,
        "hold_reject_no_reply_count": manifest.hold_reject_no_reply_count,
        "multi_turn_count": manifest.multi_turn_count,
        "planned_gmail_send_scenario_ids": [r["scenario_id"] for r in planned_sends],
        "planned_no_send_scenario_ids": [r["scenario_id"] for r in no_send_rows],
        "approved_send_body_hashes": R3_APPROVED_SEND_BODY_HASHES,
        "approved_send_body_texts": resolve_frozen_send_bodies(manifest_stub),
        "code_equivalence": code_equiv.to_dict(),
        "gmail_sent": False,
        "gmail_drafts_created": False,
        "predeploy_preflight_pass": readiness.predeploy_preflight_pass,
        "postdeploy_preflight_pass": readiness.postdeploy_preflight_pass,
        "r3_canary_ready_for_manual_send_approval": (
            readiness.r3_canary_ready_for_manual_send_approval
        ),
    }
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    readiness_payload = {
        **readiness.to_dict(),
        "merge_sha": report_sha,
        "generated_at": _utc_now(),
        "profile_id": PROFILE_ID,
        "tenant_id": TENANT_ID,
        "code_equivalence": code_equiv.to_dict(),
        "r1_hermetic": {
            "status": r1.overall_status,
            "scenario_count": r1.scenario_count,
            "hard_safety_pass_rate": r1.hard_safety_pass_rate,
        },
        "sender_email": _redact_email(
            sorted(config.sender_emails)[0] if config.sender_emails else ""
        ),
        "recipient_email": _redact_email(recipient),
    }
    readiness_path.write_text(
        json.dumps(readiness_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    render_lines = [
        f"# digital-coworker-r3-render-review-{short}.md",
        "",
        f"- phase: `{phase}`",
        f"- qualified_reply_sha: `{QUALIFIED_REPLY_SHA}`",
        f"- instrumentation_merge_sha: `{instrumentation_merge_sha}`",
        f"- runner_sha: `{runner_sha}`",
        f"- campaign_id: `{campaign_id}`",
        f"- human_render_rereview_required: **{readiness.human_render_rereview_required}**",
        f"- gmail_sent: **false**",
        "",
    ]
    for row in render_rows:
        render_lines.extend(
            [
                f"## {row['scenario_id']}",
                f"- planned_gmail_send: `{row['planned_gmail_send']}`",
                f"- approval_required: `{row['approval_required']}`",
                f"- renderer_mode: `{row['renderer_mode']}`",
                f"- fallback_stage: `{row['fallback_stage']}`",
                f"- body_hash: `{row['body_hash']}`",
                f"- approved_body_hash: `{row.get('approved_body_hash')}`",
                f"- body_hash_matches_approved: `{row.get('body_hash_matches_approved')}`",
                f"- planned_recipient: `{row['planned_recipient']}`",
                f"- approval_operation_id: `{row['approval_operation_id']}`",
                "",
                "### Final customer text (redacted)",
                "```",
                row["final_customer_text"] or "(empty — no customer draft)",
                "```",
                "",
            ]
        )
    render_path.write_text("\n".join(render_lines) + "\n", encoding="utf-8")

    preflight_lines = [
        f"# digital-coworker-r3-preflight-{short}.md",
        "",
        f"- phase: `{phase}`",
        f"- generated_at: `{_utc_now()}`",
        f"- qualified_reply_sha: `{QUALIFIED_REPLY_SHA}`",
        f"- instrumentation_merge_sha: `{instrumentation_merge_sha}`",
        f"- runner_sha: `{runner_sha}`",
        f"- api_runtime_sha: `{readiness.api_runtime_sha}`",
        f"- worker_runtime_sha: `{readiness.worker_runtime_sha}`",
        f"- runtime_sha_consistent: `{readiness.runtime_sha_consistent}`",
        f"- predeploy_preflight_pass: **{readiness.predeploy_preflight_pass}**",
        f"- postdeploy_preflight_pass: **{readiness.postdeploy_preflight_pass}**",
        f"- r3_execution_readiness: **{readiness.to_dict()['r3_execution_readiness']}**",
        f"- r3_canary_ready_for_manual_send_approval: **{readiness.r3_canary_ready_for_manual_send_approval}**",
        f"- human_render_rereview_required: **{readiness.human_render_rereview_required}**",
        f"- gmail_sent: **false**",
        "",
        "## Planned Gmail sends",
    ]
    for row in planned_sends:
        match = "MATCH" if row.get("body_hash_matches_approved") else "DRIFT"
        preflight_lines.append(
            f"- `{row['scenario_id']}` → `{row['planned_recipient']}` "
            f"({match}, hash `{row['body_hash'][:16]}…`)"
        )
    preflight_lines.extend(["", "## Stop conditions"])
    if readiness.stop_conditions:
        for issue in readiness.stop_conditions:
            preflight_lines.append(f"- BLOCK: {issue}")
    else:
        preflight_lines.append("- (none)")
    if readiness.unrelated_qualification_context:
        preflight_lines.extend(["", "## Unrelated qualification context (not R3 blockers)"])
        for item in readiness.unrelated_qualification_context:
            preflight_lines.append(f"- {item}")
    preflight_path.write_text("\n".join(preflight_lines) + "\n", encoding="utf-8")

    overall_pass = (
        readiness.predeploy_preflight_pass
        if phase == "predeploy"
        else readiness.postdeploy_preflight_pass
    )
    return {
        "preflight": preflight_path,
        "manifest": manifest_path,
        "render": render_path,
        "readiness_path": readiness_path,
        "preflight_pass": overall_pass,
        "readiness_result": readiness,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Digital coworker R3 preflight (no Gmail)")
    parser.add_argument(
        "--phase",
        choices=("predeploy", "postdeploy"),
        default="predeploy",
        help="Preflight phase",
    )
    parser.add_argument("--campaign-id", default="", help="Optional fixed campaign UUID")
    parser.add_argument(
        "--instrumentation-merge-sha",
        default="",
        help="Instrumentation merge SHA (defaults to HEAD)",
    )
    args = parser.parse_args()

    result = build_preflight_reports(
        phase=args.phase,
        campaign_id=args.campaign_id or None,
        instrumentation_merge_sha=args.instrumentation_merge_sha or None,
    )
    for key in ("preflight", "manifest", "render", "readiness_path"):
        if key in result and hasattr(result[key], "exists"):
            print(f"wrote {result[key]}")
    readiness = result["readiness_result"]
    if not result["preflight_pass"]:
        print(f"R3 {args.phase} preflight FAILED", file=sys.stderr)
        return 1
    if args.phase == "postdeploy" and readiness.human_render_rereview_required:
        print("HUMAN RENDER RE-REVIEW REQUIRED", file=sys.stderr)
        return 2
    if args.phase == "postdeploy" and readiness.r3_canary_ready_for_manual_send_approval:
        print("MANUAL APPROVAL REQUIRED — Godkänn exakt åtta R3 Gmail-sändningar till ni…@sol-f.se")
        return 0
    print(f"R3 {args.phase} preflight PASS — Gmail not sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
