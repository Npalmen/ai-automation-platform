"""Live evaluation errors."""

from __future__ import annotations

from typing import Any


class LiveEvalSafetyError(Exception):
    """Fail-closed live eval violation — must not trigger LLM fallback or external writes."""


class LiveEvalIntakeSkippedError(Exception):
    """Structured intake skip (HTTP 409) — configuration/gate, not transport."""

    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        super().__init__(str(payload.get("intake_skip_reason") or "intake_skipped"))
