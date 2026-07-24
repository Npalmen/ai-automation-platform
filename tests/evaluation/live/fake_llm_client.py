"""Hermetic fake LLM delegate for live_llm eval tests."""

from __future__ import annotations

from typing import Any

from app.ai.llm.client import LLMGenerationResult
from app.evaluation.fixture_ai import _active_prompt_name
from app.evaluation.live.fixture_bundle import BUNDLE_FIXTURES

_S01_FIXTURES = BUNDLE_FIXTURES["k2f_bundle_s01"]


class FakeEvalLLMDelegate:
  """Deterministic S01 responses with required provenance metadata."""

  def __init__(
      self,
      *,
      model: str = "fake-eval-model",
      fixtures: dict[str, dict[str, Any]] | None = None,
      missing_usage: bool = False,
      wrong_model: bool = False,
      returned_model: str | None = None,
      finish_reason: str | None = "stop",
      malformed_json: bool = False,
      raise_timeout: bool = False,
      raise_rate_limit: bool = False,
  ):
    self.model = model
    self._fixtures = fixtures or _S01_FIXTURES
    self.missing_usage = missing_usage
    self.wrong_model = wrong_model
    self.returned_model = returned_model
    self.finish_reason = finish_reason
    self.malformed_json = malformed_json
    self.raise_timeout = raise_timeout
    self.raise_rate_limit = raise_rate_limit
    self.call_count = 0

  def generate_json_detailed(
      self,
      prompt: str,
      *,
      model: str | None = None,
      timeout: float | None = None,
      max_tokens: int | None = None,
      temperature: float | None = None,
      retry_attempts: int | None = None,
  ) -> LLMGenerationResult:
    del prompt, timeout, max_tokens, temperature, retry_attempts
    self.call_count += 1
    if self.raise_timeout:
      raise TimeoutError("fake timeout")
    if self.raise_rate_limit:
      from app.ai.exceptions import LLMRequestError

      raise LLMRequestError("LLM HTTPError 429: rate limit")

    prompt_name = _active_prompt_name.get()
    if not prompt_name:
      for candidate in self._fixtures:
        if candidate in prompt:
          prompt_name = candidate
          break
    if not prompt_name or prompt_name not in self._fixtures:
      raise ValueError(f"fake missing fixture for {prompt_name!r}")

    if self.malformed_json:
      return LLMGenerationResult(
          output={"not": "valid schema"},
          returned_model=self.model,
          usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
      )

    if self.wrong_model:
      resolved_model = "other-model"
    elif self.returned_model is not None:
      resolved_model = self.returned_model
    else:
      resolved_model = model or self.model
    usage = (
        {}
        if self.missing_usage
        else {"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20}
    )
    return LLMGenerationResult(
        output=dict(self._fixtures[prompt_name]),
        returned_model=resolved_model,
        usage=usage,
        finish_reason=self.finish_reason,
    )

  def generate_json(self, prompt: str) -> dict[str, Any]:
    return self.generate_json_detailed(prompt).output
