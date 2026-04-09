# app/integrations/service.py
from __future__ import annotations

import os
import re

from app.core.settings import get_settings
from app.integrations.enums import IntegrationType


def _normalize_tenant_key(tenant_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "_", tenant_id or "")
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized.upper()


def _tenant_override(tenant_id: str, key: str) -> str | None:
    tenant_key = _normalize_tenant_key(tenant_id)
    if not tenant_key:
        return None

    candidates = (
        f"TENANT_{tenant_key}__{key}",
        f"TENANT_{tenant_key}_{key}",
    )

    for candidate in candidates:
        value = os.getenv(candidate)
        if value not in (None, ""):
            return value

    return None


def _tenant_or_default(tenant_id: str, key: str, default):
    override = _tenant_override(tenant_id, key)
    if override is None:
        return default
    return override


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def get_integration_connection_config(
    tenant_id: str,
    integration_type: IntegrationType,
) -> dict:
    settings = get_settings()
    

    if integration_type == IntegrationType.SLACK:
        return {
            "provider": _tenant_or_default(tenant_id, "SLACK_PROVIDER", settings.SLACK_PROVIDER),
            "webhook_url": _tenant_or_default(
                tenant_id,
                "SLACK_WEBHOOK_URL",
                settings.SLACK_WEBHOOK_URL,
            ),
            "timeout_seconds": int(
                _tenant_or_default(
                    tenant_id,
                    "SLACK_TIMEOUT_SECONDS",
                    settings.SLACK_TIMEOUT_SECONDS,
                )
            ),
        }

    if integration_type == IntegrationType.MONDAY:
        return {
            "api_key": settings.MONDAY_API_KEY,
            "api_url": settings.MONDAY_API_URL,
            "board_id": settings.MONDAY_BOARD_ID,
        }

    if integration_type == IntegrationType.FORTNOX:
        return {
            "access_token": settings.FORTNOX_ACCESS_TOKEN,
            "client_secret": settings.FORTNOX_CLIENT_SECRET,
            "api_url": settings.FORTNOX_API_URL,
        }

    if integration_type == IntegrationType.VISMA:
        return {
            "access_token": settings.VISMA_ACCESS_TOKEN,
            "api_url": settings.VISMA_API_URL,
        }

    if integration_type == IntegrationType.GOOGLE_MAIL:
        return {
            "access_token": settings.GOOGLE_MAIL_ACCESS_TOKEN,
            "api_url": settings.GOOGLE_MAIL_API_URL,
            "user_id": settings.GOOGLE_MAIL_USER_ID,
        }

    if integration_type == IntegrationType.GOOGLE_CALENDAR:
        return {
            "access_token": settings.GOOGLE_CALENDAR_ACCESS_TOKEN,
            "api_url": settings.GOOGLE_CALENDAR_API_URL,
            "calendar_id": settings.GOOGLE_CALENDAR_ID,
        }

    if integration_type == IntegrationType.MICROSOFT_MAIL:
        return {
            "access_token": settings.MICROSOFT_MAIL_ACCESS_TOKEN,
            "api_url": settings.MICROSOFT_GRAPH_API_URL,
        }

    if integration_type == IntegrationType.MICROSOFT_CALENDAR:
        return {
            "access_token": settings.MICROSOFT_CALENDAR_ACCESS_TOKEN,
            "api_url": settings.MICROSOFT_GRAPH_API_URL,
            "timezone": settings.MICROSOFT_CALENDAR_TIMEZONE,
        }

    if integration_type == IntegrationType.CRM:
        return {
            "api_key": settings.CRM_API_KEY,
            "base_url": settings.CRM_WEBHOOK_URL,
        }

    if integration_type == IntegrationType.ACCOUNTING:
        return {
            "api_key": settings.ACCOUNTING_API_KEY,
            "base_url": settings.ACCOUNTING_WEBHOOK_URL,
        }

    if integration_type == IntegrationType.SUPPORT:
        return {
            "api_key": settings.SUPPORT_API_KEY,
            "base_url": settings.SUPPORT_WEBHOOK_URL,
        }

    raise ValueError(
        f"Unsupported integration type '{integration_type.value}' for tenant '{tenant_id}'."
    )


def is_integration_configured(connection_config: dict) -> bool:
    provider = str(connection_config.get("provider") or "").strip().lower()

    if provider == "smtp":
        return bool(
            connection_config.get("host")
            and connection_config.get("port")
            and connection_config.get("from_email")
        )

    if provider == "webhook":
        return bool(connection_config.get("webhook_url"))

    # Token-based integrations (Google Mail, Microsoft, etc.) are configured
    # when an access_token and api_url are both present.
    if connection_config.get("access_token") and connection_config.get("api_url"):
        return True

    return False