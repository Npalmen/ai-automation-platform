from abc import ABC, abstractmethod
from typing import Any, Dict

from app.integrations.config_models import IntegrationConnectionConfig


class IntegrationAdapter(ABC):
    def __init__(self, connection_config: IntegrationConnectionConfig | None = None):
        self.connection_config = connection_config

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        pass

    @abstractmethod
    def execute_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        pass