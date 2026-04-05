from typing import Any, Dict

from app.integrations.base import IntegrationAdapter


class GoogleIntegrationAdapter(IntegrationAdapter):
    def get_status(self) -> Dict[str, Any]:
        return {
            "integration": "google",
            "enabled": self.connection_config.enabled if self.connection_config else False,
            "connected": self.connection_config.connected if self.connection_config else False,
            "account_name": self.connection_config.account_name if self.connection_config else None,
            "message": "Google integration status loaded from tenant config."
        }

    def execute_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "integration": "google",
            "action": action,
            "payload": payload,
            "status": "not_implemented",
            "account_name": self.connection_config.account_name if self.connection_config else None
        }