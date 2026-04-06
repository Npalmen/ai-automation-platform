from typing import Literal

from pydantic import BaseModel, Field


ApprovalChannel = Literal["dashboard", "email", "slack", "teams"]


class ApprovalDecisionRequest(BaseModel):
    actor: str = Field(min_length=1, max_length=255)
    channel: ApprovalChannel = "dashboard"
    note: str | None = Field(default=None, max_length=4000)