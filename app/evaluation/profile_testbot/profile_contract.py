"""Customer profile snapshot contract for profile-driven testbot."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_PROFILE_ROOT = Path(__file__).resolve().parent / "resources" / "customer_profiles"
_REQUIRED_TOP_LEVEL = (
    "profile_id",
    "version",
    "language",
    "business_type",
    "services",
    "service_area",
    "opening_hours",
    "response_tone",
    "safe_acknowledgements",
    "manual_review_topics",
    "forbidden_commitments",
    "escalation_rules",
    "required_information_by_intent",
    "customer_identity_rules",
)


@dataclass(frozen=True)
class CustomerProfileSnapshot:
    profile_id: str
    version: int
    language: str
    business_type: str
    services: dict[str, list[str]]
    service_area: dict[str, list[str]]
    opening_hours: dict[str, str]
    response_tone: str
    safe_acknowledgements: list[str]
    manual_review_topics: list[str]
    forbidden_commitments: list[str]
    escalation_rules: list[dict[str, str]]
    required_information_by_intent: dict[str, list[str]]
    customer_identity_rules: dict[str, Any]
    profile_snapshot_hash: str
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.raw)


def canonical_profile_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def compute_profile_snapshot_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_profile_bytes(payload)).hexdigest()


def validate_profile_payload(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for key in _REQUIRED_TOP_LEVEL:
        if key not in payload:
            failures.append(f"missing field: {key}")
    if not isinstance(payload.get("services"), dict):
        failures.append("services must be object")
    if not isinstance(payload.get("forbidden_commitments"), list):
        failures.append("forbidden_commitments must be list")
    if payload.get("profile_id") and not str(payload["profile_id"]).strip():
        failures.append("profile_id must be non-empty")
    return failures


def load_customer_profile(profile_id: str, *, root: Path | None = None) -> CustomerProfileSnapshot:
    base = root or _PROFILE_ROOT
    path = base / f"{profile_id}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"profile not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"profile {profile_id!r} must be a mapping")
    failures = validate_profile_payload(payload)
    if failures:
        raise ValueError("; ".join(failures))
    snapshot_hash = compute_profile_snapshot_hash(payload)
    return CustomerProfileSnapshot(
        profile_id=str(payload["profile_id"]),
        version=int(payload["version"]),
        language=str(payload["language"]),
        business_type=str(payload["business_type"]),
        services=dict(payload.get("services") or {}),
        service_area=dict(payload.get("service_area") or {}),
        opening_hours=dict(payload.get("opening_hours") or {}),
        response_tone=str(payload["response_tone"]),
        safe_acknowledgements=list(payload.get("safe_acknowledgements") or []),
        manual_review_topics=list(payload.get("manual_review_topics") or []),
        forbidden_commitments=list(payload.get("forbidden_commitments") or []),
        escalation_rules=list(payload.get("escalation_rules") or []),
        customer_identity_rules=dict(payload.get("customer_identity_rules") or {}),
        required_information_by_intent=dict(payload.get("required_information_by_intent") or {}),
        profile_snapshot_hash=snapshot_hash,
        raw=payload,
    )
