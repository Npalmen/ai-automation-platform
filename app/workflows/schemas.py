from pydantic import BaseModel, Field
from typing import Dict, Any


class CreateJobRequest(BaseModel):
    input_data: Dict[str, Any] = Field(default_factory=dict)