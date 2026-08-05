"""Write-free R4 constrained-LLM readiness (no Gmail / provider ping)."""

from __future__ import annotations

import os
from typing import Any

from app.workflows.reply_quality.llm_renderer import (
    MODEL_ID,
    PROMPT_VERSION,
    RENDERER_POLICY_VERSION,
)
from app.workflows.reply_quality.renderer_requirement import RendererRequirement


def run_r4_constrained_llm_readiness(
    *,
    expected_model: str = MODEL_ID,
    gmail_mutation_enabled: bool = False,
    production_activation: bool = False,
    automatic_gmail: bool = False,
) -> dict[str, Any]:
    """Verify R4 can invoke constrained live LLM without performing writes."""
    blockers: list[str] = []

    llm_render = os.environ.get("DIGITAL_COWORKER_LLM_RENDER", "").lower() in {
        "1",
        "true",
        "live",
    }
    if not llm_render:
        blockers.append("DIGITAL_COWORKER_LLM_RENDER_not_enabled")

    api_key_configured = bool(os.environ.get("LLM_API_KEY", "").strip())
    if not api_key_configured:
        # Also accept settings-backed keys without exposing values.
        try:
            from app.core.settings import get_settings

            api_key_configured = bool(getattr(get_settings(), "LLM_API_KEY", None))
        except Exception:  # noqa: BLE001
            api_key_configured = False
    if not api_key_configured:
        blockers.append("LLM_API_KEY_not_configured")

    endpoint_configured = bool(
        os.environ.get("LLM_API_URL", "").strip()
        or os.environ.get("LLM_BASE_URL", "").strip()
        or os.environ.get("OPENAI_BASE_URL", "").strip()
        or os.environ.get("LLM_API_BASE", "").strip()
    )
    if not endpoint_configured:
        try:
            from app.core.settings import get_settings

            settings = get_settings()
            endpoint_configured = bool(getattr(settings, "LLM_API_URL", None))
        except Exception:  # noqa: BLE001
            endpoint_configured = False
    if not endpoint_configured:
        blockers.append("LLM_endpoint_not_configured")

    if expected_model != MODEL_ID:
        blockers.append(f"requested_model_mismatch:{expected_model}!={MODEL_ID}")

    json_mode_supported = True
    try:
        from app.ai.llm.client import LLMClient

        json_mode_supported = hasattr(LLMClient, "generate_json_detailed")
    except Exception:  # noqa: BLE001
        json_mode_supported = False
    if not json_mode_supported:
        blockers.append("json_response_mode_unsupported")

    timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "30") or 30)
    if timeout <= 0:
        blockers.append("timeout_not_positive")

    retry_count = int(os.environ.get("LLM_RETRY_ATTEMPTS", "2") or 2)
    if retry_count < 1 or retry_count > 5:
        blockers.append(f"retry_count_out_of_range:{retry_count}")

    strict_mode_enabled = RendererRequirement.CONSTRAINED_LLM_REQUIRED.value == (
        "constrained_llm_required"
    )
    if not strict_mode_enabled:
        blockers.append("strict_renderer_mode_missing")

    deterministic_fallback_allowed = False
    if gmail_mutation_enabled:
        blockers.append("gmail_mutation_enabled")
    if production_activation:
        blockers.append("production_activation_true")
    if automatic_gmail:
        blockers.append("automatic_gmail_true")

    return {
        "constrained_llm_ready": not blockers,
        "requested_model_id": MODEL_ID,
        "expected_model_id": expected_model,
        "prompt_version": PROMPT_VERSION,
        "renderer_policy_version": RENDERER_POLICY_VERSION,
        "credentials_configured": api_key_configured,
        "endpoint_configured": endpoint_configured,
        "llm_render_enabled": llm_render,
        "strict_mode_enabled": strict_mode_enabled,
        "deterministic_fallback_allowed": deterministic_fallback_allowed,
        "json_response_mode_supported": json_mode_supported,
        "timeout_seconds": timeout,
        "retry_count": retry_count,
        "gmail_mutation_enabled": gmail_mutation_enabled,
        "production_activation": production_activation,
        "automatic_gmail": automatic_gmail,
        "blockers": blockers,
    }
