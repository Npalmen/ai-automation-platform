# app/integrations/base.py

from abc import ABC, abstractmethod
from typing import Any


class BaseIntegrationAdapter(ABC):
    def __init__(self, connection_config: dict[str, Any] | None = None):
        self.connection_config = connection_config or {}

    @abstractmethod
    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_status(self) -> dict[str, Any]:
        raise NotImplementedError