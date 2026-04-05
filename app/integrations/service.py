# app/integrations/service.py

from app.core.settings import get_settings
from app.integrations.enums import IntegrationType


def get_integration_connection_config(
    tenant_id: str,
    integration_type: IntegrationType,
) -> dict:
    settings = get_settings()

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