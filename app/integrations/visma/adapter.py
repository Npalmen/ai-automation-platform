from __future__ import annotations

import logging
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
    """Retrieve a valid Visma access token for a tenant (legacy nullable wrapper)."""
    from app.integrations.visma.token_resolver import VismaTokenError, resolve_visma_access_token

    try:
        return resolve_visma_access_token(db, tenant_id, check_allowlist=False)
    except VismaTokenError:
        return None