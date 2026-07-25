"""Controlled internal AI-receptionist pilot activation gates."""

from app.internal_pilot.constants import (
    INTERNAL_PILOT_MARKER,
    MAX_PILOT_BATCH_EMAILS,
    PILOT_GMAIL_LABEL_SCOPE,
    PILOT_GMAIL_QUERY,
    PILOT_TENANT_ID,
)
from app.internal_pilot.gates import PilotGateViolation, enforce_pilot_inbox_gates
from app.internal_pilot.readiness import build_internal_pilot_readiness

__all__ = [
    "INTERNAL_PILOT_MARKER",
    "MAX_PILOT_BATCH_EMAILS",
    "PILOT_GMAIL_LABEL_SCOPE",
    "PILOT_GMAIL_QUERY",
    "PILOT_TENANT_ID",
    "PilotGateViolation",
    "build_internal_pilot_readiness",
    "enforce_pilot_inbox_gates",
]
