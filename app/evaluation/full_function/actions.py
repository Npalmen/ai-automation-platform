"""Evaluation context and production-path helpers for Testbot G."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.evaluation.full_function.campaign import CampaignRun


@dataclass
class EvalContext:
    engine: Engine
    tenant_id: str
    campaign: CampaignRun | None = None
    scenario_id: str | None = None
    arrangements: list[str] = field(default_factory=list)
    production_actions: list[str] = field(default_factory=list)

    def session(self) -> Session:
        return sessionmaker(bind=self.engine)()

    def tenant_hash(self) -> str:
        return sha256(self.tenant_id.encode()).hexdigest()[:16]

    def step_idempotency_key(self, step: str) -> str:
        if self.campaign is not None and self.scenario_id:
            return self.campaign.stable_idempotency_key(self.scenario_id, step)
        return str(uuid4())

    def source_event_id(self, step: str) -> str:
        if self.campaign is not None and self.scenario_id:
            return self.campaign.source_event_id(self.scenario_id, step)
        return f"src:{step}"
