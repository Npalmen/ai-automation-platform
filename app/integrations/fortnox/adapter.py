from typing import Any

from app.integrations.base import BaseIntegrationAdapter
from app.integrations.fortnox.client import FortnoxClient


class FortnoxAdapter(BaseIntegrationAdapter):
    def __init__(self, connection_config: dict[str, Any] | None = None):
        super().__init__(connection_config=connection_config)

        access_token = self.connection_config.get("access_token")
        client_secret = self.connection_config.get("client_secret")
        api_url = self.connection_config.get("api_url", "https://api.fortnox.se/3")

        if not access_token:
            raise ValueError("Missing fortnox access_token in connection_config.")

        if not client_secret:
            raise ValueError("Missing fortnox client_secret in connection_config.")

        self.client = FortnoxClient(
            access_token=access_token,
            client_secret=client_secret,
            api_url=api_url,
        )

    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "create_customer":
            customer = payload.get("customer")
            if not customer:
                raise ValueError("Missing 'customer' for fortnox create_customer action.")

            result = self.client.create_customer(customer)

            return {
                "status": "success",
                "integration": "fortnox",
                "action": action,
                "result": result,
            }

        if action == "create_invoice":
            invoice = payload.get("invoice")
            if not invoice:
                raise ValueError("Missing 'invoice' for fortnox create_invoice action.")

            result = self.client.create_invoice(invoice)

            return {
                "status": "success",
                "integration": "fortnox",
                "action": action,
                "result": result,
            }

        raise ValueError(f"Unsupported fortnox action: {action}")

    def get_status(self) -> dict[str, Any]:
        result = self.client.get_company_information()

        return {
            "status": "connected",
            "integration": "fortnox",
            "result": result,
        }