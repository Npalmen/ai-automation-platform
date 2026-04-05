import json
import time
from typing import Any
from urllib import error, request

from app.ai.exceptions import (
    LLMConfigurationError,
    LLMRequestError,
    LLMResponseError,
)
from app.core.settings import get_settings


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _build_request(self, prompt: str) -> request.Request:
        payload = {
            "model": self.settings.LLM_MODEL,
            "temperature": self.settings.LLM_TEMPERATURE,
            "max_tokens": self.settings.LLM_MAX_TOKENS,
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

    def _parse_response(self, raw_body: str) -> dict[str, Any]:
        try:
            parsed = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise LLMResponseError(
                f"LLM raw response is not valid JSON: {raw_body}"
            ) from exc

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
            raise LLMResponseError(
                f"LLM returned invalid JSON content: {content}"
            ) from exc

        if not isinstance(output, dict):
            raise LLMResponseError("LLM output must be a JSON object")

        return output

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
                body = exc.read().decode("utf-8", errors="replace")
                last_error = LLMRequestError(f"LLM HTTPError {exc.code}: {body}")

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