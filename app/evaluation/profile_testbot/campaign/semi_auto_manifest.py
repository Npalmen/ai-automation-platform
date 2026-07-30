"""Locked PTB-SEM scenario manifest for live semi-auto Gmail campaigns."""

from __future__ import annotations

import hashlib
import json

from app.evaluation.profile_testbot.constants import SEMI_AUTO_SCENARIO_TARGET

# Deterministic generator IDs (seed=0, any authorized profile) — do not edit ad hoc.
LOCKED_PTB_SEM_SCENARIO_IDS: frozenset[str] = frozenset(
    f"PTB-SEM-{index:04d}" for index in range(SEMI_AUTO_SCENARIO_TARGET)
)

LOCKED_PTB_SEM_MANIFEST_HASH: str = hashlib.sha256(
    json.dumps(sorted(LOCKED_PTB_SEM_SCENARIO_IDS), separators=(",", ":")).encode("utf-8")
).hexdigest()

AUTHORIZED_LIVE_SEMI_AUTO_PROFILE_IDS: frozenset[str] = frozenset(
    {
        "pilot-service-company-v1",
        "niklas-demo-live-eval-v1",
    }
)


def is_locked_ptb_sem_scenario_id(scenario_id: str) -> bool:
    return (scenario_id or "").strip() in LOCKED_PTB_SEM_SCENARIO_IDS
