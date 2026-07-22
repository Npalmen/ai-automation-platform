"""Redacted read-only Gmail readiness report for operator verification."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.redaction import redact_sensitive

READINESS_REPORT_SCHEMA_VERSION = "2f.2.readiness"


def account_fingerprint(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:12]


def build_readiness_report(
    *,
    tenant_id: str,
    workflow_sha: str | None,
    environment_status: str,
    sender_profile_match: bool,
    recipient_profile_match: bool,
    recipient_label_found: bool,
    intake_query_valid: bool,
    result: str,
    failure_category: str | None = None,
    sender_fingerprint: str | None = None,
    recipient_fingerprint: str | None = None,
    issues: list[str] | None = None,
    config: LiveEvalConfig | None = None,
) -> dict[str, Any]:
    config = config or get_live_eval_config()
    return {
        "report_schema_version": READINESS_REPORT_SCHEMA_VERSION,
        "workflow_sha": workflow_sha,
        "tenant_id": tenant_id,
        "environment_status": environment_status,
        "sender_profile_match": sender_profile_match,
        "recipient_profile_match": recipient_profile_match,
        "recipient_label_found": recipient_label_found,
        "intake_query_valid": intake_query_valid,
        "sender_account_fingerprint": sender_fingerprint,
        "recipient_account_fingerprint": recipient_fingerprint,
        "external_sends": 0,
        "gmail_mutations": 0,
        "live_llm_calls": 0,
        "result": result,
        "failure_category": failure_category,
        "issues": issues or [],
        "intake_label": config.intake_label,
    }


def write_readiness_report_atomic(path: str | Path, payload: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    redacted = redact_sensitive(payload)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".readiness.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(redacted, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    os.chmod(target, 0o640)
    return target
