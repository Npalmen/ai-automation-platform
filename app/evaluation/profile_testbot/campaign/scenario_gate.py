"""Allowlist gates for profile testbot live Gmail scenarios."""

from __future__ import annotations

import os
import re
from functools import lru_cache

from app.core.canonical_commit import resolve_canonical_commit
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.campaign.readiness import require_live_semi_auto_runner_execution
from app.evaluation.profile_testbot.campaign.semi_auto_manifest import is_locked_ptb_sem_scenario_id
from app.evaluation.profile_testbot.constants import OPERATOR_STOP_LIVE_QUALITY_RUNNER

_PROFILE_SEMI_AUTO_SCENARIO_RE = re.compile(r"^PTB-SEM-\d{4}$")
_PROFILE_QUALITY_SCENARIO_RE = re.compile(r"^PTB-Q96-\d{4}$")


@lru_cache(maxsize=1)
def locked_profile_testbot_quality_scenario_ids() -> frozenset[str]:
    from app.evaluation.profile_testbot.qualification.live_campaign_manifest import (
        LIVE_QUALITY_CAMPAIGN_SCENARIO_IDS,
    )
    from app.evaluation.profile_testbot.qualification.live_canary_manifest import (
        LIVE_QUALITY_CANARY_SCENARIO_IDS,
    )

    return frozenset(LIVE_QUALITY_CANARY_SCENARIO_IDS) | frozenset(
        LIVE_QUALITY_CAMPAIGN_SCENARIO_IDS
    )


def is_profile_testbot_semi_auto_scenario(scenario_id: str) -> bool:
    normalized = (scenario_id or "").strip()
    if not _PROFILE_SEMI_AUTO_SCENARIO_RE.match(normalized):
        return False
    return is_locked_ptb_sem_scenario_id(normalized)


def is_profile_testbot_quality_scenario(scenario_id: str) -> bool:
    normalized = (scenario_id or "").strip()
    if not _PROFILE_QUALITY_SCENARIO_RE.match(normalized):
        return False
    return normalized in locked_profile_testbot_quality_scenario_ids()


def is_r3_frozen_live_canary_scenario(scenario_id: str) -> bool:
    from app.evaluation.profile_testbot.qualification.coworker_r3_registration_contract import (
        is_r3_frozen_live_canary_scenario as _is_r3,
    )

    return _is_r3(scenario_id)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("yes", "true", "1")


def require_live_quality_runner_execution(*, runtime_sha: str) -> str | None:
    approved_sha = os.environ.get(
        "PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED_SHA", ""
    ).strip()
    if _env_truthy("PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED"):
        if approved_sha and approved_sha == runtime_sha.strip():
            return None
        return OPERATOR_STOP_LIVE_QUALITY_RUNNER
    if _env_truthy("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED"):
        semi_sha = os.environ.get(
            "PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA", ""
        ).strip()
        if semi_sha and semi_sha == runtime_sha.strip():
            return None
    return OPERATOR_STOP_LIVE_QUALITY_RUNNER


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


def require_profile_testbot_quality_live_execution_authorized() -> None:
    if not _env_truthy("LIVE_GMAIL_EVAL_ALLOWED"):
        raise LiveEvalSafetyError("LIVE_GMAIL_EVAL_ALLOWED=yes required for profile testbot live Gmail")
    if _env_truthy("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT"):
        raise LiveEvalSafetyError(
            "PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT must not be set for live Gmail execution"
        )
    if not _env_truthy("PROFILE_TESTBOT_LIVE_QUALITY_APPROVED"):
        raise LiveEvalSafetyError(
            "PROFILE_TESTBOT_LIVE_QUALITY_APPROVED=yes required for live quality execution"
        )
    runtime_sha = resolve_canonical_commit() or "unknown"
    blocked = require_live_quality_runner_execution(runtime_sha=runtime_sha)
    if blocked:
        raise LiveEvalSafetyError(blocked)
