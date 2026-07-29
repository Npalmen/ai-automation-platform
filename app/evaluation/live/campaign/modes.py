"""Campaign mode and type constants for full-system testbot."""

from __future__ import annotations

# Execution modes (how the app may act during a scenario)
CAMPAIGN_MODES = frozenset({
    "observe",
    "semi_automatic",
    "automatic",
    "customer_card_stateful",
    "integration_sandbox",
    "full_regression",
})

# Named campaign bundles (plan section H)
CAMPAIGN_TYPES = frozenset({
    "transport-smoke",
    "observe-core",
    "semi-auto-core",
    "automatic-gmail-canary",
    "automatic-gmail-core",
    "auto-safe-actions",
    "customer-card-stateful",
    "integration-sandbox",
    "full-regression",
})

# Default mode per campaign type
CAMPAIGN_TYPE_DEFAULT_MODE: dict[str, str] = {
    "transport-smoke": "observe",
    "observe-core": "observe",
    "semi-auto-core": "semi_automatic",
    "automatic-gmail-canary": "automatic",
    "automatic-gmail-core": "automatic",
    "auto-safe-actions": "automatic",
    "customer-card-stateful": "customer_card_stateful",
    "integration-sandbox": "integration_sandbox",
    "full-regression": "full_regression",
}

# Budget ceilings per campaign type (gmail sends per run)
CAMPAIGN_TYPE_SEND_BUDGET: dict[str, int] = {
    "transport-smoke": 5,
    "observe-core": 5,
    "semi-auto-core": 8,
    "automatic-gmail-canary": 2,
    "automatic-gmail-core": 8,
    "auto-safe-actions": 10,
    "customer-card-stateful": 30,
    "integration-sandbox": 10,
    "full-regression": 30,
}

# Reply budget ceilings per campaign type (app Gmail replies to testbot sender)
CAMPAIGN_TYPE_REPLY_BUDGET: dict[str, int] = {
    "semi-auto-core": 4,
    "automatic-gmail-canary": 1,
    "automatic-gmail-core": 3,
}
