"""Shared constants for continuous regression."""

from __future__ import annotations

REGISTRY_VERSION = 1
QUALIFICATION_REGISTRY_VERSION = 1
REPORT_SCHEMA_VERSION = "continuous_regression_report_v1"
SEMANTIC_HASH_VERSION = "semantic_hash_v1"

TIER_H1 = "pr_fast"
TIER_H2 = "main_pg"
TIER_H3 = "nightly"
TIER_H4 = "manual_canary"

AUTOMATED_TIERS = frozenset({TIER_H1, TIER_H2, TIER_H3})
FORBIDDEN_NETWORK_TIERS = AUTOMATED_TIERS
ZERO_WRITE_BUDGET_TIERS = AUTOMATED_TIERS

EXPECTED_TBR_IDS = tuple(f"TBR{index:02d}" for index in range(1, 21))

SECURITY_CRITICAL_SUITE_TAGS = frozenset({
    "tenant_isolation",
    "unauthorized_writes",
    "pre_write_safety",
    "idempotency",
    "cleanup",
    "feature_flags",
    "redaction",
    "automatic_verify_merge",
})
