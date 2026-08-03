"""Frozen manually-approved R3 send bodies (operator-locked, hash-bound)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (
    R3_APPROVED_SEND_BODY_HASHES,
)
from app.workflows.reply_quality.provenance import hash_body

_BODIES_PATH = Path(__file__).with_name("r3_approved_send_bodies.json")


@lru_cache(maxsize=1)
def load_r3_approved_send_body_texts() -> dict[str, str]:
    bodies = json.loads(_BODIES_PATH.read_text(encoding="utf-8"))
    if not isinstance(bodies, dict):
        raise ValueError("r3_approved_send_bodies.json must be an object")
    return {str(key): str(value) for key, value in bodies.items()}


def r3_send_body_hash(text: str) -> str:
    return hash_body(text)


def resolve_frozen_send_bodies(manifest: dict[str, Any] | None = None) -> dict[str, str]:
    manifest = manifest or {}
    from_manifest = manifest.get("approved_send_body_texts") or {}
    canonical = load_r3_approved_send_body_texts()
    if not from_manifest:
        return dict(canonical)
    merged = dict(canonical)
    merged.update({str(k): str(v) for k, v in from_manifest.items()})
    return merged


def validate_frozen_send_bodies(
    *,
    manifest: dict[str, Any],
    approval_hashes: dict[str, str] | None = None,
) -> list[str]:
    issues: list[str] = []
    approval_hashes = approval_hashes or dict(R3_APPROVED_SEND_BODY_HASHES)
    manifest_hashes = manifest.get("approved_send_body_hashes") or {}
    if manifest_hashes != R3_APPROVED_SEND_BODY_HASHES:
        issues.append("manifest approved_send_body_hashes mismatch")
    bodies = resolve_frozen_send_bodies(manifest)
    expected_ids = set(R3_APPROVED_SEND_BODY_HASHES)
    if set(bodies) != expected_ids:
        missing = sorted(expected_ids - set(bodies))
        extra = sorted(set(bodies) - expected_ids)
        if missing:
            issues.append(f"missing frozen bodies: {', '.join(missing)}")
        if extra:
            issues.append(f"unexpected frozen bodies: {', '.join(extra)}")
    for scenario_id, approved_hash in R3_APPROVED_SEND_BODY_HASHES.items():
        text = bodies.get(scenario_id, "")
        if not text.strip():
            issues.append(f"{scenario_id} frozen body missing")
            continue
        current = r3_send_body_hash(text)
        if current != approved_hash:
            issues.append(f"{scenario_id} frozen body hash mismatch")
        if approval_hashes.get(scenario_id) != approved_hash:
            issues.append(f"{scenario_id} approval hash mismatch")
    return issues
