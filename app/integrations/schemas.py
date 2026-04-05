from pydantic import BaseModel, Field
from typing import Dict, Any


class IntegrationActionRequest(BaseModel):
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)