"""Locked constants for the production pilot."""

from __future__ import annotations

PRODUCTION_PILOT_MARKER = "production-pilot-v1"
PILOT_TENANT_ID = "TENANT_PRODUCTION_PILOT_01"
RELEASE_VERSION = "pilot-v0.1.0"
MANIFEST_SCHEMA_VERSION = "production-pilot.release-manifest.v1"
READINESS_SCHEMA_VERSION = "production-pilot.readiness.v1"
PREFLIGHT_SCHEMA_VERSION = "production-pilot.p0-preflight.v1"

ACTIVATION_STAGES = ("P0", "P1", "P2", "P3")
DEFAULT_ACTIVATION_STAGE = "P0"

MIGRATION_HEAD = "024_end_customer_shadow_ledger"
CAPABILITY_REGISTRY_VERSION = "full_function_matrix_v1"
QUALIFICATION_REGISTRY_VERSION = "continuous_regression_v1"

ALLOWED_PILOT_INTEGRATIONS = frozenset({"google_mail"})
BLOCKED_PILOT_INTEGRATIONS = frozenset({"google_sheets", "monday", "visma", "fortnox"})

P0_MAX_SYNTHETIC_INBOUND = 2
P0_GMAIL_REPLY_BUDGET = 0
P0_NON_GMAIL_WRITE_BUDGET = 0

BLOCKED_AUTO_MODES = frozenset({"auto", "full_auto", True})
