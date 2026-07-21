"""Live evaluation errors."""

from __future__ import annotations


class LiveEvalSafetyError(Exception):
    """Fail-closed live eval violation — must not trigger LLM fallback or external writes."""
