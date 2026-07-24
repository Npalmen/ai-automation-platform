import json
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from app.ai.exceptions import (
    LLMConfigurationError,
    LLMRequestError,
    LLMResponseError,
)
from app.core.settings import get_settings


@dataclass(frozen=True)
class LLMGenerationResult:
    output: dict[str, Any]
    returned_model: str
    usage: dict[str, int]
    finish_reason: str | None = None
    raw_response: dict[str, Any] | None = None


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _build_request(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> request.Request:
        payload = {
            "model": model or self.settings.LLM_MODEL,
            "temperature": self.settings.LLM_TEMPERATURE if temperature is None else temperature,
            "max_tokens": max_tokens or self.settings.LLM_MAX_TOKENS,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a strict JSON engine. "
                        "Always return valid JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        }

        return request.Request(
            self.settings.LLM_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.settings.LLM_API_KEY}",
            },
            method="POST",
        )

    def _parse_response_body(self, raw_body: str) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise LLMResponseError("LLM raw response is not valid JSON") from exc

        choices = parsed.get("choices") or []
        if not choices:
            raise LLMResponseError("LLM response missing choices")

        message = choices[0].get("message") or {}
        content = message.get("content")

        if not content or not isinstance(content, str):
            raise LLMResponseError("LLM response missing message content")

        try:
            output = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMResponseError("LLM returned invalid JSON content") from exc

        if not isinstance(output, dict):
            raise LLMResponseError("LLM output must be a JSON object")

        return output, parsed

    def _parse_response(self, raw_body: str) -> dict[str, Any]:
        output, _parsed = self._parse_response_body(raw_body)
        return output

    @staticmethod
    def _extract_usage(parsed: dict[str, Any]) -> dict[str, int]:
        usage = parsed.get("usage") or {}
        return {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }

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
        if not self.settings.LLM_API_KEY:
            raise LLMConfigurationError("LLM_API_KEY is not configured")

        last_error: Exception | None = None
        attempts = max(1, int(retry_attempts if retry_attempts is not None else self.settings.LLM_RETRY_ATTEMPTS))
        timeout_seconds = float(timeout if timeout is not None else self.settings.LLM_TIMEOUT_SECONDS)

        for attempt in range(1, attempts + 1):
            req = self._build_request(
                prompt,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            try:
                with request.urlopen(req, timeout=timeout_seconds) as response:
                    raw_body = response.read().decode("utf-8")

                output, parsed = self._parse_response_body(raw_body)
                choices = parsed.get("choices") or []
                finish_reason = None
                if choices:
                    finish_reason = choices[0].get("finish_reason")
                returned_model = str(parsed.get("model") or model or self.settings.LLM_MODEL)
                return LLMGenerationResult(
                    output=output,
                    returned_model=returned_model,
                    usage=self._extract_usage(parsed),
                    finish_reason=finish_reason,
                    raw_response=parsed,
                )

            except error.HTTPError as exc:
                exc.read()
                last_error = LLMRequestError(f"LLM HTTPError {exc.code}")

                if exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                    raise last_error from exc

            except error.URLError as exc:
                last_error = LLMRequestError(f"LLM URLError: {exc}")

            except LLMResponseError as exc:
                last_error = exc

            except Exception as exc:
                last_error = LLMRequestError(f"Unexpected LLM request failure: {exc}")

            if attempt < attempts:
                time.sleep(float(self.settings.LLM_RETRY_DELAY_SECONDS))

        if last_error is not None:
            raise last_error

        raise LLMRequestError("LLM request failed without a captured error")

    def generate_json(self, prompt: str) -> dict[str, Any]:
        if not self.settings.LLM_API_KEY:
            raise LLMConfigurationError("LLM_API_KEY is not configured")

        last_error: Exception | None = None
        attempts = max(1, int(self.settings.LLM_RETRY_ATTEMPTS))

        for attempt in range(1, attempts + 1):
            req = self._build_request(prompt)

            try:
                with request.urlopen(
                    req,
                    timeout=self.settings.LLM_TIMEOUT_SECONDS,
                ) as response:
                    raw_body = response.read().decode("utf-8")

                return self._parse_response(raw_body)

            except error.HTTPError as exc:
                exc.read()
                last_error = LLMRequestError(f"LLM HTTPError {exc.code}")

                # retry only on transient server/rate-limit style errors
                if exc.code not in {408, 409, 429, 500, 502, 503, 504}:
                    raise last_error from exc

            except error.URLError as exc:
                last_error = LLMRequestError(f"LLM URLError: {exc}")

            except LLMResponseError as exc:
                last_error = exc

            except Exception as exc:
                last_error = LLMRequestError(f"Unexpected LLM request failure: {exc}")

            if attempt < attempts:
                time.sleep(float(self.settings.LLM_RETRY_DELAY_SECONDS))

        if last_error is not None:
            raise last_error

        raise LLMRequestError("LLM request failed without a captured error")


_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client

    if _client is None:
        _client = LLMClient()

    return _client