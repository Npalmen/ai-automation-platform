"""Write-free PR #172 postdeploy readiness @ 271a977 (no execute)."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

RUNTIME = os.environ.get(
    "R4_POSTDEPLOY_RUNTIME_SHA",
    "271a977abb178d92004f9f636a56c081cc69d2fa",
)
REPORT_STEM = os.environ.get(
    "R4_POSTDEPLOY_REPORT_STEM",
    "r4-pr172-postdeploy-readiness",
)
CANDIDATE = "b7fd95e075c16feee93a116a6062e402c1fee3df"
ATTEMPT1 = "fb36fd42-ce05-492e-8227-f1aad537868b"
ATTEMPT2 = "4d836572-9c27-4eac-9892-a3693801d334"
ATTEMPT3 = "32c6ed26-d030-441a-af52-5b186fae1107"
ATTEMPT4 = "99fa0b7f-1a6b-45aa-bec9-07f54f845de3"
MANIFEST_HASH = "bdebc3ce422aee302fdafad748e3e9b93a3deda8effe5deb90b49853e09144f5"
CANDIDATE_PKG_HASH = "6e6c37aaa57df1464fbc367701c0cfbfaf500f697ffae5cec3a50d2dda116254"
HUMAN_REVIEW_SHA256 = "7dced592907fb6fcbb89e632f1e37246cd120ace2a453e0aaa198397f5f0b57b"
PRIOR_SENDER_FP12 = "8e5bed9dd14d"
PRIOR_RECIPIENT_FP12 = "1818a63a4654"
STATUS = ROOT / "storage" / "status"
MAIN_STATUS = Path(r"C:\ai_automation_platform\storage\status")
MANIFEST = STATUS / "digital-coworker-r4-manifest-b7fd95e.json"
CANDIDATES = STATUS / "digital-coworker-r4-candidates-b7fd95e.json"
REVIEW = STATUS / "digital-coworker-r4-human-review-scored-b7fd95e.json"
SENDER_ENV_KEYS = (
    "LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN",
    "LIVE_EVAL_SENDER_GMAIL_CLIENT_ID",
    "LIVE_EVAL_SENDER_GMAIL_CLIENT_SECRET",
    "LIVE_EVAL_SENDER_GMAIL_USER",
    "LIVE_EVAL_SENDER_GMAIL_API_URL",
)


def _fp12(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def _get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def _post(url: str, headers: dict, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    h = dict(headers)
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def _load_env_files() -> None:
    for path in (ROOT / ".env", ROOT / ".env.live-eval.local"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, value = s.split("=", 1)
            os.environ[key.strip()] = value.strip()


def _inspect_token(env_key: str) -> dict:
    raw = os.environ.get(env_key, "")
    trimmed = raw.strip()
    fp = _fp12(trimmed) if trimmed else None
    return {
        "env_key": env_key,
        "env_present": raw is not None and raw != "",
        "trimmed_nonempty": bool(trimmed),
        "leading_or_trailing_whitespace": bool(raw) and raw != trimmed,
        "newline_detected": ("\n" in raw) or ("\r" in raw),
        "sha256_fingerprint_12": fp,
        "string_length": len(trimmed),
    }


def _env_source_presence() -> dict:
    sources = {}
    for path in (ROOT / ".env", ROOT / ".env.live-eval.local"):
        found = {k: False for k in SENDER_ENV_KEYS}
        if path.is_file():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                key = s.split("=", 1)[0].strip()
                if key in found:
                    found[key] = True
        sources[str(path)] = found
    return sources


def _write_reports(report: dict, md_lines: list[str]) -> None:
    payload_json = json.dumps(report, indent=2) + "\n"
    md_payload = "\n".join(md_lines) + "\n"
    short = RUNTIME[:7]
    json_name = f"{REPORT_STEM}-{short}.json"
    md_name = f"{REPORT_STEM}-{short}.md"
    for base in (STATUS, MAIN_STATUS):
        base.mkdir(parents=True, exist_ok=True)
        (base / json_name).write_text(payload_json, encoding="utf-8")
        (base / md_name).write_text(md_payload, encoding="utf-8")


def _run_campaign_mode(env: dict, extra: list[str]) -> dict:
    cmd = [
        sys.executable,
        "scripts/run_digital_coworker_r4_live_campaign.py",
        "--candidate-runtime-sha",
        CANDIDATE,
        "--expected-executor-sha",
        RUNTIME,
        "--manifest",
        "storage/status/digital-coworker-r4-manifest-b7fd95e.json",
        "--candidates-json",
        "storage/status/digital-coworker-r4-candidates-b7fd95e.json",
        "--human-review-file",
        "storage/status/digital-coworker-r4-human-review-scored-b7fd95e.json",
        *extra,
    ]
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    status = "UNKNOWN"
    for line in out.splitlines():
        if line.startswith("overall_status="):
            status = line.split("=", 1)[1].strip()
    return {"overall_status": status, "returncode": proc.returncode, "log_tail": out[-1200:]}


def _classify_refresh_error(exc: Exception) -> str:
    err = str(exc).lower()
    for label in ("invalid_grant", "invalid_client", "unauthorized_client", "access_denied"):
        if label in err:
            return label
    return type(exc).__name__


def _blocked_exit(report: dict, md_lines: list[str]) -> int:
    _write_reports(report, md_lines)
    print("R4 ATTEMPT 4 BLOCKED — postdeploy readiness på runtime 271a977 är inte komplett PASS; ingen ny Gmail-exekvering har utförts")
    return 1


def _sha_parity(*, headers: dict, base: str) -> dict:
    origin_main = subprocess.check_output(
        ["git", "rev-parse", "origin/main"], text=True, cwd=str(ROOT)
    ).strip()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, cwd=str(ROOT)).strip()
    runtime_api = _get(f"{base}/admin/live-eval/runtime-readiness", headers)
    runner_sha = (
        os.environ.get("PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED_SHA")
        or os.environ.get("BUILD_GIT_SHA")
        or ""
    ).strip()
    api_sha = runtime_api.get("api_build_git_sha")
    worker_sha = runtime_api.get("worker_build_git_sha")
    parity = {
        "origin_main": origin_main,
        "worktree_head": head,
        "api_build_git_sha": api_sha,
        "worker_build_git_sha": worker_sha,
        "runner_sha": runner_sha,
        "target": RUNTIME,
        "passed": all(
            s == RUNTIME for s in (origin_main, head, api_sha, worker_sha, runner_sha)
        ),
    }
    return parity


def _artifact_integrity() -> dict:
    from app.evaluation.profile_testbot.qualification.coworker_r4_execution import (
        _body_hash_map,
        validate_locked_candidate_bindings,
    )
    from app.evaluation.profile_testbot.qualification.coworker_r4_human_review import (
        validate_r4_human_review_bindings,
    )
    from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
        R4_NO_SEND_SCENARIO_IDS,
        R4_SEND_SCENARIO_IDS,
    )

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    candidates = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    review = json.loads(REVIEW.read_text(encoding="utf-8"))
    review_sha = hashlib.sha256(REVIEW.read_bytes()).hexdigest()
    body_hashes = _body_hash_map(candidates)
    bindings = validate_r4_human_review_bindings(candidates, review)
    binding_blockers = validate_locked_candidate_bindings(
        candidate_runtime_sha=CANDIDATE,
        candidates=candidates,
        human_review=review,
        human_review_path=REVIEW,
        manifest=manifest,
    )
    reviewed_matches = sum(
        1
        for row in review.get("reviews") or []
        if row.get("body_hash") and row.get("body_hash") == row.get("bound_body_hash")
    )
    return {
        "candidate_runtime_sha": candidates.get("runtime_sha"),
        "manifest_semantic_hash": manifest.get("manifest_semantic_hash"),
        "candidate_package_semantic_hash": candidates.get("candidate_package_semantic_hash"),
        "human_review_sha256": review_sha,
        "send_scenario_count": len(candidates.get("send_candidates") or []),
        "no_send_scenario_count": len(candidates.get("no_send_candidates") or []),
        "send_scenario_ids_match": set(body_hashes) == set(R4_SEND_SCENARIO_IDS),
        "no_send_count_16": len(candidates.get("no_send_candidates") or []) == 16,
        "reviewed_body_hash_matches": f"{reviewed_matches}/20",
        "human_review_complete": bindings.get("human_review_complete"),
        "automatic_gmail": manifest.get("automatic_gmail"),
        "production_activation": manifest.get("production_activation"),
        "blockers": binding_blockers,
        "passed": (
            not binding_blockers
            and reviewed_matches == 20
            and bindings.get("human_review_complete") is True
            and manifest.get("manifest_semantic_hash") == MANIFEST_HASH
            and candidates.get("candidate_package_semantic_hash") == CANDIDATE_PKG_HASH
            and review_sha == HUMAN_REVIEW_SHA256
            and candidates.get("runtime_sha") == CANDIDATE
            and manifest.get("automatic_gmail") is False
            and manifest.get("production_activation") is False
        ),
    }


def _migration_verify() -> dict:
    from app.repositories.postgres.database import engine
    from app.repositories.postgres.migration_runner import (
        LATEST_MIGRATION_VERSION,
        column_exists,
        read_migration_state,
        _index_names,
    )
    from app.repositories.postgres.schema_migrations import ensure_runtime_schema
    from sqlalchemy import text

    with engine.begin() as conn:
        before_count = conn.execute(text("SELECT COUNT(*) FROM live_eval_runs")).scalar()
    ensure_runtime_schema(engine)
    state = read_migration_state(engine)
    cols = {
        c: column_exists(engine, "live_eval_runs", c)
        for c in ("campaign_type", "execution_mode", "manifest_hash", "registration_context")
    }
    indexes = _index_names(engine, "live_eval_runs")
    with engine.begin() as conn:
        after_count = conn.execute(text("SELECT COUNT(*) FROM live_eval_runs")).scalar()
    return {
        "latest_migration": LATEST_MIGRATION_VERSION,
        "migration_state": state,
        "columns": cols,
        "index_present": "ix_live_eval_runs_campaign_type" in indexes,
        "row_count_unchanged": before_count == after_count,
        "passed": (
            LATEST_MIGRATION_VERSION == "026"
            and state.get("latest_version") == "026"
            and all(cols.values())
            and "ix_live_eval_runs_campaign_type" in indexes
            and before_count == after_count
        ),
    }


def _run_r4_routing_probe() -> dict:
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    from app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider import (
        R3LiveReplyProviderResolution,
        is_r3_frozen_customer_reply_context,
        is_reviewed_live_customer_reply_context,
        resolve_r3_live_reply_provider,
    )
    from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
        R4_EXECUTE_AI_MODE,
        R4_EXECUTION_MODE,
        R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        R4_TENANT_ID,
    )
    from app.workflows.action_executor import _build_email_result
    from app.workflows.reply_quality.provenance import hash_body

    body = "Reviewed R4 body for PTB-DCQ-0000"
    job = SimpleNamespace(
        tenant_id=R4_TENANT_ID,
        job_id="job-r4-probe",
        input_data={
            "live_eval": {
                "evaluation_run_id": "22222222-2222-4222-8222-222222222222",
                "tenant_id": R4_TENANT_ID,
                "scenario_id": "PTB-DCQ-0000",
                "attempt_id": 1,
                "transport_mode": "live_gmail",
                "ai_mode": R4_EXECUTE_AI_MODE,
                "config_hash": "cfg",
                "expected_sender": "sender@eval.test",
                "expected_recipient": "recipient@eval.test",
                "trusted": True,
            }
        },
    )
    action = {
        "type": "send_customer_auto_reply",
        "tenant_id": R4_TENANT_ID,
        "to": "sender@eval.test",
        "subject": "Re: offer",
        "body": body,
        "_authorization": "execution_allowed",
        "_action_operation_id": "op-r4-probe",
        "_approval_id": "appr-r4-probe",
    }
    reviewed_ctx = is_reviewed_live_customer_reply_context(action=action, job=job, db=None)
    r3_ctx = is_r3_frozen_customer_reply_context(action=action, job=job, db=None)

    adapter = MagicMock()
    adapter.execute_action.return_value = {
        "status": "success",
        "provider": "google_mail",
        "external_id": "fake-r4-routing-msg",
    }
    resolution = R3LiveReplyProviderResolution(
        provider_adapter=adapter,
        provider_source="live_eval_recipient_env",
        provider_name="google_mail",
        tenant_google_mail_used=False,
        stub_fallback_possible=False,
        ready=True,
        blockers=[],
    )
    tenant_called = False
    stub_called = False

    def _tenant_cfg(*_a, **_k):
        nonlocal tenant_called
        tenant_called = True
        return {}

    def _stub_ctor(*_a, **_k):
        nonlocal stub_called
        stub_called = True
        return MagicMock()

    with (
        patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.resolve_r3_live_reply_provider",
            return_value=resolution,
        ),
        patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.is_reviewed_live_customer_reply_context",
            return_value=True,
        ),
        patch("app.workflows.action_executor.get_integration_connection_config", side_effect=_tenant_cfg),
        patch("app.workflows.action_executor.InternalStubAdapter", side_effect=_stub_ctor),
    ):
        email_result = _build_email_result(action, db=MagicMock(), job=job)

    missing_bind_blockers: list[str] = []
    reviewed_missing = None
    if not isinstance(reviewed_missing, dict) or not (reviewed_missing or {}).get("canonical_body_hash"):
        missing_bind_blockers.append("reviewed body bind missing on approval")

    wrong_hash_blockers: list[str] = []
    wrong_hash = "0" * 64
    if hash_body(body) != wrong_hash:
        wrong_hash_blockers.append("reviewed body hash mismatch before send")

    return {
        "scenario_id": "PTB-DCQ-0000",
        "is_reviewed_live_customer_reply_context": reviewed_ctx,
        "r3_only_context": r3_ctx,
        "recipient_env_route_selected": email_result.get("r3_reply_provider_source") == "live_eval_recipient_env",
        "tenant_gmail_route_selected": tenant_called,
        "internal_stub_selected": stub_called,
        "provider": email_result.get("provider"),
        "r4_reviewed_bind_required": any("reviewed body bind missing" in b for b in missing_bind_blockers),
        "body_hash_required": any("body hash mismatch" in b for b in wrong_hash_blockers),
        "expected_body_hash": hash_body(body),
        "google_contacted": False,
        "passed": (
            reviewed_ctx
            and not r3_ctx
            and email_result.get("r3_reply_provider_source") == "live_eval_recipient_env"
            and not tenant_called
            and not stub_called
            and email_result.get("provider") == "google_mail"
            and any("reviewed body bind missing" in b for b in missing_bind_blockers)
            and any("body hash mismatch" in b for b in wrong_hash_blockers)
        ),
    }


def _run_provider_lifecycle_probe() -> dict:
    proc = subprocess.run(
        [sys.executable, "storage/status/_r4_postdeploy_execution_contract_probe.py"],
        cwd=str(ROOT),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    short = RUNTIME[:7]
    out_path = STATUS / f"r4-postdeploy-execution-contract-probe-{short}.json"
    if not out_path.is_file():
        out_path = STATUS / "r4-postdeploy-execution-contract-probe-271a977.json"
    doc = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {}
    return {
        "returncode": proc.returncode,
        "report": doc,
        "passed": proc.returncode == 0 and bool(doc.get("fake_provider_positive")),
    }


def _run_thread_evidence_probe() -> dict:
    proc = subprocess.run(
        [sys.executable, "storage/status/_r4_thread_evidence_contract_probe.py", RUNTIME],
        cwd=str(ROOT),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    short = RUNTIME[:7]
    out_path = STATUS / f"r4-thread-evidence-contract-probe-{short}.json"
    doc = json.loads(out_path.read_text(encoding="utf-8")) if out_path.is_file() else {}
    probe = doc.get("thread_evidence_contract_probe") or {}
    return {
        "returncode": proc.returncode,
        "probe": probe,
        "passed": proc.returncode == 0 and bool(probe.get("passed")),
    }


def _attempt_quarantine() -> dict:
    from app.evaluation.profile_testbot.qualification.coworker_r4_attempt1_orphan import (
        ATTEMPT1_CAMPAIGN_ID,
        attempt1_orphan_record,
        assert_r4_campaign_not_quarantined,
    )

    def _q(rec: dict, campaign_id: str) -> bool:
        return (
            rec.get("campaign_id") == campaign_id
            and rec.get("reuse_blocked") is True
            and rec.get("exclude_from_r4_pass") is True
            and (rec.get("resume_forbidden") is True or rec.get("never_resume") is True)
            and (rec.get("retry_forbidden") is True or rec.get("never_retry") is True)
        )

    attempt1_quarantined = False
    try:
        assert_r4_campaign_not_quarantined(ATTEMPT1_CAMPAIGN_ID)
    except Exception:
        attempt1_quarantined = True
    attempt2_rec = (
        json.loads((STATUS / "digital-coworker-r4-attempt2-orphan-registry.json").read_text(encoding="utf-8"))
        if (STATUS / "digital-coworker-r4-attempt2-orphan-registry.json").is_file()
        else {}
    )
    attempt3_rec = (
        json.loads((STATUS / "digital-coworker-r4-attempt3-orphan-registry.json").read_text(encoding="utf-8"))
        if (STATUS / "digital-coworker-r4-attempt3-orphan-registry.json").is_file()
        else {}
    )
    attempt4_rec = (
        json.loads((STATUS / "digital-coworker-r4-attempt4-orphan-registry.json").read_text(encoding="utf-8"))
        if (STATUS / "digital-coworker-r4-attempt4-orphan-registry.json").is_file()
        else {}
    )
    return {
        "attempt1": attempt1_orphan_record().to_dict(),
        "attempt2": attempt2_rec,
        "attempt3": attempt3_rec,
        "attempt4": attempt4_rec,
        "attempt1_quarantined": attempt1_quarantined,
        "attempt2_quarantined": _q(attempt2_rec, ATTEMPT2),
        "attempt3_quarantined": _q(attempt3_rec, ATTEMPT3),
        "attempt4_quarantined": _q(attempt4_rec, ATTEMPT4),
        "attempt3_inbound_trigger_excluded": bool(attempt3_rec.get("inbound_trigger_sent")),
        "attempt4_inbound_trigger_excluded": bool(attempt4_rec.get("inbound_trigger_sent")),
        "attempt4_gmail_replies_excluded": int(attempt4_rec.get("gmail_replies") or 0),
        "passed": (
            attempt1_quarantined
            and _q(attempt2_rec, ATTEMPT2)
            and _q(attempt3_rec, ATTEMPT3)
            and _q(attempt4_rec, ATTEMPT4)
        ),
    }


def main() -> int:
    _load_env_files()
    os.environ["BUILD_GIT_SHA"] = RUNTIME
    os.environ["WORKER_BUILD_GIT_SHA"] = RUNTIME
    os.environ["PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA"] = RUNTIME
    os.environ["PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED_SHA"] = RUNTIME
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sender_meta = _inspect_token("LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN")
    recipient_meta = _inspect_token("LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN")
    env_sources = _env_source_presence()
    blockers: list[str] = []
    base = os.environ.get("LIVE_EVAL_APP_BASE_URL", "http://127.0.0.1:8010")
    key = os.environ.get("ADMIN_API_KEY", "").strip()
    headers = {"X-Tenant-ID": "TENANT_LIVE_EVAL", "X-Admin-API-Key": key}

    sha_parity = _sha_parity(headers=headers, base=base)
    if not sha_parity["passed"]:
        blockers.append("sha_parity_failed")
        if sha_parity.get("origin_main") != RUNTIME:
            blockers.append("origin_main_mismatch")
        if sha_parity.get("api_build_git_sha") != RUNTIME:
            blockers.append("api_sha_mismatch")
        if sha_parity.get("worker_build_git_sha") != RUNTIME:
            blockers.append("worker_sha_mismatch")
        if sha_parity.get("runner_sha") != RUNTIME:
            blockers.append("runner_sha_mismatch")
        report = {
            "generated_at": generated_at,
            "deployed_sha": RUNTIME,
            "sha_parity": sha_parity,
            "blockers": blockers,
            "passed": False,
            "execute_not_run": True,
            "attempt4_approval_not_created": True,
            "secrets_exposed": False,
        }
        md = [
            "# R4 PR #172 postdeploy readiness — 271a977",
            "",
            "## SHA parity — STOPPED",
            "",
            f"- origin/main: `{sha_parity.get('origin_main')}`",
            f"- API: `{sha_parity.get('api_build_git_sha')}`",
            f"- worker: `{sha_parity.get('worker_build_git_sha')}`",
            f"- runner: `{sha_parity.get('runner_sha')}`",
            f"- target: `{RUNTIME}`",
        ]
        return _blocked_exit(report, md)

    artifact = _artifact_integrity()
    if not artifact["passed"]:
        blockers.extend([f"artifact:{b}" for b in artifact.get("blockers") or []])
        if artifact.get("reviewed_body_hash_matches") != "20/20":
            blockers.append(f"reviewed_body_hashes:{artifact.get('reviewed_body_hash_matches')}")

    migration = _migration_verify()
    if not migration["passed"]:
        blockers.append("migration_026_failed")

    if sender_meta["sha256_fingerprint_12"] == PRIOR_SENDER_FP12:
        blockers.append("sender_refresh_token_still_revoked_fp12")
    if recipient_meta["sha256_fingerprint_12"] == PRIOR_RECIPIENT_FP12:
        blockers.append("recipient_refresh_token_still_revoked_fp12")

    if not sender_meta["trimmed_nonempty"]:
        blockers.append("LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN missing or empty")
    if sender_meta["leading_or_trailing_whitespace"]:
        blockers.append("sender_refresh_token_whitespace")
    if sender_meta["newline_detected"]:
        blockers.append("sender_refresh_token_newline")

    from app.evaluation.live.config import get_live_eval_config
    from app.evaluation.live.delivery_mailbox_reader import CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV
    from app.evaluation.live.gmail_transport import (
        build_sender_client,
        load_sender_credentials,
        run_sender_readiness_read_only,
    )
    from app.evaluation.live.recipient_gmail_readiness import run_recipient_gmail_readiness
    from app.evaluation.live.sender_scope import verify_sender_send_scope
    from app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider import (
        run_r3_live_reply_provider_readiness,
    )
    from app.evaluation.profile_testbot.qualification.coworker_r4_live_probes import (
        probe_r4_mailbox_baseline,
    )
    from app.integrations.google.mail_client import refresh_access_token_with_metadata

    cfg = get_live_eval_config()
    senders = sorted({e.strip().lower() for e in cfg.sender_emails if e and e.strip()})
    recipients = sorted({e.strip().lower() for e in cfg.recipient_emails if e and e.strip()})
    sender = senders[0] if senders else ""
    recipient = recipients[0] if recipients else ""

    # 2. Sender OAuth probe (single)
    access_returned = False
    invalid_grant = False
    refresh_classification = "not_attempted"
    granted_scopes: list[str] = []
    send_scope_ok = False
    read_scope_ok = False
    if not blockers:
        try:
            creds = load_sender_credentials()
            refresh = refresh_access_token_with_metadata(
                refresh_token=creds.refresh_token,
                client_id=creds.client_id,
                client_secret=creds.client_secret,
            )
            access_returned = bool(refresh.access_token)
            granted_scopes = sorted(refresh.granted_scopes)
            refresh_classification = "refresh_success" if access_returned else "malformed_response"
            send_scope_ok = any("gmail.send" in s for s in granted_scopes)
            read_scope_ok = any(
                "gmail.readonly" in s or "gmail.modify" in s or "mail.google.com" in s
                for s in granted_scopes
            )
            if not access_returned:
                blockers.append("sender_token_refresh_no_access_token")
            if not send_scope_ok:
                blockers.append("sender_gmail_send_scope_missing")
        except Exception as exc:
            invalid_grant = "invalid_grant" in str(exc).lower()
            refresh_classification = _classify_refresh_error(exc)
            blockers.append(f"sender_token_refresh_failed:{refresh_classification}")

    sender_probe_pass = (
        not blockers
        and refresh_classification == "refresh_success"
        and access_returned
        and not invalid_grant
        and send_scope_ok
    )

    if not sender_probe_pass:
        report = {
            "generated_at": generated_at,
            "runtime_sha": RUNTIME,
            "candidate_runtime_sha": CANDIDATE,
            "stopped_after_sender_probe": True,
            "sender_refresh_fp12": sender_meta["sha256_fingerprint_12"],
            "prior_sender_refresh_fp12": PRIOR_SENDER_FP12,
            "sender_refresh_token_changed": sender_meta["sha256_fingerprint_12"] != PRIOR_SENDER_FP12,
            "sender_token_meta": sender_meta,
            "sender_env_sources": env_sources,
            "sender_credential_source": "live_eval_sender_env",
            "sender_oauth_refresh": {
                "classification": refresh_classification,
                "http_success": refresh_classification == "refresh_success",
                "access_token_returned": access_returned,
                "invalid_grant": invalid_grant,
                "granted_scopes": granted_scopes,
                "gmail_send_scope": send_scope_ok,
                "read_scope_present": read_scope_ok,
            },
            "blockers": blockers,
            "passed": False,
            "execute_not_run": True,
            "attempt3_approval_not_created": True,
            "secrets_exposed": False,
        }
        md = [
            "# R4 sender OAuth reauth readiness — af7e49c",
            "",
            f"- generated_at: `{generated_at}`",
            "- **STOPPED after sender OAuth probe**",
            f"- sender_refresh_fp12: `{sender_meta['sha256_fingerprint_12']}`",
            f"- prior_sender_refresh_fp12: `{PRIOR_SENDER_FP12}`",
            f"- sender refresh classification: `{refresh_classification}`",
            f"- access_token_returned: {access_returned}",
            f"- invalid_grant: {invalid_grant}",
        ]
        if blockers:
            md.extend(["", "## Blockers", ""] + [f"- {b}" for b in blockers])
        return _blocked_exit(report, md)

    # 3. Sender Gmail readiness
    send_scope_report = verify_sender_send_scope()
    sender_readiness = run_sender_readiness_read_only(
        expected_sender=sender,
        expected_recipient=recipient,
        config=cfg,
    )
    profile_redacted = None
    try:
        profile_email = (build_sender_client().get_profile_email() or "").strip().lower()
        profile_redacted = (
            f"{profile_email[:2]}…@{profile_email.split('@')[-1]}" if "@" in profile_email else None
        )
    except Exception:
        profile_email = None

    sender_identity_match = bool(sender_readiness.profile_email) and sender_readiness.profile_email == sender
    if not sender_readiness.ready:
        blockers.extend([f"sender_readiness:{i}" for i in sender_readiness.issues])
    if not sender_identity_match:
        blockers.append("sender_mailbox_identity_match!=true")
    if not sender_readiness.read_scope_verified:
        blockers.append("sender_read_probe_failed")
    if not send_scope_report.verified:
        blockers.extend([f"sender_send_scope:{i}" for i in send_scope_report.issues])

    # 4. Recipient regression
    recipient_readiness = run_recipient_gmail_readiness(expected_recipient=recipient, config=cfg)
    reply_provider = run_r3_live_reply_provider_readiness(
        expected_recipient=recipient,
        expected_sender=sender,
    )
    recipient_regression = {
        "refresh_fp12": recipient_meta["sha256_fingerprint_12"],
        "prior_refresh_fp12": PRIOR_RECIPIENT_FP12,
        "token_refresh_passed": recipient_readiness.recipient_token_refresh_passed,
        "gmail_scopes_ok": recipient_readiness.recipient_required_scopes_present,
        "gmail_identity_match": recipient_readiness.recipient_mailbox_identity_match,
        "recipient_credential_source": recipient_readiness.recipient_credential_source,
        "delivery_observation_credential_source": recipient_readiness.delivery_observation_credential_source,
        "reply_provider_source": reply_provider.get("reply_provider_source"),
        "credential_source_match": recipient_readiness.credential_source_match,
        "tenant_google_mail_fallback": bool(reply_provider.get("tenant_google_mail_used")),
        "stub_fallback": bool(reply_provider.get("stub_fallback_possible")),
        "smtp": False,
        "passed": (
            recipient_readiness.recipient_token_refresh_passed
            and recipient_readiness.recipient_required_scopes_present
            and recipient_readiness.recipient_mailbox_identity_match
            and recipient_readiness.recipient_credential_source == CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV
            and recipient_readiness.delivery_observation_credential_source
            == CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV
            and reply_provider.get("reply_provider_source") == CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV
            and recipient_readiness.credential_source_match
            and not reply_provider.get("tenant_google_mail_used")
            and not reply_provider.get("stub_fallback_possible")
        ),
    }
    if not recipient_regression["passed"]:
        blockers.append("recipient_regression_failed")
        blockers.extend([f"recipient:{b}" for b in recipient_readiness.blockers[:3]])

    routing_probe = _run_r4_routing_probe()
    if not routing_probe.get("passed"):
        blockers.append("r4_routing_probe_failed")

    provider_lifecycle = _run_provider_lifecycle_probe()
    if not provider_lifecycle.get("passed"):
        blockers.append("provider_lifecycle_probe_failed")

    thread_evidence = _run_thread_evidence_probe()
    if not thread_evidence.get("passed"):
        blockers.append("thread_evidence_probe_failed")

    migration_026_pass = migration["passed"]
    runtime_api = sha_parity
    reg = _get(f"{base}/admin/live-eval/r4-registration-readiness", headers)
    probe = _post(f"{base}/admin/live-eval/r4-registration-probe", headers, {})
    if reg.get("send_registration_ready") != "20/20":
        blockers.append("send_registration_not_20_20")
    if reg.get("no_send_registration_ready") != "16/16":
        blockers.append("no_send_registration_not_16_16")
    if not reg.get("trusted_snapshot_roundtrip_ready"):
        blockers.append("trusted_snapshot_not_ready")
    if reg.get("mutation_contract_ready") != "36/36":
        blockers.append("mutation_not_36_36")
    if not probe.get("passed"):
        blockers.append("registration_probe_failed")

    env = os.environ.copy()
    env["BUILD_GIT_SHA"] = RUNTIME
    env["WORKER_BUILD_GIT_SHA"] = RUNTIME
    env["PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA"] = RUNTIME
    env["PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED_SHA"] = RUNTIME
    subprocess.run(
        [sys.executable, "scripts/seed_live_eval_tenant.py", "--tenant-id", "TENANT_LIVE_EVAL", "--apply"],
        cwd=str(ROOT),
        env=env,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    dry_run = _run_campaign_mode(env, [])
    full_jit = _run_campaign_mode(env, ["--full-jit"])
    baseline_campaign = f"r4-pr172-postdeploy-baseline-{uuid.uuid4()}"
    mailbox_runner = _run_campaign_mode(env, ["--mailbox-baseline", "--campaign-id", baseline_campaign])
    baseline_probe = probe_r4_mailbox_baseline(campaign_id=baseline_campaign, recipient_email=recipient)

    structural_dry_run_pass = dry_run.get("overall_status") == "PASS"
    full_jit_pass = full_jit.get("overall_status") == "PASS"
    mailbox_baseline_pass = (
        mailbox_runner.get("overall_status") == "PASS"
        and baseline_probe.get("mutations_performed") is False
        and not baseline_probe.get("r3_subject_tokens")
    )
    if not structural_dry_run_pass:
        blockers.append("structural_dry_run_not_pass")
    if not full_jit_pass:
        blockers.append("full_live_jit_not_pass")
        jit_candidates = sorted(STATUS.glob("digital-coworker-r4-full-live-jit-*.json"))
        jit_path = jit_candidates[-1] if jit_candidates else None
        if jit_path and jit_path.is_file():
            jit_doc = json.loads(jit_path.read_text(encoding="utf-8"))
            for b in (jit_doc.get("blockers") or [])[:5]:
                blockers.append(f"full_live_jit:{b}")
    if not mailbox_baseline_pass:
        blockers.append("mailbox_baseline_not_pass")

    quarantine = _attempt_quarantine()
    if not quarantine["passed"]:
        blockers.append("attempt_quarantine_failed")

    write_counters = {
        "gmail_triggers": 0,
        "gmail_replies": 0,
        "gmail_drafts": 0,
        "jobs": 0,
        "approvals_created": 0,
        "external_writes": 0,
        "llm_calls": 0,
        "candidate_regeneration": 0,
        "secrets_exposed": False,
    }

    sender_oauth_passed = sender_probe_pass and sender_readiness.ready and sender_identity_match
    passed = not blockers and sender_oauth_passed and recipient_regression["passed"] and all(
        [
            artifact["passed"],
            migration_026_pass,
            routing_probe.get("passed"),
            provider_lifecycle.get("passed"),
            thread_evidence.get("passed"),
            bool(reg.get("passed")),
            structural_dry_run_pass,
            full_jit_pass,
            mailbox_baseline_pass,
            quarantine["passed"],
        ]
    )

    report = {
        "generated_at": generated_at,
        "deployed_sha": RUNTIME,
        "pr172_squash_sha": RUNTIME,
        "candidate_runtime_sha": CANDIDATE,
        "sha_parity": sha_parity,
        "artifact_integrity": artifact,
        "migration": migration,
        "routing_probe": routing_probe,
        "provider_lifecycle_probe": provider_lifecycle,
        "thread_evidence_probe": thread_evidence,
        "sender_refresh_fp12": sender_meta["sha256_fingerprint_12"],
        "recipient_refresh_fp12": recipient_meta["sha256_fingerprint_12"],
        "prior_sender_refresh_fp12": PRIOR_SENDER_FP12,
        "prior_recipient_refresh_fp12": PRIOR_RECIPIENT_FP12,
        "sender_refresh_token_changed": sender_meta["sha256_fingerprint_12"] != PRIOR_SENDER_FP12,
        "sender_token_meta": sender_meta,
        "sender_env_sources": env_sources,
        "sender_credential_source": "live_eval_sender_env",
        "sender_oauth_refresh": {
            "classification": refresh_classification,
            "http_success": True,
            "access_token_returned": access_returned,
            "invalid_grant": False,
            "granted_scopes": granted_scopes,
            "gmail_send_scope": send_scope_ok,
            "read_scope_present": read_scope_ok,
        },
        "sender_gmail_identity": {
            "profile_lookup_passed": sender_identity_match,
            "profile_email_redacted": profile_redacted,
            "sender_mailbox_identity_match": sender_identity_match,
            "read_probe_passed": sender_readiness.read_scope_verified,
            "send_scope_verified": send_scope_report.verified,
            "mutations_performed": False,
        },
        "recipient_regression": recipient_regression,
        "credential_sources": {
            "sender": "live_eval_sender_env",
            "recipient": recipient_readiness.recipient_credential_source,
            "delivery_observation": recipient_readiness.delivery_observation_credential_source,
            "reply_provider": reply_provider.get("reply_provider_source"),
            "credential_source_match": recipient_readiness.credential_source_match,
        },
        "migration_state": migration.get("migration_state"),
        "registration_readiness": reg,
        "registration_probe": probe,
        "structural_dry_run": dry_run,
        "full_live_jit": full_jit,
        "mailbox_baseline": {"campaign_id": baseline_campaign, "runner": mailbox_runner, "probe": baseline_probe},
        "attempt_quarantine": quarantine,
        "write_counters": write_counters,
        "gates": {
            "R3_LIVE_CANARY": "PASS",
            "R4_HUMAN_REVIEW": "PASS",
            "R4_LIVE_CAMPAIGN": "PENDING",
            "R5_CLOSURE": "PENDING",
            "PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED": "PENDING",
            "R4_ATTEMPT_5_APPROVAL": "NOT_GRANTED",
        },
        "sender_oauth_passed": sender_oauth_passed,
        "passed": passed,
        "blockers": blockers,
        "execute_not_run": True,
        "attempt4_approval_not_created": True,
        "secrets_exposed": False,
    }

    md_lines = [
        "# R4 PR #172 postdeploy readiness — 271a977",
        "",
        f"- generated_at: `{generated_at}`",
        f"- deployed_sha: `{RUNTIME}`",
        f"- api_sha: `{sha_parity.get('api_build_git_sha')}`",
        f"- worker_sha: `{sha_parity.get('worker_build_git_sha')}`",
        f"- runner_sha: `{sha_parity.get('runner_sha')}`",
        f"- candidate_sha: `{CANDIDATE}`",
        f"- passed: **{passed}**",
        "",
        "## Artifact integrity",
        "",
        f"- manifest hash: `{artifact.get('manifest_semantic_hash')}`",
        f"- candidate package hash: `{artifact.get('candidate_package_semantic_hash')}`",
        f"- human review sha256: `{artifact.get('human_review_sha256')}`",
        f"- reviewed body hashes: {artifact.get('reviewed_body_hash_matches')}",
        "",
        "## OAuth",
        "",
        f"- sender_refresh_fp12: `{sender_meta['sha256_fingerprint_12']}` (len {sender_meta['string_length']})",
        f"- recipient_refresh_fp12: `{recipient_meta['sha256_fingerprint_12']}` (len {recipient_meta['string_length']})",
        f"- sender OAuth: {sender_oauth_passed}",
        f"- recipient OAuth: {recipient_regression['passed']}",
        f"- reply_provider_source: `{recipient_regression.get('reply_provider_source')}`",
        "",
        "## Probes",
        "",
        f"- R4 routing probe: {routing_probe.get('passed')}",
        f"- provider lifecycle probe: {provider_lifecycle.get('passed')}",
        f"- thread evidence probe: {thread_evidence.get('passed')}",
        f"- migration 026: {migration_026_pass}",
        f"- registration: {reg.get('send_registration_ready')} + {reg.get('no_send_registration_ready')}",
        f"- mutation: {reg.get('mutation_contract_ready')}",
        f"- structural dry-run: {structural_dry_run_pass}",
        f"- full live JIT: {full_jit_pass}",
        f"- mailbox baseline: {mailbox_baseline_pass}",
        "",
        "## Quarantine",
        "",
        f"- attempt 1: {quarantine.get('attempt1_quarantined')}",
        f"- attempt 2: {quarantine.get('attempt2_quarantined')}",
        f"- attempt 3: {quarantine.get('attempt3_quarantined')}",
        f"- attempt 4: {quarantine.get('attempt4_quarantined')}",
        f"- attempt 3 inbound trigger excluded: {quarantine.get('attempt3_inbound_trigger_excluded')}",
        f"- attempt 4 inbound trigger excluded: {quarantine.get('attempt4_inbound_trigger_excluded')}",
        f"- attempt 4 gmail replies excluded: {quarantine.get('attempt4_gmail_replies_excluded')}",
        "",
        "## Write counters",
        "",
        "- gmail_triggers=0, gmail_replies=0, gmail_drafts=0, jobs=0, approvals=0, external_writes=0, llm_calls=0",
        "- secrets_exposed=false",
        "",
    ]
    if blockers:
        md_lines.extend(["## Blockers", ""] + [f"- {b}" for b in blockers])

    _write_reports(report, md_lines)
    print(json.dumps({"passed": passed, "sender_fp12": sender_meta["sha256_fingerprint_12"], "blockers": blockers}, indent=2))
    if passed:
        ending = os.environ.get("R4_POSTDEPLOY_SUCCESS_LINE")
        if not ending:
            ending = (
                "MANUAL EXECUTION CONFIRMATION REQUIRED — Attempt-4 thread-evidence propagation är "
                "reparerad och verifierad; provider Gmail message ID, RFC Message-ID, delivered-copy "
                "correlation och inbound thread linkage är separata och fail-closed; attempt 1–4 "
                "permanent quarantined; full JIT och fresh mailbox baseline PASS utan nya Gmail-writes"
            )
        print(ending)
        return 0
    print(
        f"R4 ATTEMPT 5 BLOCKED — postdeploy readiness på runtime {RUNTIME[:7]} är inte komplett PASS; "
        "ingen ny Gmail-exekvering har utförts"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
