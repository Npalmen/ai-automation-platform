"""Fake integration adapters for evaluation (no real external I/O)."""

from __future__ import annotations

from typing import Any

from app.evaluation.telemetry import get_telemetry
from app.integrations.base import BaseIntegrationAdapter
from app.integrations.enums import IntegrationType

EVAL_INTEGRATION_CONNECTION_CONFIG = {
    "access_token": "eval-harness-token",
    "api_url": "https://gmail.eval.invalid/v1",
    "user_id": "me",
    "credential_source": "eval_harness",
}


class EvalFakeAdapter(BaseIntegrationAdapter):
    """Records adapter calls without network access."""

    def __init__(self, integration_type: IntegrationType, connection_config: dict | None = None):
        super().__init__(connection_config=connection_config or {})
        self.integration_type = integration_type

    def execute_action(self, action: str, payload: dict) -> dict:
        get_telemetry().record_fake_adapter(action)
        return {
            "status": "success",
            "provider": "eval_fake",
            "integration": self.integration_type.value,
            "action": action,
            "payload": payload,
            "message": "Eval harness fake adapter — no external I/O.",
        }

    def get_status(self) -> dict:
        return {
            "status": "connected",
            "provider": "eval_fake",
            "integration": self.integration_type.value,
        }


def eval_get_integration_adapter(
    integration_type: IntegrationType,
    connection_config: dict | None = None,
) -> BaseIntegrationAdapter:
    """Harness hook: always fake; never call real external adapters."""
    return EvalFakeAdapter(integration_type, connection_config)


def eval_get_integration_connection_config(
    tenant_id: str,
    integration_type: IntegrationType,
    db: Any | None = None,
) -> dict[str, Any]:
    """Deterministic eval connection config — never reads platform env or DB."""
    _ = tenant_id, integration_type, db
    return dict(EVAL_INTEGRATION_CONNECTION_CONFIG)
