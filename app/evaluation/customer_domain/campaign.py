"""Campaign metadata and cleanup registry for TBF stateful evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.evaluation.customer_domain.db import cleanup_eval_tenants
from app.evaluation.customer_domain.guards import EVAL_TENANT_PREFIX
from app.evaluation.customer_domain.semantic_hash import semantic_hash


@dataclass
class CampaignRun:
    campaign_run_id: str = field(default_factory=lambda: str(uuid4()))
    registered_tenants: list[str] = field(default_factory=list)
    scenario_execution_ids: list[str] = field(default_factory=list)
    pre_run_snapshot: dict[str, Any] = field(default_factory=dict)
    cross_tenant_findings: list[str] = field(default_factory=list)

    def register_tenant(self, tenant_id: str, scenario_id: str, attempt: int = 1) -> None:
        if tenant_id not in self.registered_tenants:
            self.registered_tenants.append(tenant_id)
        self.scenario_execution_ids.append(f"{scenario_id}/{attempt}")

    def stable_idempotency_key(self, scenario_id: str, step: str) -> str:
        digest = sha256(f"{self.campaign_run_id}:{scenario_id}:{step}".encode()).hexdigest()[:16]
        return f"idem:{scenario_id}:{step}:{digest}"

    def source_event_id(self, scenario_id: str, step: str) -> str:
        return f"src:{scenario_id}:{step}"


def tenant_id_for_scenario(campaign: CampaignRun, scenario_id: str) -> str:
    short = campaign.campaign_run_id.replace("-", "")[:8]
    return f"{EVAL_TENANT_PREFIX}{short}_{scenario_id.lower()}"


def snapshot_campaign_state(engine: Engine, tenants: list[str]) -> dict[str, Any]:
    counts: dict[str, dict[str, int]] = {}
    with engine.connect() as conn:
        for tenant_id in tenants:
            counts[tenant_id] = {}
            for table in (
                "end_customer_shadow_match_proposals",
                "end_customer_shadow_fact_proposals",
                "end_customer_shadow_identity_signals",
                "end_customer_shadow_observations",
                "end_customers",
                "end_customer_contacts",
                "end_customer_source_facts",
                "end_customer_idempotency_records",
                "end_customer_timeline_events",
                "end_customer_thread_links",
                "end_customer_job_links",
                "end_customer_duplicate_candidates",
            ):
                counts[tenant_id][table] = int(
                    conn.execute(
                        text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tenant_id"),
                        {"tenant_id": tenant_id},
                    ).scalar()
                    or 0
                )
    return {"tenant_counts": counts}


def verify_campaign_cleanup(engine: Engine, campaign: CampaignRun) -> dict[str, Any]:
    cleanup_eval_tenants(engine)
    remaining: dict[str, int] = {}
    with engine.connect() as conn:
        for tenant_id in campaign.registered_tenants:
            total = 0
            for table in (
                "end_customer_shadow_match_proposals",
                "end_customer_shadow_fact_proposals",
                "end_customer_shadow_identity_signals",
                "end_customer_shadow_observations",
                "end_customers",
                "end_customer_contacts",
                "end_customer_source_facts",
                "end_customer_idempotency_records",
                "end_customer_timeline_events",
                "end_customer_thread_links",
                "end_customer_job_links",
                "end_customer_duplicate_candidates",
            ):
                total += int(
                    conn.execute(
                        text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tenant_id"),
                        {"tenant_id": tenant_id},
                    ).scalar()
                    or 0
                )
            remaining[tenant_id] = total
    post_hash = semantic_hash({"remaining_rows": remaining})
    pre_hash = campaign.pre_run_snapshot.get("normalized_hash", "")
    return {
        "cleanup_status": "restored" if all(v == 0 for v in remaining.values()) else "failed",
        "remaining_rows": remaining,
        "pre_run_hash": pre_hash,
        "post_cleanup_hash": post_hash,
        "hash_match": pre_hash == post_hash or all(v == 0 for v in remaining.values()),
    }


def build_campaign_oracle(
    *,
    campaign: CampaignRun,
    scenario_results: list[dict[str, Any]],
    cleanup_result: dict[str, Any],
    cross_tenant_findings: list[str] | None = None,
) -> dict[str, Any]:
    findings = cross_tenant_findings if cross_tenant_findings is not None else campaign.cross_tenant_findings
    passed = all(item.get("result") == "PASS" for item in scenario_results)
    return {
        "campaign_run_id": campaign.campaign_run_id,
        "scenario_execution_ids": list(campaign.scenario_execution_ids),
        "registered_tenants": list(campaign.registered_tenants),
        "families_executed": [item.get("scenario_id") for item in scenario_results],
        "families_skipped": [],
        "overall_status": "passed" if passed else "failed",
        "cross_tenant_findings": findings,
        "cleanup_status": cleanup_result.get("cleanup_status"),
        "pre_run_hash": cleanup_result.get("pre_run_hash"),
        "post_cleanup_hash": cleanup_result.get("post_cleanup_hash"),
    }
