"""Locked constants for the internal live pilot."""

from __future__ import annotations

from app.admin.onboarding.integration_fingerprint import build_gmail_label_query

INTERNAL_PILOT_MARKER = "internal-live-pilot-v1"

PILOT_TENANT_ID = "T_NIKLAS_DEMO_001"
PILOT_GMAIL_LABEL_SCOPE = "demo-niklas"
PILOT_GMAIL_QUERY = build_gmail_label_query(PILOT_GMAIL_LABEL_SCOPE)

MAX_PILOT_BATCH_EMAILS = 5
MIN_PILOT_FIRST_BATCH_EMAILS = 3

ALLOWED_PILOT_JOB_TYPES = frozenset(
    {
        "lead",
        "customer_inquiry",
        "invoice",
        "unknown",
    }
)

BLOCKED_AUTO_ACTION_MODES = frozenset({"auto", "full_auto", True})
