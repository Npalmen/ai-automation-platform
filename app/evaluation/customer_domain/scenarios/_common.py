"""Shared scenario result helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.customer_domain.assertions import snapshot_audit_counts, snapshot_db_counts
from app.evaluation.customer_domain.semantic_hash import semantic_hash


@dataclass
class ScenarioRunResult:
    scenario_id: str
    family: str
    tenant_id: str
    result: str = "PASS"
    failures: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    arrangements: list[str] = field(default_factory=list)
    production_actions: list[str] = field(default_factory=list)
    database_counts: dict[str, int] = field(default_factory=dict)
    audit_counts: int = 0
    semantic_payload: dict[str, Any] = field(default_factory=dict)
    oracle: dict[str, Any] = field(default_factory=dict)

    def fail(self, message: str) -> None:
        self.failures.append(message)
        self.result = "FAIL"

    def to_report(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "family": self.family,
            "tenant_id": self.tenant_id,
            "steps": self.steps,
            "expected_invariants": [],
            "actual_invariants": list(self.semantic_payload.keys()),
            "database_counts": self.database_counts,
            "audit_counts": self.audit_counts,
            "semantic_result_hash": semantic_hash(self.semantic_payload),
            "oracle": self.oracle,
            "result": self.result,
            "failures": self.failures,
            "arrangements": self.arrangements,
            "production_actions": self.production_actions,
        }


def finalize_result(ctx, db, result: ScenarioRunResult) -> ScenarioRunResult:
    result.arrangements = list(ctx.arrangements)
    result.production_actions = list(ctx.production_actions)
    result.database_counts = snapshot_db_counts(db, ctx.tenant_id)
    result.audit_counts = snapshot_audit_counts(ctx.engine, ctx.tenant_id)
    return result
