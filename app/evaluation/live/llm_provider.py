"""Fixture AI provider for live evaluation (app-side, gated)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai.exceptions import LLMClientError
from app.ai.llm.client import LLMClient, get_llm_client
from app.ai.schemas import (
    ClassificationResponse,
    DecisioningResponse,
    EntityExtractionResponse,
    InquiryAnalysisResponse,
    InvoiceAnalysisResponse,
    LeadScoringResponse,
)
from app.evaluation.fixture_ai import (
    _active_prompt_name,
    reset_active_prompt_name,
    set_active_prompt_name,
)
from app.evaluation.live.context import get_current_live_eval_snapshot
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.fixture_bundle import load_bundle_fixtures
from app.evaluation.live.safety import require_live_eval_enabled, require_tenant_allowed
from app.evaluation.live.config import get_live_eval_config

PROMPT_RESPONSE_MODELS: dict[str, type[BaseModel]] = {
    "classification_v1": ClassificationResponse,
    "entity_extraction_v1": EntityExtractionResponse,
    "lead_scoring_v1": LeadScoringResponse,
    "customer_inquiry_analysis_v1": InquiryAnalysisResponse,
    "decisioning_v1": DecisioningResponse,
    "invoice_analysis_v1": InvoiceAnalysisResponse,
}


class FixtureEvalLLMClient:
    """Deterministic fixtures from server allowlisted bundles."""

    def __init__(self, fixtures: dict[str, dict[str, Any]]):
        self._fixtures = fixtures

    def generate_json(self, prompt: str) -> dict[str, Any]:
        prompt_name = _active_prompt_name.get()
        if not prompt_name:
            for name in PROMPT_RESPONSE_MODELS:
                if name in prompt:
                    prompt_name = name
                    break
        if not prompt_name or prompt_name not in self._fixtures:
            raise LiveEvalSafetyError(
                f"fixture_ai missing allowlisted fixture for prompt {prompt_name!r}"
            )
        model = PROMPT_RESPONSE_MODELS[prompt_name]
        validated = model.model_validate(self._fixtures[prompt_name])
        return json.loads(validated.model_dump_json())


def resolve_llm_client(*, job, db: Session | None = None):
    """Select LLM client based on trusted live_eval snapshot on job."""
    input_data = getattr(job, "input_data", None) or {}
    raw = input_data.get("live_eval") if isinstance(input_data, dict) else None
    if not isinstance(raw, dict) or not raw.get("trusted"):
        return get_llm_client()

    snapshot = get_current_live_eval_snapshot()
    if snapshot is None:
        raise LiveEvalSafetyError("live_eval job missing in-process trusted snapshot")

    config = require_live_eval_enabled()
    require_tenant_allowed(snapshot.tenant_id, config)

    if snapshot.ai_mode == "fixture_ai":
        if not snapshot.fixture_bundle_id:
            raise LiveEvalSafetyError("fixture_ai run missing fixture_bundle_id")
        fixtures = load_bundle_fixtures(snapshot.fixture_bundle_id)
        return FixtureEvalLLMClient(fixtures)

    if snapshot.ai_mode == "live_llm":
        if not config.llm_enabled:
            raise LiveEvalSafetyError("LIVE_LLM_EVAL_ALLOWED is required for live_llm")
        return get_llm_client()

    raise LiveEvalSafetyError(f"Unsupported ai_mode {snapshot.ai_mode!r}")


# Re-export prompt context helpers for ai_processor_utils compatibility
__all__ = [
    "resolve_llm_client",
    "FixtureEvalLLMClient",
    "set_active_prompt_name",
    "reset_active_prompt_name",
    "LiveEvalSafetyError",
]
