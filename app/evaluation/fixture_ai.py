"""Fixture-backed LLM client for deterministic evaluation."""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Any

from pydantic import BaseModel

from app.ai.exceptions import LLMClientError
from app.ai.schemas import (
    ClassificationResponse,
    DecisioningResponse,
    EntityExtractionResponse,
    InquiryAnalysisResponse,
    InvoiceAnalysisResponse,
    LeadScoringResponse,
)
from app.evaluation.errors import FixtureAIError

PROMPT_RESPONSE_MODELS: dict[str, type[BaseModel]] = {
    "classification_v1": ClassificationResponse,
    "entity_extraction_v1": EntityExtractionResponse,
    "lead_scoring_v1": LeadScoringResponse,
    "customer_inquiry_analysis_v1": InquiryAnalysisResponse,
    "decisioning_v1": DecisioningResponse,
    "invoice_analysis_v1": InvoiceAnalysisResponse,
}

_active_prompt_name: ContextVar[str | None] = ContextVar("eval_active_prompt_name", default=None)


def set_active_prompt_name(prompt_name: str | None):
    return _active_prompt_name.set(prompt_name)


def reset_active_prompt_name(token) -> None:
    _active_prompt_name.reset(token)


class FixtureAIClient:
    """Returns schema-valid JSON per prompt_name; tracks usage."""

    def __init__(self, fixtures: dict[str, dict[str, Any]], *, mode: str = "fixture_ai"):
        self._fixtures = dict(fixtures)
        self._mode = mode
        self._called: set[str] = set()

    def generate_json(self, prompt: str) -> dict[str, Any]:
        if self._mode == "forced_fallback":
            raise LLMClientError("forced_fallback evaluation mode")

        prompt_name = _active_prompt_name.get()
        if not prompt_name:
            prompt_name = self._resolve_prompt_name(prompt)
        if prompt_name not in self._fixtures:
            raise FixtureAIError(
                f"Unexpected AI call for prompt '{prompt_name}' with no fixture defined"
            )
        raw = self._fixtures[prompt_name]
        model = PROMPT_RESPONSE_MODELS.get(prompt_name)
        if model is None:
            raise FixtureAIError(f"No response model registered for prompt '{prompt_name}'")
        validated = model.model_validate(raw)
        self._called.add(prompt_name)
        return json.loads(validated.model_dump_json())

    def finalize(self) -> None:
        unused = set(self._fixtures) - self._called
        if unused:
            raise FixtureAIError(f"Unused AI fixtures: {sorted(unused)}")

    @staticmethod
    def _resolve_prompt_name(prompt: str) -> str:
        for name in PROMPT_RESPONSE_MODELS:
            if name in prompt:
                return name
        raise FixtureAIError("Could not resolve prompt_name from rendered prompt")
