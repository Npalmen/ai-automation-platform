"""Integration lifecycle status helpers for Slice 2B onboarding."""

from __future__ import annotations

from typing import Literal

IntegrationLifecycleStatus = Literal[
    "selected",
    "configured",
    "connected",
    "verified",
    "configured_not_running",
    "configured_not_enforced",
    "not_applicable",
    "not_supported",
    "unknown",
]

VerificationStatus = Literal["pending", "verified", "invalidated", "failed"]

SourceClass = Literal[
    "declared",
    "locally_verified",
    "externally_verified",
    "platform_level",
    "not_verifiable",
    "not_applicable",
]
