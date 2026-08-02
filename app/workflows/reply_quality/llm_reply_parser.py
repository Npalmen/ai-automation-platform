"""Typed parsing for constrained coworker LLM provider output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

REPLY_BODY_KEYS = ("reply_body", "body", "customer_reply", "email_body")


class LLMReplyParseError(ValueError):
    """Provider returned data that cannot be parsed into a reply body."""


@dataclass(frozen=True)
class ParsedLLMReply:
    reply_body: str
    source_key: str


def _coerce_output_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if not stripped:
            raise LLMReplyParseError("llm_output_empty")
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise LLMReplyParseError("llm_output_malformed_json") from exc
        if not isinstance(parsed, dict):
            raise LLMReplyParseError("llm_output_not_object")
        return parsed
    raise LLMReplyParseError(f"llm_output_unsupported_type:{type(raw).__name__}")


def parse_llm_reply_output(raw: Any) -> ParsedLLMReply:
    """Parse provider output into a customer reply body without str()-coercion."""
    output = _coerce_output_dict(raw)
    for key in REPLY_BODY_KEYS:
        value = output.get(key)
        if isinstance(value, str) and value.strip():
            return ParsedLLMReply(reply_body=value.strip(), source_key=key)
    raise LLMReplyParseError("llm_output_missing_reply_body")
