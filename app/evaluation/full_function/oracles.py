"""Structured oracles for full-function scenarios."""

from __future__ import annotations

import subprocess
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.full_function.scenarios._common import ScenarioRunResult


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def build_scenario_oracle(
    ctx,
    db: Session,
    result: ScenarioRunResult,
    *,
    execution_mode: str = "postgres",
) -> dict[str, Any]:
    payload = result.semantic_payload
    return {
        "scenario_id": result.scenario_id,
        "capability_ids": payload.get("capability_ids", []),
        "execution_mode": execution_mode,
        "tenant_id_hash": payload.get("tenant_id_hash", ""),
        "runtime_sha": _git_sha(),
        "input_count": payload.get("input_count", 0),
        "job_count": payload.get("job_count", 0),
        "classification": payload.get("classification"),
        "extracted_entities_hash": payload.get("extracted_entities_hash"),
        "decision": payload.get("decision"),
        "authorization": payload.get("authorization"),
        "approval_count": payload.get("approval_count", 0),
        "operator_action_count": payload.get("operator_action_count", 0),
        "manual_review_count": payload.get("manual_review_count", 0),
        "execution_intent_count": payload.get("execution_intent_count", 0),
        "execution_outcome_count": payload.get("execution_outcome_count", 0),
        "adapter_invocations": payload.get("adapter_invocations", 0),
        "provider_accepted": payload.get("provider_accepted", False),
        "recipient_verified": payload.get("recipient_verified", False),
        "external_writes_by_type": payload.get("external_writes_by_type", {}),
        "unauthorized_writes": payload.get("unauthorized_writes", 0),
        "idempotency_result": payload.get("idempotency_result"),
        "customer_state_mutations": payload.get("customer_state_mutations", 0),
        "shadow_observations": payload.get("shadow_observations", 0),
        "verified_facts_created": payload.get("verified_facts_created", 0),
        "automatic_links": payload.get("automatic_links", 0),
        "automatic_merges": payload.get("automatic_merges", 0),
        "audit_event_types": payload.get("audit_event_types", []),
        "cross_tenant_findings": payload.get("cross_tenant_findings", []),
        "redaction_status": payload.get("redaction_status", "clean"),
        "cleanup_status": payload.get("cleanup_status", "pending"),
        "semantic_hash": result.to_report().get("semantic_result_hash"),
        "status": result.result,
    }


def attach_oracle(ctx, db: Session, result: ScenarioRunResult, **kwargs: Any) -> ScenarioRunResult:
    result.oracle = build_scenario_oracle(ctx, db, result, **kwargs)
    return result
