"""Fail-closed remote eval-stack runtime SHA verification for profile testbot readiness."""

from __future__ import annotations

from typing import Any

import httpx

from app.evaluation.live.pipeline_runtime import FULL_GIT_SHA_LENGTH, require_full_git_sha

_RUNTIME_MISMATCH_PREFIX = "EVAL_STACK_RUNTIME_SHA_MISMATCH"


def fetch_eval_stack_runtime_readiness(
    *,
    base_url: str,
    admin_api_key: str,
    timeout: float = 15.0,
) -> tuple[dict[str, Any] | None, str | None]:
    if not base_url.strip():
        return None, "EVAL_STACK_RUNTIME_READINESS_UNAVAILABLE: LIVE_EVAL_APP_BASE_URL missing"
    if not admin_api_key.strip():
        return None, "EVAL_STACK_RUNTIME_READINESS_UNAVAILABLE: ADMIN_API_KEY missing"
    url = f"{base_url.rstrip('/')}/admin/live-eval/runtime-readiness"
    try:
        response = httpx.get(
            url,
            headers={"X-Admin-API-Key": admin_api_key},
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        return None, f"EVAL_STACK_RUNTIME_READINESS_UNAVAILABLE: {exc.__class__.__name__}"
    if response.status_code in (401, 403):
        return None, f"EVAL_STACK_RUNTIME_READINESS_AUTH_FAILED: http_{response.status_code}"
    if response.status_code >= 400:
        return None, f"EVAL_STACK_RUNTIME_READINESS_HTTP_{response.status_code}"
    try:
        payload = response.json()
    except ValueError:
        return None, "EVAL_STACK_RUNTIME_READINESS_INVALID_JSON"
    if not isinstance(payload, dict):
        return None, "EVAL_STACK_RUNTIME_READINESS_INVALID_PAYLOAD"
    return payload, None


def _mismatch_blocker(*, approved: str | None, api: str | None, worker: str | None) -> str:
    return (
        f"{_RUNTIME_MISMATCH_PREFIX}: "
        f"approved={approved or 'missing'}, api={api or 'missing'}, worker={worker or 'missing'}"
    )


def evaluate_eval_stack_runtime_sha(
    *,
    base_url: str,
    admin_api_key: str,
    approved_runtime_sha: str | None,
    runner_runtime_sha: str | None,
    require_remote: bool,
) -> dict[str, Any]:
    approved = require_full_git_sha(approved_runtime_sha)
    runner = require_full_git_sha(runner_runtime_sha)
    blocking_failures: list[str] = []
    live_blockers: list[str] = []
    endpoint_verified = False
    api_sha: str | None = None
    worker_sha: str | None = None
    runtime_consistent = False

    if not require_remote:
        return {
            "approved_runtime_sha": approved,
            "runner_runtime_sha": runner,
            "api_runtime_sha": None,
            "worker_runtime_sha": None,
            "runtime_sha_consistent": None,
            "runtime_readiness_endpoint_verified": False,
            "blocking_failures": [],
            "live_execution_blockers": [],
            "authoritative_runtime_sha": None,
        }

    remote, fetch_error = fetch_eval_stack_runtime_readiness(
        base_url=base_url,
        admin_api_key=admin_api_key,
    )
    if fetch_error:
        blocking_failures.append(fetch_error)
        live_blockers.append(fetch_error)
        return {
            "approved_runtime_sha": approved,
            "runner_runtime_sha": runner,
            "api_runtime_sha": None,
            "worker_runtime_sha": None,
            "runtime_sha_consistent": False,
            "runtime_readiness_endpoint_verified": False,
            "blocking_failures": blocking_failures,
            "live_execution_blockers": live_blockers,
            "authoritative_runtime_sha": None,
        }

    endpoint_verified = True
    raw_api = remote.get("build_git_sha") or remote.get("api_build_git_sha")
    raw_worker = remote.get("worker_build_git_sha")
    api_sha = require_full_git_sha(str(raw_api) if raw_api else None)
    worker_sha = require_full_git_sha(str(raw_worker) if raw_worker else None)

    if not api_sha:
        msg = "EVAL_STACK_RUNTIME_SHA_MISSING: api build_git_sha missing or invalid"
        blocking_failures.append(msg)
        live_blockers.append(msg)
    if not worker_sha:
        msg = "EVAL_STACK_RUNTIME_SHA_MISSING: worker build_git_sha missing or invalid"
        blocking_failures.append(msg)
        live_blockers.append(msg)
    if raw_api and len(str(raw_api).strip()) not in (0, FULL_GIT_SHA_LENGTH):
        blocking_failures.append("EVAL_STACK_RUNTIME_SHA_INVALID: api build_git_sha is shortened")
    if raw_worker and len(str(raw_worker).strip()) not in (0, FULL_GIT_SHA_LENGTH):
        blocking_failures.append("EVAL_STACK_RUNTIME_SHA_INVALID: worker build_git_sha is shortened")

    if approved_runtime_sha and not approved:
        msg = "EVAL_STACK_RUNTIME_SHA_INVALID: operator-approved SHA missing or invalid"
        blocking_failures.append(msg)
        live_blockers.append(msg)
    if runner_runtime_sha and not runner:
        msg = "EVAL_STACK_RUNTIME_SHA_INVALID: runner runtime SHA missing or invalid"
        blocking_failures.append(msg)
        live_blockers.append(msg)

    if api_sha and worker_sha and api_sha != worker_sha:
        mismatch = _mismatch_blocker(approved=approved, api=api_sha, worker=worker_sha)
        blocking_failures.append(mismatch)
        live_blockers.append(mismatch)

    if approved and api_sha and approved != api_sha:
        mismatch = _mismatch_blocker(approved=approved, api=api_sha, worker=worker_sha)
        blocking_failures.append(mismatch)
        live_blockers.append(mismatch)
    if approved and worker_sha and approved != worker_sha:
        mismatch = _mismatch_blocker(approved=approved, api=api_sha, worker=worker_sha)
        blocking_failures.append(mismatch)
        live_blockers.append(mismatch)
    if runner and api_sha and runner != api_sha:
        mismatch = _mismatch_blocker(approved=runner, api=api_sha, worker=worker_sha)
        blocking_failures.append(mismatch)
        live_blockers.append(mismatch)
    if runner and worker_sha and runner != worker_sha:
        mismatch = _mismatch_blocker(approved=runner, api=api_sha, worker=worker_sha)
        blocking_failures.append(mismatch)
        live_blockers.append(mismatch)

    runtime_consistent = bool(
        api_sha
        and worker_sha
        and api_sha == worker_sha
        and (not approved or approved == api_sha)
        and (not runner or runner == api_sha)
        and not blocking_failures
    )

    return {
        "approved_runtime_sha": approved,
        "runner_runtime_sha": runner,
        "api_runtime_sha": api_sha,
        "worker_runtime_sha": worker_sha,
        "runtime_sha_consistent": runtime_consistent,
        "runtime_readiness_endpoint_verified": endpoint_verified,
        "blocking_failures": blocking_failures,
        "live_execution_blockers": live_blockers,
        "authoritative_runtime_sha": api_sha,
    }
