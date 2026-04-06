# app/integrations/internal_stub.py
from __future__ import annotations

import logging
from typing import Any

from app.integrations.base import BaseIntegrationAdapter


logger = logging.getLogger(__name__)


class InternalStubAdapter(BaseIntegrationAdapter):
    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        integration = str(self.connection_config.get("integration") or "internal")
        provider = str(self.connection_config.get("provider") or "internal_stub")
        message = str(
            self.connection_config.get("message")
            or "Action executed by internal stub because no real provider is configured."
        )

        logger.info(
            "Executing internal stub action",
            extra={
                "integration": integration,
                "provider": provider,
                "action": action,
            },
        )

        return {
            "status": "stubbed",
            "integration": integration,
            "provider": provider,
            "action": action,
            "payload": payload,
            "message": message,
            "external_id": None,
        }

    def get_status(self) -> dict[str, Any]:
        return {
            "status": "stubbed",
            "integration": str(self.connection_config.get("integration") or "internal"),
            "provider": str(self.connection_config.get("provider") or "internal_stub"),
            "message": str(self.connection_config.get("message") or "Internal stub is available."),
        }