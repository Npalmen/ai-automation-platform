"""Kapitel 2F live-eval CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.constants import PYTEST_MARKER_EXPR, REPORT_SCHEMA_VERSION
from app.evaluation.live.gmail_transport import run_sender_readiness_read_only
from app.evaluation.live.journal import append_transition, load_transitions, run_directory, write_report_atomic
from app.evaluation.live.readiness import run_offline_readiness_checks
from app.evaluation.live.readiness_report import (
    account_fingerprint,
    build_readiness_report,
    write_readiness_report_atomic,
)
from app.evaluation.live.registry import new_evaluation_run_id
from app.evaluation.live.runner import LiveEvalRunner, cleanup_only
from app.evaluation.live.schemas import LiveEvalReport
from app.evaluation.live.subject_parser import build_subject_with_token, parse_subject_token


def _resolve_sender_recipient(config) -> tuple[str, str]:
    senders = sorted(config.sender_emails)
    recipients = sorted(config.recipient_emails)
    if len(senders) != 1 or len(recipients) != 1:
        raise SystemExit("Exactly one allowlisted sender and recipient required for run-scenario")
    return senders[0], recipients[0]


def _admin_http_context(args: argparse.Namespace) -> tuple[str, str]:
    base = (args.app_base_url or os.environ.get("LIVE_EVAL_APP_BASE_URL") or "").rstrip("/")
    admin_key = os.environ.get("ADMIN_API_KEY", "").strip()
    if not base or not admin_key:
        raise SystemExit("LIVE_EVAL_APP_BASE_URL and ADMIN_API_KEY required")
    return base, admin_key


def _fetch_runtime_and_recipient_readiness(
    *,
    base: str,
    admin_key: str,
    tenant_id: str,
) -> tuple[dict, dict, int]:
    import httpx

    response = httpx.get(
        f"{base}/admin/live-eval/runtime-readiness",
        headers={"X-Admin-API-Key": admin_key},
        timeout=30.0,
    )
    runtime = response.json()
    gmail_response = httpx.post(
        f"{base}/admin/live-eval/gmail-readiness",
        headers={"X-Admin-API-Key": admin_key},
        json={"tenant_id": tenant_id},
        timeout=30.0,
    )
    return runtime, gmail_response.json(), gmail_response.status_code


def _sender_readiness_payload(
    *,
    expected_sender: str,
    expected_recipient: str,
) -> dict:
    report = run_sender_readiness_read_only(
        expected_sender=expected_sender,
        expected_recipient=expected_recipient,
    )
    return {
        "ready": report.ready,
        "issues": report.issues,
        "sender_profile_match": bool(
            report.profile_email
            and report.profile_email == expected_sender.strip().lower()
            and report.read_scope_verified
        ),
        "read_scope_verified": report.read_scope_verified,
        "sender_account_fingerprint": account_fingerprint(expected_sender),
    }


def cmd_validate_config(args: argparse.Namespace) -> int:
    if args.gmail_readiness or args.sender_readiness:
        if not args.confirm_read_only:
            print(json.dumps({"ready": False, "issues": ["--confirm-read-only is required"]}, indent=2))
            return 1
        config = get_live_eval_config()
        issues: list[str] = []
        payload: dict = {"mode": "gmail_read_only"}

        if args.gmail_readiness:
            if not args.tenant_id:
                print(json.dumps({"ready": False, "issues": ["--tenant-id is required"]}, indent=2))
                return 1
            base, admin_key = _admin_http_context(args)
            runtime, gmail, gmail_status = _fetch_runtime_and_recipient_readiness(
                base=base,
                admin_key=admin_key,
                tenant_id=args.tenant_id,
            )
            payload["runtime"] = runtime
            payload["gmail"] = gmail
            if gmail_status != 200 or not runtime.get("database_ok") or not gmail.get("ready"):
                issues.append("recipient gmail readiness failed")

        if args.sender_readiness:
            try:
                sender, recipient = _resolve_sender_recipient(config)
            except SystemExit as exc:
                print(json.dumps({"ready": False, "issues": [str(exc)]}, indent=2))
                return 1
            sender_payload = _sender_readiness_payload(
                expected_sender=sender,
                expected_recipient=recipient,
            )
            payload["sender"] = sender_payload
            if not sender_payload["ready"]:
                issues.extend(sender_payload.get("issues") or [])

        payload["ready"] = not issues
        payload["issues"] = issues
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if not issues else 1

    report = run_offline_readiness_checks()
    payload = {
        "ready": report.ready,
        "issues": report.issues,
        "checks": report.checks,
        "pytest_marker_expr": PYTEST_MARKER_EXPR,
        "mode": "offline",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if report.ready else 1


def cmd_readiness_only(args: argparse.Namespace) -> int:
    if not args.confirm_read_only:
        print("--confirm-read-only is required", file=sys.stderr)
        return 2
    if not args.tenant_id:
        print("--tenant-id is required", file=sys.stderr)
        return 2
    if not args.report_file:
        print("--report-file is required", file=sys.stderr)
        return 2

    config = get_live_eval_config()
    base, admin_key = _admin_http_context(args)
    try:
        sender, recipient = _resolve_sender_recipient(config)
    except SystemExit:
        sender, recipient = "", ""

    issues: list[str] = []
    runtime, gmail, gmail_status = _fetch_runtime_and_recipient_readiness(
        base=base,
        admin_key=admin_key,
        tenant_id=args.tenant_id,
    )
    if gmail_status != 200 or not runtime.get("database_ok"):
        issues.append("runtime or recipient readiness HTTP failure")
    if not gmail.get("ready"):
        issues.extend(gmail.get("issues") or ["recipient gmail readiness failed"])

    sender_report = run_sender_readiness_read_only(
        expected_sender=sender,
        expected_recipient=recipient,
    )
    if not sender_report.ready:
        issues.extend(sender_report.issues)

    gmail_checks = gmail.get("checks") or {}
    recipient_profile = str(gmail_checks.get("gmail_profile_email") or "").strip().lower()
    recipient_profile_match = recipient_profile in config.recipient_emails and gmail.get("ready", False)
    label_present = bool(gmail_checks.get("label_present"))
    intake_query = str(gmail_checks.get("intake_query") or "")
    intake_query_valid = (
        f"label:{config.intake_label}".replace(" ", "").lower()
        in intake_query.replace(" ", "").lower()
    )

    workflow_sha = os.environ.get("BUILD_GIT_SHA") or os.environ.get("GITHUB_SHA")
    ready = not issues
    report = build_readiness_report(
        tenant_id=args.tenant_id,
        workflow_sha=workflow_sha,
        environment_status="live-gmail-eval",
        sender_profile_match=bool(
            sender_report.profile_email
            and sender_report.profile_email == sender
            and sender_report.read_scope_verified
        ),
        recipient_profile_match=recipient_profile_match,
        recipient_label_found=label_present,
        intake_query_valid=intake_query_valid,
        result="passed" if ready else "failed",
        failure_category=None if ready else "readiness_failed",
        sender_fingerprint=account_fingerprint(sender) if sender else None,
        recipient_fingerprint=account_fingerprint(recipient) if recipient else None,
        issues=issues,
        config=config,
    )
    write_readiness_report_atomic(args.report_file, report)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        lines = [
            "## Live Gmail readiness-only",
            f"- result: **{report['result']}**",
            f"- workflow_sha: `{workflow_sha or 'unknown'}`",
            f"- sender_profile_match: {report['sender_profile_match']}",
            f"- recipient_profile_match: {report['recipient_profile_match']}",
            f"- recipient_label_found: {report['recipient_label_found']}",
            f"- external_sends: {report['external_sends']}",
        ]
        Path(summary_path).write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if ready else 1


def cmd_dry_run(args: argparse.Namespace) -> int:
    config = get_live_eval_config()
    run_id = args.evaluation_run_id or new_evaluation_run_id()
    scenario_id = args.scenario_id or "S01_lead_laddbox_quality"
    attempt_id = args.attempt_id or 1
    subject = build_subject_with_token(
        evaluation_run_id=run_id,
        scenario_id=scenario_id,
        attempt_id=attempt_id,
        base_subject="Dry-run probe",
    )
    parsed = parse_subject_token(subject)
    if parsed is None:
        print("Subject parser failed", file=sys.stderr)
        return 1
    append_transition(run_id, {"state": "dry_run_started", "scenario_id": scenario_id})
    append_transition(
        run_id,
        {
            "state": "subject_parsed",
            "evaluation_run_id": parsed.evaluation_run_id,
            "scenario_id": parsed.scenario_id,
            "attempt_id": parsed.attempt_id,
        },
    )
    transitions = load_transitions(run_id)
    report = LiveEvalReport(
        evaluation_run_id=run_id,
        scenario_id=scenario_id,
        transport_mode="offline",
        ai_mode="fixture_ai",
        result="dry_run",
        state_transitions=transitions,
    )
    report_path = write_report_atomic(run_id, report)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        Path(summary_path).write_text(
            "\n".join(
                [
                    "## Live Gmail eval offline dry-run",
                    "- mode: **offline/hermetic**",
                    "- workflow_sha: _not applicable (offline dry-run)_",
                    f"- evaluation_run_id: `{run_id}`",
                    f"- transition_count: {len(transitions)}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "evaluation_run_id": run_id,
                "report_schema_version": REPORT_SCHEMA_VERSION,
                "report_path": str(report_path),
                "transition_count": len(transitions),
            },
            indent=2,
        )
    )
    return 0


def cmd_llm_readiness_only(args: argparse.Namespace) -> int:
    from app.evaluation.live.llm_readiness import (
        build_llm_readiness_artifact,
        run_llm_offline_readiness_checks,
        run_llm_readiness_checks,
    )
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    config = get_live_eval_config()
    issues: list[str] = []
    if args.tenant_id:
        db_url = os.environ.get("DATABASE_URL", "").strip()
        if db_url:
            engine = create_engine(db_url)
            Session = sessionmaker(bind=engine)
            session = Session()
            try:
                report = run_llm_readiness_checks(session, args.tenant_id, config=config)
                payload = build_llm_readiness_artifact(report)
                issues = report.issues
            finally:
                session.close()
                engine.dispose()
        else:
            report = run_llm_offline_readiness_checks(config)
            payload = build_llm_readiness_artifact(report)
            issues = report.issues
    else:
        report = run_llm_offline_readiness_checks(config)
        payload = build_llm_readiness_artifact(report)
        issues = report.issues

    if args.report_file:
        Path(args.report_file).write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        Path(summary_path).write_text(
            "\n".join(
                [
                    "## Live LLM readiness-only",
                    f"- result: **{'passed' if not issues else 'failed'}**",
                    f"- live_llm_calls: **0**",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if not issues else 1


def cmd_run_llm_s01(args: argparse.Namespace) -> int:
    if not args.confirm_external:
        print("--confirm-external is required", file=sys.stderr)
        return 2

    import httpx

    from app.evaluation.live.constants import S01_LOCKED_SCENARIO_HASH
    from app.evaluation.live.llm_assertions import assert_s01_live_llm_semantics
    from app.evaluation.live.llm_report import (
        build_live_eval_llm_failure_report,
        build_live_eval_llm_report,
        write_llm_failure_report_atomic,
        write_llm_report_atomic,
    )
    from app.evaluation.live.pipeline_poll import poll_pipeline_observation
    from app.evaluation.live.registry import new_evaluation_run_id

    config = get_live_eval_config()
    base = (args.app_base_url or os.environ.get("LIVE_EVAL_APP_BASE_URL") or "").rstrip("/")
    admin_key = os.environ.get("ADMIN_API_KEY", "").strip()
    tenant_id = args.tenant_id or next(iter(config.tenant_ids), "")
    if not base or not admin_key or not tenant_id:
        print("LIVE_EVAL_APP_BASE_URL, ADMIN_API_KEY, and tenant required", file=sys.stderr)
        return 2
    if not config.llm_provider or not config.llm_model:
        print("LIVE_EVAL_LLM_PROVIDER and LIVE_EVAL_LLM_MODEL required", file=sys.stderr)
        return 2

    run_id = args.evaluation_run_id or new_evaluation_run_id()
    scenario_id = args.scenario_id or "S01_lead_laddbox_quality"
    headers = {"X-Admin-API-Key": admin_key}
    failure_stage = "initialization"
    failure_category: str | None = None
    observation: dict = {}
    workflow_sha = os.environ.get("BUILD_GIT_SHA") or os.environ.get("GITHUB_SHA")

    if args.run_id_file:
        Path(args.run_id_file).write_text(run_id + "\n", encoding="utf-8")

    def _write_failure(
        *,
        stage: str,
        category: str | None,
        error: str | BaseException | None = None,
        obs: dict | None = None,
    ) -> None:
        payload = build_live_eval_llm_failure_report(
            evaluation_run_id=run_id,
            scenario_id=scenario_id,
            failure_stage=stage,
            failure_category=category,
            error=error,
            workflow_sha=workflow_sha,
            observation=obs or observation,
        )
        if args.failure_artifact_file:
            write_llm_failure_report_atomic(args.failure_artifact_file, payload)
        else:
            write_llm_failure_report_atomic(
                Path(os.environ.get("RUNNER_TEMP", ".")) / "llm_failure_report.json",
                payload,
            )

    try:
        failure_stage = "registration"
        register = httpx.post(
            f"{base}/admin/live-eval/runs",
            headers=headers,
            json={
                "evaluation_run_id": run_id,
                "tenant_id": tenant_id,
                "scenario_id": scenario_id,
                "attempt_id": args.attempt_id or 1,
                "transport_mode": "fixture_input",
                "ai_mode": "live_llm",
                "llm_provider": config.llm_provider,
                "llm_requested_model": config.llm_model,
            },
            timeout=30.0,
        )
        if register.status_code != 200:
            failure_category = "registration_failed"
            _write_failure(stage=failure_stage, category=failure_category, error=register.text)
            print(register.text, file=sys.stderr)
            return 1

        failure_stage = "fixture_intake"
        intake = httpx.post(
            f"{base}/admin/live-eval/runs/{run_id}/process-fixture-input",
            headers=headers,
            json={"tenant_id": tenant_id},
            timeout=120.0,
        )
        if intake.status_code != 200:
            failure_category = "provider_failure"
            _write_failure(stage=failure_stage, category=failure_category, error=intake.text)
            print(intake.text, file=sys.stderr)
            return 1

        failure_stage = "pipeline_poll"

        def _fetch_observation() -> dict:
            response = httpx.get(
                f"{base}/admin/live-eval/runs/{run_id}/observation",
                headers=headers,
                params={"tenant_id": tenant_id},
                timeout=30.0,
            )
            return response.json()

        try:
            observation = poll_pipeline_observation(_fetch_observation, timeout_seconds=120)
        except Exception as exc:
            print(f"pipeline poll failed: {exc}", file=sys.stderr)
            observation = _fetch_observation()

        failure_stage = "assertions"
        violations = assert_s01_live_llm_semantics(observation)
        result = "passed" if not violations else "failed"
        run_summary = observation.get("run") or {}

        failure_stage = "report"
        report = build_live_eval_llm_report(
            evaluation_run_id=run_id,
            run={
                **run_summary,
                "llm_provider": config.llm_provider,
                "llm_requested_model": config.llm_model,
                "dataset_version": "k2e-v1",
            },
            observation=observation,
            semantic_assertions=violations,
            result=result,
            failure_category=None if not violations else "assertion_failed",
            scenario_content_hash=S01_LOCKED_SCENARIO_HASH,
        )
        write_llm_report_atomic(run_id, report)

        if violations:
            failure_category = "assertion_failed"
            _write_failure(
                stage=failure_stage,
                category=failure_category,
                error="; ".join(violations),
                obs=observation,
            )

        terminal = httpx.post(
            f"{base}/admin/live-eval/runs/{run_id}/status",
            headers=headers,
            json={"tenant_id": tenant_id, "status": "completed" if not violations else "aborted"},
            timeout=30.0,
        )
        if terminal.status_code != 200:
            print(terminal.text, file=sys.stderr)

        print(json.dumps({"evaluation_run_id": run_id, "result": result, "violations": violations}, indent=2))
        return 0 if not violations else 1
    except Exception as exc:
        if failure_category is None:
            failure_category = "report_failure"
        _write_failure(stage=failure_stage, category=failure_category, error=exc, obs=observation)
        print(str(exc), file=sys.stderr)
        return 1


def cmd_run_scenario(args: argparse.Namespace) -> int:
    if not args.confirm_external:
        print("--confirm-external is required", file=sys.stderr)
        return 2
    config = get_live_eval_config()
    base = (args.app_base_url or os.environ.get("LIVE_EVAL_APP_BASE_URL") or "").rstrip("/")
    admin_key = os.environ.get("ADMIN_API_KEY", "").strip()
    tenant_id = args.tenant_id or next(iter(config.tenant_ids), "")
    if not base or not admin_key or not tenant_id:
        print("LIVE_EVAL_APP_BASE_URL, ADMIN_API_KEY, and tenant required", file=sys.stderr)
        return 2
    sender, recipient = _resolve_sender_recipient(config)

    evaluation_run_id = args.evaluation_run_id
    scenario_id = args.scenario_id
    attempt_id = args.attempt_id or 1
    if args.resume:
        if not evaluation_run_id:
            print("--run-id required for resume", file=sys.stderr)
            return 2
        from app.evaluation.live.journal import load_run_config

        run_config = load_run_config(evaluation_run_id)
        if not run_config:
            print("run_config.json missing for resume", file=sys.stderr)
            return 2
        scenario_id = run_config.get("scenario_id", scenario_id)
        attempt_id = int(run_config.get("attempt_id", attempt_id))
        if args.scenario_id and args.scenario_id != scenario_id:
            print("scenario_id override not allowed on resume", file=sys.stderr)
            return 2
        if args.attempt_id and args.attempt_id != attempt_id:
            print("attempt_id override not allowed on resume", file=sys.stderr)
            return 2

    runner = LiveEvalRunner(
        base_url=base,
        admin_api_key=admin_key,
        tenant_id=tenant_id,
        scenario_id=scenario_id,
        expected_sender=sender,
        expected_recipient=recipient,
        evaluation_run_id=evaluation_run_id,
        attempt_id=attempt_id,
        resume=args.resume,
        force_unlock=getattr(args, "force_unlock", False),
        run_id_file=getattr(args, "run_id_file", None),
    )
    return runner.run()


def cmd_show_report(args: argparse.Namespace) -> int:
    from app.evaluation.live.redaction import redact_sensitive

    path = run_directory(args.run_id) / "report.json"
    if not path.exists():
        print(f"report not found: {path}", file=sys.stderr)
        return 1
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"invalid report json: {exc}", file=sys.stderr)
        return 1
    redacted = redact_sensitive(payload)
    print(json.dumps(redacted, indent=2, ensure_ascii=False))
    return 0


def cmd_abort_run(args: argparse.Namespace) -> int:
    import httpx

    config = get_live_eval_config()
    base = (args.app_base_url or os.environ.get("LIVE_EVAL_APP_BASE_URL") or "").rstrip("/")
    admin_key = os.environ.get("ADMIN_API_KEY", "").strip()
    tenant_id = args.tenant_id or next(iter(config.tenant_ids), "")
    response = httpx.post(
        f"{base}/admin/live-eval/runs/{args.run_id}/status",
        headers={"X-Admin-API-Key": admin_key},
        json={"tenant_id": tenant_id, "status": "aborted"},
        timeout=30.0,
    )
    print(response.text)
    return 0 if response.status_code == 200 else 1


def cmd_cleanup_run(args: argparse.Namespace) -> int:
    if not args.confirm_external:
        return 2
    config = get_live_eval_config()
    base = (args.app_base_url or os.environ.get("LIVE_EVAL_APP_BASE_URL") or "").rstrip("/")
    admin_key = os.environ.get("ADMIN_API_KEY", "").strip()
    tenant_id = args.tenant_id or next(iter(config.tenant_ids), "")
    return cleanup_only(
        base_url=base,
        admin_api_key=admin_key,
        tenant_id=tenant_id,
        evaluation_run_id=args.run_id,
        recipient_gmail_message_id=args.recipient_message_id,
        phase=args.phase,
    )


def cmd_resume_run(args: argparse.Namespace) -> int:
    args.resume = True
    args.confirm_external = True
    return cmd_run_scenario(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live evaluation CLI (2F)")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-config")
    validate.add_argument("--offline", action="store_true", default=True)
    validate.add_argument("--gmail-readiness", action="store_true")
    validate.add_argument("--sender-readiness", action="store_true")
    validate.add_argument("--confirm-read-only", action="store_true")
    validate.add_argument("--tenant-id", default=None)
    validate.add_argument("--app-base-url", default=None)
    validate.set_defaults(func=cmd_validate_config)

    dry_run = sub.add_parser("dry-run")
    dry_run.add_argument("--evaluation-run-id", default=None)
    dry_run.add_argument("--scenario-id", default=None)
    dry_run.add_argument("--attempt-id", type=int, default=None)
    dry_run.set_defaults(func=cmd_dry_run)

    run = sub.add_parser("run-scenario")
    run.add_argument("--scenario-id", default="S01_lead_laddbox_quality")
    run.add_argument("--tenant-id", default=None)
    run.add_argument("--evaluation-run-id", default=None)
    run.add_argument("--attempt-id", type=int, default=None)
    run.add_argument("--app-base-url", default=None)
    run.add_argument("--confirm-external", action="store_true")
    run.add_argument("--resume", action="store_true", default=False)
    run.add_argument("--force-unlock", action="store_true", default=False)
    run.add_argument("--run-id-file", default=None)
    run.set_defaults(func=cmd_run_scenario)

    show = sub.add_parser("show-report")
    show.add_argument("--run-id", required=True)
    show.set_defaults(func=cmd_show_report)

    abort = sub.add_parser("abort-run")
    abort.add_argument("--run-id", required=True)
    abort.add_argument("--tenant-id", default=None)
    abort.add_argument("--app-base-url", default=None)
    abort.set_defaults(func=cmd_abort_run)

    cleanup = sub.add_parser("cleanup-run")
    cleanup.add_argument("--run-id", required=True)
    cleanup.add_argument("--tenant-id", default=None)
    cleanup.add_argument("--recipient-message-id", default=None)
    cleanup.add_argument("--phase", default="auto", choices=["auto", "pre_claim", "post_claim"])
    cleanup.add_argument("--app-base-url", default=None)
    cleanup.add_argument("--confirm-external", action="store_true")
    cleanup.set_defaults(func=cmd_cleanup_run)

    resume = sub.add_parser("resume-run")
    resume.add_argument("--run-id", required=True, dest="evaluation_run_id")
    resume.add_argument("--scenario-id", default="S01_lead_laddbox_quality")
    resume.add_argument("--tenant-id", default=None)
    resume.add_argument("--attempt-id", type=int, default=None)
    resume.add_argument("--app-base-url", default=None)
    resume.add_argument("--force-unlock", action="store_true")
    resume.set_defaults(func=cmd_resume_run)

    readiness = sub.add_parser("readiness-only")
    readiness.add_argument("--tenant-id", required=True)
    readiness.add_argument("--report-file", required=True)
    readiness.add_argument("--app-base-url", default=None)
    readiness.add_argument("--confirm-read-only", action="store_true")
    readiness.set_defaults(func=cmd_readiness_only)

    llm_readiness = sub.add_parser("llm-readiness-only")
    llm_readiness.add_argument("--tenant-id", default=None)
    llm_readiness.add_argument("--report-file", default=None)
    llm_readiness.set_defaults(func=cmd_llm_readiness_only)

    run_llm = sub.add_parser("run-llm-s01")
    run_llm.add_argument("--scenario-id", default="S01_lead_laddbox_quality")
    run_llm.add_argument("--tenant-id", default=None)
    run_llm.add_argument("--evaluation-run-id", default=None)
    run_llm.add_argument("--attempt-id", type=int, default=None)
    run_llm.add_argument("--app-base-url", default=None)
    run_llm.add_argument("--confirm-external", action="store_true")
    run_llm.add_argument("--run-id-file", default=None)
    run_llm.add_argument("--failure-artifact-file", default=None)
    run_llm.set_defaults(func=cmd_run_llm_s01)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
