"""Semantic hashing for deterministic evaluation comparisons."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

EVAL_TENANT_PREFIX = "eval_cd_"

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
_ISO_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def _normalize_string(value: str) -> str:
    normalized = _UUID_RE.sub("{{uuid}}", value)
    normalized = _ISO_TS_RE.sub("{{timestamp}}", normalized)
    if value.startswith(EVAL_TENANT_PREFIX):
        return "{{eval_tenant}}"
    return normalized


def normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: normalize_value(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [normalize_value(v) for v in value]
    if isinstance(value, str):
        return _normalize_string(value)
    return value


def semantic_hash(payload: dict[str, Any]) -> str:
    normalized = normalize_value(payload)
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
