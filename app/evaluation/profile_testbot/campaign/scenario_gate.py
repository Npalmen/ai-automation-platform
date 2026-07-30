"""Allowlist gates for profile testbot live Gmail scenarios."""

from __future__ import annotations

import os
import re

from app.core.canonical_commit import resolve_canonical_commit
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.campaign.readiness import require_live_semi_auto_runner_execution

_PROFILE_SEMI_AUTO_SCENARIO_RE = re.compile(r"^PTB-SEM-\d{4}$")


def is_profile_testbot_semi_auto_scenario(scenario_id: str) -> bool:
    return bool(_PROFILE_SEMI_AUTO_SCENARIO_RE.match((scenario_id or "").strip()))


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("yes", "true", "1")


def require_profile_testbot_live_execution_authorized() -> None:
    if not _env_truthy("LIVE_GMAIL_EVAL_ALLOWED"):
        raise LiveEvalSafetyError("LIVE_GMAIL_EVAL_ALLOWED=yes required for profile testbot live Gmail")
    if _env_truthy("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT"):
        raise LiveEvalSafetyError(
            "PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT must not be set for live Gmail execution"
        )
    runtime_sha = resolve_canonical_commit() or "unknown"
    blocked = require_live_semi_auto_runner_execution(runtime_sha=runtime_sha)
    if blocked:
        raise LiveEvalSafetyError(blocked)
