from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.integrations.base import BaseIntegrationAdapter
from app.integrations.visma.client import VismaClient

logger = logging.getLogger(__name__)


class VismaAdapter(BaseIntegrationAdapter):
    def __init__(self, connection_config: dict[str, Any] | None = None):
        super().__init__(connection_config=connection_config)

        access_token = self.connection_config.get("access_token")
        api_url = self.connection_config.get(
            "api_url",
            "https://eaccountingapi.vismaonline.com/v2",
        )

        if not access_token:
            raise ValueError("Missing visma access_token in connection_config.")

        self.client = VismaClient(
            access_token=access_token,
            api_url=api_url,
        )

    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "create_customer":
            customer = payload.get("customer")
            if not customer:
                raise ValueError("Missing 'customer' for visma create_customer action.")

            result = self.client.create_customer(customer)

            return {
                "status": "success",
                "integration": "visma",
                "action": action,
                "result": result,
            }

        if action == "create_invoice":
            invoice = payload.get("invoice")
            if not invoice:
                raise ValueError("Missing 'invoice' for visma create_invoice action.")

            result = self.client.create_customer_invoice(invoice)

            return {
                "status": "success",
                "integration": "visma",
                "action": action,
                "result": result,
            }

        raise ValueError(f"Unsupported visma action: {action}")

    def get_status(self) -> dict[str, Any]:
        result = self.client.get_company()

        return {
            "status": "connected",
            "integration": "visma",
            "result": result,
        }


def get_visma_access_token_for_tenant(db, tenant_id: str) -> str | None:
    """Retrieve a valid Visma access token for a tenant, refreshing if expired."""
    from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
    from app.integrations.visma.oauth_service import refresh_access_token

    record = OAuthCredentialRepository.get(db, tenant_id, "visma")
    if record is None:
        return None

    now = datetime.now(timezone.utc)
    if record.expires_at and record.expires_at < now and record.refresh_token:
        try:
            refreshed = refresh_access_token(record.refresh_token)
            OAuthCredentialRepository.upsert(
                db=db,
                tenant_id=tenant_id,
                provider="visma",
                access_token=refreshed["access_token"],
                refresh_token=refreshed["refresh_token"],
                expires_at=refreshed["expires_at"],
                scopes=refreshed.get("scopes") or record.scopes,
            )
            logger.info("Visma token auto-refreshed for tenant %s", tenant_id)
            return refreshed["access_token"]
        except Exception:
            logger.warning("Visma token refresh failed for tenant %s", tenant_id)
            return None

    return record.access_token