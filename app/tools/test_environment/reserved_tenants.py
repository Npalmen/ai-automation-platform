"""Version-controlled tenant IDs for local test environment tooling."""

from __future__ import annotations

# Tenants that may be targeted by --profile local-standard purge (explicit allowlist only).
LOCAL_STANDARD_PURGE_ALLOWLIST: frozenset[str] = frozenset(
    {
        "T_LOCAL_OPS_BASELINE",
        "T_LOCAL_OPS_SECONDARY",
    }
)

# Reserved baseline tenant created/updated by seed-baseline.
BASELINE_TENANT_ID = "T_LOCAL_OPS_BASELINE"
BASELINE_TENANT_NAME = "Lokal operatörstest"
