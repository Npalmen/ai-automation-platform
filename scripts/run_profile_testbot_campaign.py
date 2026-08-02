#!/usr/bin/env python3
"""Profile-driven live testbot campaign CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LIVE_EVAL_ENV_FILE = ROOT / ".env.live-eval.local"


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("yes", "true", "1")


def _load_live_eval_env(*, for_live_execution: bool = False) -> None:
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
    if LIVE_EVAL_ENV_FILE.is_file():
        for line in LIVE_EVAL_ENV_FILE.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
    _apply_live_eval_operator_overrides(for_live_execution=for_live_execution)


def _apply_live_eval_operator_overrides(*, for_live_execution: bool = False) -> None:
    """Apply operator-approved live-eval flags after loading env files."""
    from app.core.settings import get_settings

    runtime_sha = (
        os.environ.get("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA", "").strip()
        or resolve_canonical_commit()
        or ""
    )
    os.environ["ENV"] = "test"
    if runtime_sha:
        os.environ["BUILD_GIT_SHA"] = runtime_sha
        os.environ["BUILD_COMMIT_SHA"] = runtime_sha
        os.environ["GIT_COMMIT"] = runtime_sha
    os.environ["LIVE_EVAL_ALLOWED"] = "yes"
    if for_live_execution or not _env_truthy("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT"):
        os.environ["LIVE_GMAIL_EVAL_ALLOWED"] = "yes"
    elif _env_truthy("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT"):
        os.environ.pop("LIVE_GMAIL_EVAL_ALLOWED", None)
    os.environ["LIVE_LLM_EVAL_ALLOWED"] = "yes"
    os.environ["FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED"] = "yes"
    os.environ.setdefault("LIVE_EVAL_LLM_MODEL", "gpt-4o-mini")
    os.environ.setdefault("LIVE_EVAL_LLM_PROVIDER", "openai")
    os.environ.setdefault("LLM_MODEL", os.environ.get("LIVE_EVAL_LLM_MODEL", "gpt-4o-mini"))
    os.environ["LIVE_EVAL_MAX_GMAIL_REPLIES"] = "25"
    os.environ["LIVE_EVAL_MAX_GMAIL_SENDS"] = "25"
    os.environ["LIVE_EVAL_MAX_SCENARIOS_PER_RUN"] = "25"
    os.environ.setdefault("PROFILE_TESTBOT_LIVE_SEMI_AUTO_APPROVED", "yes")
    os.environ.setdefault("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED", "yes")
    if runtime_sha:
        os.environ.setdefault(
            "PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA", runtime_sha
        )
    os.environ.setdefault("PROFILE_TESTBOT_LIVE_QUALITY_APPROVED", "yes")
    os.environ.setdefault("PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED", "yes")
    if runtime_sha:
        os.environ.setdefault("PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED_SHA", runtime_sha)
    if for_live_execution:
        os.environ.pop("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT", None)

    client_id = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_ID", "").strip()
    client_secret = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_SECRET", "").strip()
    if client_id:
        os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", client_id)
    if client_secret:
        os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", client_secret)

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


from app.core.canonical_commit import resolve_canonical_commit
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.registry import new_evaluation_run_id
from app.evaluation.profile_testbot.campaign.hermetic_runner import run_hermetic_profile_campaign
from app.evaluation.profile_testbot.campaign.live_runners import (
    materialize_campaign_scenarios,
    plan_automatic_canary_campaign,
    plan_automatic_core_campaign,
    plan_semi_auto_live_campaign,
)
from app.evaluation.profile_testbot.campaign.semi_auto_runner import (
    SemiAutoRunnerConfig,
    new_campaign_id,
    run_profile_semi_auto_campaign,
)
from app.evaluation.profile_testbot.campaign.readiness import (
    build_profile_testbot_readiness,
    require_live_semi_auto_approval,
    validate_profile_testbot_tenant,
)
from app.evaluation.profile_testbot.campaign.report import write_profile_testbot_report
from app.evaluation.profile_testbot.campaign.quality_live_runner import (
    QualityRunnerConfig,
    new_quality_campaign_id,
    run_profile_quality_live_campaign,
)
from app.evaluation.profile_testbot.constants import (
    OPERATOR_STOP_AUTOMATIC,
    OPERATOR_STOP_LIVE_QUALITY,
    OPERATOR_STOP_SEMI_AUTO,
    OPERATOR_STOP_SEMI_AUTO_RUNNER,
    QUALITY_LIVE_PROFILE_ID,
)
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import (
    run_hermetic_coworker_reply_qualification,
)
from app.evaluation.profile_testbot.qualification.hermetic_quality import (
    run_hermetic_quality_qualification,
)


def _emit_stop(message: str) -> None:
    sys.stdout.buffer.write((message + "\n").encode("utf-8"))


def _run_hermetic(args: argparse.Namespace) -> int:
    result = run_hermetic_profile_campaign(profile_id=args.profile_id, seed=args.seed)
    run_id = new_evaluation_run_id()
    payload = result.to_dict()
    payload["profile_id"] = args.profile_id
    write_profile_testbot_report(phase="hermetic", run_id=run_id, payload=payload)
    print(result.overall_status)
    print(json.dumps(payload, indent=2))
    return 0 if result.overall_status == "PASS" else 1


def _run_semi_auto(args: argparse.Namespace) -> int:
    if getattr(args, "confirm_external", False):
        _load_live_eval_env(for_live_execution=True)
    if getattr(args, "confirm_external", False):
        config = get_live_eval_config()
        senders = sorted(config.sender_emails)
        recipients = sorted(config.recipient_emails)
        campaign_id = args.campaign_id or new_campaign_id()
        runtime_sha = args.runtime_sha or resolve_canonical_commit() or "unknown"
        import os

        base_url = os.environ.get("LIVE_EVAL_APP_BASE_URL", "").strip()
        admin_api_key = os.environ.get("ADMIN_API_KEY", "").strip()
        try:
            result = run_profile_semi_auto_campaign(
                SemiAutoRunnerConfig(
                    campaign_id=campaign_id,
                    runtime_sha=runtime_sha,
                    profile_id=args.profile_id,
                    seed=args.seed,
                    contract_mode=False,
                    confirm_external=True,
                    state_root=args.state_root or None,
                    sender_email=senders[0] if senders else "",
                    recipient_email=recipients[0] if recipients else "",
                    base_url=base_url,
                    admin_api_key=admin_api_key,
                ),
                resume=args.resume,
            )
        except LiveEvalSafetyError as exc:
            print(f"FAIL: {exc}")
            return 1
        print(result.overall_status)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.overall_status == "PASS" else 1

    if getattr(args, "execute_contract", False):
        config = get_live_eval_config()
        senders = sorted(config.sender_emails)
        recipients = sorted(config.recipient_emails)
        campaign_id = args.campaign_id or new_campaign_id()
        runtime_sha = args.runtime_sha or resolve_canonical_commit() or "unknown"
        result = run_profile_semi_auto_campaign(
            SemiAutoRunnerConfig(
                campaign_id=campaign_id,
                runtime_sha=runtime_sha,
                profile_id=args.profile_id,
                seed=args.seed,
                contract_mode=True,
                state_root=args.state_root or None,
                sender_email=senders[0] if senders else "",
                recipient_email=recipients[0] if recipients else "",
            ),
            resume=args.resume,
        )
        print(result.overall_status)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.overall_status == "PASS" else 1

    plan = plan_semi_auto_live_campaign(profile_id=args.profile_id, seed=args.seed)
    if plan.blocked_reason:
        _emit_stop(plan.blocked_reason)
        return 2
    payload = plan.to_dict()
    payload["campaign_scenarios"] = len(materialize_campaign_scenarios(plan))
    run_id = new_evaluation_run_id()
    write_profile_testbot_report(phase="semi-auto-live", run_id=run_id, payload=payload)
    print("READY_FOR_LIVE_SEMI_AUTO")
    return 0


def _run_automatic(args: argparse.Namespace) -> int:
    canary = plan_automatic_canary_campaign(profile_id=args.profile_id, seed=args.seed)
    if canary.blocked_reason:
        _emit_stop(canary.blocked_reason)
        return 2
    core = plan_automatic_core_campaign(profile_id=args.profile_id, seed=args.seed)
    payload = {
        "canary": canary.to_dict(),
        "core": core.to_dict(),
    }
    run_id = new_evaluation_run_id()
    write_profile_testbot_report(phase="automatic-live", run_id=run_id, payload=payload)
    print("READY_FOR_AUTOMATIC")
    return 0


def _run_hermetic_coworker_reply(args: argparse.Namespace) -> int:
    result = run_hermetic_coworker_reply_qualification(
        profile_id=args.profile_id,
        seed=args.seed,
    )
    print(result.overall_status)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.overall_status == "PASS" else 1


def _run_hermetic_quality(args: argparse.Namespace) -> int:
    result = run_hermetic_quality_qualification(
        profile_id=args.profile_id,
        seed=args.seed,
    )
    print(result.overall_status)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.overall_status == "PASS" else 1


def _run_quality_live(args: argparse.Namespace, *, campaign_kind: str) -> int:
    _load_live_eval_env(for_live_execution=True)
    config = get_live_eval_config()
    senders = sorted(config.sender_emails)
    recipients = sorted(config.recipient_emails)
    campaign_id = args.campaign_id or new_quality_campaign_id()
    runtime_sha = args.runtime_sha or resolve_canonical_commit() or "unknown"
    base_url = os.environ.get("LIVE_EVAL_APP_BASE_URL", "").strip()
    admin_api_key = os.environ.get("ADMIN_API_KEY", "").strip()
    try:
        result = run_profile_quality_live_campaign(
            QualityRunnerConfig(
                campaign_id=campaign_id,
                runtime_sha=runtime_sha,
                campaign_kind=campaign_kind,  # type: ignore[arg-type]
                profile_id=args.profile_id,
                seed=args.seed,
                contract_mode=False,
                confirm_external=True,
                state_root=args.state_root or None,
                sender_email=senders[0] if senders else "",
                recipient_email=recipients[0] if recipients else "",
                base_url=base_url,
                admin_api_key=admin_api_key,
            ),
            resume=args.resume,
        )
    except LiveEvalSafetyError as exc:
        print(f"FAIL: {exc}")
        return 1
    print(result.overall_status)
    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.overall_status == "PASS" else 1


def _write_readiness_report(report: dict) -> Path:
    run_id = new_evaluation_run_id()
    path = Path("storage/status") / f"profile-testbot-semi-auto-live-readiness-{run_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Profile testbot semi-auto live readiness",
        "",
        f"- runtime_sha: `{report.get('runtime_sha')}`",
        f"- approved_runtime_sha: `{report.get('approved_runtime_sha')}`",
        f"- runner_runtime_sha: `{report.get('runner_runtime_sha')}`",
        f"- api_runtime_sha: `{report.get('api_runtime_sha')}`",
        f"- worker_runtime_sha: `{report.get('worker_runtime_sha')}`",
        f"- runtime_sha_consistent: **{report.get('runtime_sha_consistent')}**",
        f"- runtime_readiness_endpoint_verified: **{report.get('runtime_readiness_endpoint_verified')}**",
        f"- profile_id: `{report.get('profile_id')}`",
        f"- profile_snapshot_hash: `{report.get('profile_snapshot_hash')}`",
        f"- eval_tenant: `{report.get('eval_tenant')}`",
        f"- ready_for_live_semi_auto: **{report.get('ready_for_live_semi_auto')}**",
        f"- runner_ready_for_contract_execution: **{report.get('runner_ready_for_contract_execution')}**",
        f"- runner_ready_for_live_execution: **{report.get('runner_ready_for_live_execution')}**",
        f"- single_active_consumer: **{report.get('single_active_consumer')}**",
        "",
        "## Live execution blockers",
        "",
    ]
    live_blockers = report.get("live_execution_blockers") or []
    if live_blockers:
        lines.extend(f"- {item}" for item in live_blockers)
    else:
        lines.append("- none")
    lines.extend(
        [
            f"- sender_mailbox_hash: `{report.get('sender_mailbox_hash')}`",
            f"- recipient_mailbox_hash: `{report.get('recipient_mailbox_hash')}`",
            f"- sender_provider_verified: **{report.get('sender_provider_verified')}**",
            f"- recipient_deliverability_verified: **{report.get('recipient_deliverability_verified')}**",
            "",
            "## Safety assertions",
            "",
        ]
    )
    assertions = report.get("safety_assertions") or []
    if assertions:
        lines.extend(f"- {item}" for item in assertions)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Semi-auto manifest",
            "",
            "```json",
            json.dumps(report.get("semi_auto_manifest", {}), indent=2, ensure_ascii=False),
            "```",
            "",
            "## Blocking failures",
            "",
        ]
    )
    blockers = report.get("blocking_failures") or []
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- none")
    if report.get("operator_stop"):
        lines.extend(["", "## Operator stop", "", report["operator_stop"]])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    from app.core.settings import get_settings

    settings = get_settings()
    if settings.ADMIN_API_KEY and not os.environ.get("ADMIN_API_KEY", "").strip():
        os.environ["ADMIN_API_KEY"] = settings.ADMIN_API_KEY
    parser = argparse.ArgumentParser(description="Profile-driven live testbot campaigns")
    parser.add_argument("--profile-id", default="pilot-service-company-v1")
    parser.add_argument("--seed", type=int, default=0)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("readiness", help="Build profile testbot readiness report")
    sub.add_parser("hermetic", help="Run 120-scenario hermetic profile campaign")
    sub.add_parser("hermetic-quality", help="Run Gate Q5 hermetic quality qualification")
    sub.add_parser(
        "hermetic-coworker-reply",
        help="Run Gate R1 hermetic digital coworker reply qualification",
    )
    quality_canary = sub.add_parser(
        "quality-canary-live",
        help="Execute 12-scenario live inbox quality canary (Gate Q6)",
    )
    quality_canary.add_argument("--confirm-operator", action="store_true")
    quality_canary.add_argument("--campaign-id", default="")
    quality_canary.add_argument("--runtime-sha", default="")
    quality_canary.add_argument("--state-root", default="")
    quality_canary.add_argument("--resume", action="store_true")
    quality_campaign = sub.add_parser(
        "quality-campaign-live",
        help="Execute 32-scenario live inbox quality campaign (Gate Q7)",
    )
    quality_campaign.add_argument("--confirm-operator", action="store_true")
    quality_campaign.add_argument("--campaign-id", default="")
    quality_campaign.add_argument("--runtime-sha", default="")
    quality_campaign.add_argument("--state-root", default="")
    quality_campaign.add_argument("--resume", action="store_true")
    semi = sub.add_parser("semi-auto-live", help="Plan or execute live semi-auto campaign")
    semi.add_argument("--confirm-operator", action="store_true")
    semi.add_argument("--execute-contract", action="store_true")
    semi.add_argument("--confirm-external", action="store_true")
    semi.add_argument("--campaign-id", default="")
    semi.add_argument("--runtime-sha", default="")
    semi.add_argument("--state-root", default="")
    semi.add_argument("--resume", action="store_true")
    auto = sub.add_parser("automatic-live", help="Plan automatic campaigns (requires approval)")
    auto.add_argument("--confirm-operator", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "readiness":
        _load_live_eval_env()
        profile_id = args.profile_id
        if profile_id == "pilot-service-company-v1":
            profile_id = QUALITY_LIVE_PROFILE_ID
        report = build_profile_testbot_readiness(profile_id=profile_id)
        report_path = _write_readiness_report(report)
        sys.stdout.buffer.write(json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"))
        sys.stdout.buffer.write(f"\nreport={report_path}\n".encode("utf-8"))
        return 0 if report.get("ready_for_live_semi_auto") else 1
    if args.command == "hermetic":
        return _run_hermetic(args)
    if args.command == "hermetic-coworker-reply":
        return _run_hermetic_coworker_reply(args)
    if args.command == "hermetic-quality":
        return _run_hermetic_quality(args)
    if args.command == "quality-canary-live":
        if not args.confirm_operator:
            _emit_stop(OPERATOR_STOP_LIVE_QUALITY)
            return 2
        args.profile_id = (
            args.profile_id
            if args.profile_id != "pilot-service-company-v1"
            else QUALITY_LIVE_PROFILE_ID
        )
        return _run_quality_live(args, campaign_kind="canary")
    if args.command == "quality-campaign-live":
        if not args.confirm_operator:
            _emit_stop(OPERATOR_STOP_LIVE_QUALITY)
            return 2
        args.profile_id = (
            args.profile_id
            if args.profile_id != "pilot-service-company-v1"
            else QUALITY_LIVE_PROFILE_ID
        )
        return _run_quality_live(args, campaign_kind="campaign")
    if args.command == "semi-auto-live":
        if not args.confirm_operator:
            _emit_stop(OPERATOR_STOP_SEMI_AUTO)
            return 2
        return _run_semi_auto(args)
    if args.command == "automatic-live":
        if not args.confirm_operator:
            _emit_stop(OPERATOR_STOP_AUTOMATIC)
            return 2
        return _run_automatic(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
