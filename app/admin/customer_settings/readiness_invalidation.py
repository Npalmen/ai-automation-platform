"""Readiness domain invalidation mapping for customer settings edits."""

from __future__ import annotations

from app.admin.customer_settings.domains import READINESS_DOMAINS_BY_SETTINGS_DOMAIN


def readiness_domains_for_patch(domain: str) -> list[str]:
    return list(READINESS_DOMAINS_BY_SETTINGS_DOMAIN.get(domain, (domain,)))


def readiness_summary_for_tenant(record) -> dict:
    stale = (
        record.readiness_config_version is not None
        and int(record.readiness_config_version) != int(record.config_version or 1)
    )
    return {
        "stale": stale,
        "config_version": int(record.config_version or 1),
        "readiness_config_version": record.readiness_config_version,
        "readiness_checked_at": (
            record.readiness_checked_at.isoformat() if record.readiness_checked_at else None
        ),
    }
