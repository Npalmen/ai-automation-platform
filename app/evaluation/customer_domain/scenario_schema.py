"""Scenario schema for customer-domain stateful evaluation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCENARIO_SCHEMA_VERSION = "customer_domain_stateful_scenario_v1"
ALLOWED_PHASES = frozenset({"arrange", "act", "assert"})
ALLOWED_ACTIONS = frozenset(
    {
        "create_private_customer",
        "create_company_customer",
        "add_fact",
        "verify_fact",
        "create_identity",
        "create_job_link",
        "duplicate_decision",
        "update_customer",
        "read_customer_card",
        "assess_customer_match",
        "arrange_contact",
        "arrange_relationship",
        "arrange_thread_link",
        "arrange_duplicate_candidate",
        "arrange_job",
        "assert_db_counts",
        "assert_current_state",
    }
)


class ScenarioStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_id: str = Field(min_length=1)
    phase: Literal["arrange", "act", "assert"]
    action: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    expected_outcome: str | None = None
    expected_invariants: list[str] = Field(default_factory=list)


class StatefulScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default=SCENARIO_SCHEMA_VERSION)
    scenario_id: str = Field(min_length=1)
    family: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    description: str = ""
    steps: list[ScenarioStep] = Field(default_factory=list)
    expected_final_invariants: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_steps(self) -> StatefulScenario:
        if self.schema_version != SCENARIO_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version: {self.schema_version}")
        seen_steps: set[str] = set()
        for step in self.steps:
            if step.step_id in seen_steps:
                raise ValueError(f"duplicate step_id: {step.step_id}")
            seen_steps.add(step.step_id)
            if step.phase not in ALLOWED_PHASES:
                raise ValueError(f"invalid phase: {step.phase}")
        return self
