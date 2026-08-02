"""Renderer provenance for reply auditability."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

RENDERER_POLICY_VERSION = "digital_coworker_renderer_v1"
DETERMINISTIC_RENDERER = "deterministic_structured_v1"
LLM_RENDERER = "constrained_llm_v1"
LEGACY_RENDERER = "legacy_safe_ack_v1"


@dataclass(frozen=True)
class ReplyRenderProvenance:
    renderer_type: str
    llm_used: bool
    model_id: str | None
    prompt_version: str | None
    template_version: str
    use_fallback: bool
    fallback_reason: str | None
    plan_hash: str
    body_hash: str
    draft_body_hash: str | None
    sent_body_hash: str | None
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "renderer_type": self.renderer_type,
            "llm_used": self.llm_used,
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "template_version": self.template_version,
            "use_fallback": self.use_fallback,
            "fallback_reason": self.fallback_reason,
            "plan_hash": self.plan_hash,
            "body_hash": self.body_hash,
            "draft_body_hash": self.draft_body_hash,
            "sent_body_hash": self.sent_body_hash,
            "policy_version": self.policy_version,
        }


def hash_plan(plan_dict: dict[str, Any]) -> str:
    payload = json.dumps(plan_dict, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hash_body(body: str) -> str:
    normalized = " ".join((body or "").split()).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
