"""Feature flag fail-closed drift checks."""

from __future__ import annotations

from app.core.settings import get_settings


RISK_FLAGS = (
    "END_CUSTOMER_READ_API_ENABLED",
    "END_CUSTOMER_WRITE_API_ENABLED",
    "END_CUSTOMER_SHADOW_INTAKE_ENABLED",
    "END_CUSTOMER_SHADOW_MATCHING_ENABLED",
    "END_CUSTOMER_SHADOW_PROMOTION_ENABLED",
)


def validate_feature_flag_defaults() -> list[str]:
    settings = get_settings()
    failures: list[str] = []
    for flag in RISK_FLAGS:
        if bool(getattr(settings, flag, False)):
            failures.append(f"{flag} default must be false for fail-closed regression")
    return failures
