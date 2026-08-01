"""Versioned quality evaluation dataset (Todo H)."""

from __future__ import annotations

QUALITY_DATASET_VERSION = "profile_quality_dataset_v1"
QUALITY_SCENARIO_TARGET = 96
QUALITY_FAMILY_TARGET = 16
QUALITY_SCENARIOS_PER_FAMILY = 6
MAX_FAMILY_SHARE = 0.15  # no family may exceed 15% of dataset

# Plan-aligned scenario families (16).
QUALITY_FAMILIES: tuple[str, ...] = (
    "complete_new_lead",
    "incomplete_new_lead",
    "existing_customer_support",
    "status_request",
    "pricing_request",
    "booking_request",
    "urgent_safety",
    "complaint_warranty",
    "invoice_payment",
    "supplier_partner",
    "spam_phishing_injection",
    "irrelevant_out_of_scope",
    "gdpr_privacy",
    "attachments_missing_info",
    "mixed_intent",
    "thread_continuation_duplicate",
)
