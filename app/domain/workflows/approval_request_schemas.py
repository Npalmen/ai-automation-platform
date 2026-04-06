from __future__ import annotations

from pydantic import BaseModel


class ApprovalDecisionRequest(BaseModel):
    actor: str = "api"
    channel: str = "api"
    note: str | None = None