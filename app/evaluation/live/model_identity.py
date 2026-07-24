"""Explicit requested-model to returned-model identity contract for live LLM eval."""

from __future__ import annotations

import hashlib
import json

from app.evaluation.live.errors import LiveEvalSafetyError

LIVE_EVAL_ALLOWED_RETURNED_MODELS: dict[str, frozenset[str]] = {
    "gpt-4o-mini": frozenset(
        {
            "gpt-4o-mini",
            "gpt-4o-mini-2024-07-18",
        }
    ),
}


def model_identity_registry_fingerprint() -> str:
    payload = {
        alias: sorted(allowed)
        for alias, allowed in sorted(LIVE_EVAL_ALLOWED_RETURNED_MODELS.items())
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_model_identity_registry() -> list[str]:
    issues: list[str] = []
    if not LIVE_EVAL_ALLOWED_RETURNED_MODELS:
        issues.append("model identity allowlist is empty")
        return issues
    for alias, allowed in LIVE_EVAL_ALLOWED_RETURNED_MODELS.items():
        if not isinstance(alias, str) or not alias.strip():
            issues.append("model identity alias must be a non-empty exact string")
            continue
        if not allowed:
            issues.append(f"model identity allowlist for {alias!r} is empty")
            continue
        for returned in allowed:
            if not isinstance(returned, str) or not returned.strip():
                issues.append(f"model identity allowlist value for {alias!r} must be non-empty")
            if returned != returned.strip():
                issues.append(f"model identity allowlist value for {alias!r} must be exact")
            if "*" in returned or "?" in returned:
                issues.append(f"wildcard model identity values are forbidden for {alias!r}")
    return issues


def allowed_returned_models(requested_model: str) -> frozenset[str]:
    requested = (requested_model or "").strip()
    if not requested:
        raise LiveEvalSafetyError("live_llm missing pinned model in trusted snapshot")
    allowed = LIVE_EVAL_ALLOWED_RETURNED_MODELS.get(requested)
    if allowed is None:
        raise LiveEvalSafetyError(f"live_llm requested model {requested!r} is not allowlisted")
    return allowed


def validate_returned_model_identity(
    *,
    requested_model: str,
    returned_model: str | None,
) -> str:
    """Return normalized returned model or raise LiveEvalSafetyError."""
    requested = (requested_model or "").strip()
    returned = (returned_model or "").strip()
    if not returned:
        raise LiveEvalSafetyError("live_llm provider missing returned model")
    allowed = allowed_returned_models(requested)
    if returned not in allowed:
        raise LiveEvalSafetyError(
            f"live_llm returned model {returned!r} is not allowlisted for {requested!r}"
        )
    return returned
