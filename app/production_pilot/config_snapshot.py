"""Tenant config snapshot and restore with hash verification."""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from app.production_pilot.constants import PRODUCTION_PILOT_MARKER


def canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def snapshot_payload(settings: dict[str, Any] | None) -> dict[str, Any]:
    source = copy.deepcopy(settings or {})
    pilot = dict(source.get("production_pilot") or {})
    return {
        "marker": PRODUCTION_PILOT_MARKER,
        "activation_stage": pilot.get("activation_stage"),
        "scheduler": source.get("scheduler"),
        "automation": source.get("automation"),
        "operations": source.get("operations"),
        "allowed_integrations": source.get("allowed_integrations"),
        "auto_actions": source.get("auto_actions"),
        "production_pilot_intake": source.get("production_pilot_intake"),
        "production_pilot": pilot,
    }


def compute_snapshot_hash(settings: dict[str, Any] | None) -> str:
    return hashlib.sha256(canonical_json_bytes(snapshot_payload(settings))).hexdigest()


def build_snapshot_record(settings: dict[str, Any] | None) -> dict[str, Any]:
    payload = snapshot_payload(settings)
    snapshot_hash = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return {
        "snapshot_schema_version": "production-pilot.config-snapshot.v1",
        "snapshot_hash": snapshot_hash,
        "payload": payload,
    }


def restore_snapshot_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    payload = copy.deepcopy(snapshot.get("payload") or {})
    restored = {
        "scheduler": payload.get("scheduler") or {"run_mode": "paused"},
        "automation": payload.get("automation") or {"demo_mode": True, "automatic_gmail_replies": False},
        "operations": payload.get("operations") or {"paused": True},
        "allowed_integrations": payload.get("allowed_integrations") or ["google_mail"],
        "auto_actions": payload.get("auto_actions") or {},
        "production_pilot_intake": payload.get("production_pilot_intake") or {"enabled": False},
        "production_pilot": payload.get("production_pilot") or {},
    }
    pilot = dict(restored["production_pilot"])
    pilot["marker"] = PRODUCTION_PILOT_MARKER
    restored["production_pilot"] = pilot
    return restored


def verify_snapshot_hash(snapshot: dict[str, Any]) -> bool:
    expected = snapshot.get("snapshot_hash")
    if not expected:
        return False
    payload = snapshot.get("payload") or {}
    actual = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return actual == expected
