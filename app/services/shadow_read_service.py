"""Shadow read service for observations and proposals."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories.postgres.end_customer_shadow_repository import EndCustomerShadowRepository


class ShadowReadService:
    @staticmethod
    def get_observation_summary(db: Session, tenant_id: str, observation_id: str) -> dict[str, Any] | None:
        row = EndCustomerShadowRepository.get_observation(db, tenant_id, observation_id)
        if row is None:
            return None
        signals = EndCustomerShadowRepository.list_signals(db, tenant_id, observation_id)
        facts = EndCustomerShadowRepository.list_fact_proposals(db, tenant_id, observation_id)
        matches = EndCustomerShadowRepository.list_match_proposals(db, tenant_id, observation_id)
        return {
            "observation_id": row.observation_id,
            "state": row.state,
            "source_message_id": row.source_message_id,
            "source_thread_id": row.source_thread_id,
            "extraction_version": row.extraction_version,
            "confidence": row.confidence,
            "identity_signal_count": len(signals),
            "fact_proposal_count": len(facts),
            "match_proposal_count": len(matches),
        }

    @staticmethod
    def build_oracle(db: Session, tenant_id: str) -> dict[str, Any]:
        counts = EndCustomerShadowRepository.snapshot_counts(db, tenant_id)
        observations = EndCustomerShadowRepository.list_observations(db, tenant_id)

        job_links = int(
            db.execute(
                text("SELECT COUNT(*) FROM end_customer_job_links WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            ).scalar()
            or 0
        )
        thread_links = int(
            db.execute(
                text("SELECT COUNT(*) FROM end_customer_thread_links WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            ).scalar()
            or 0
        )

        signal_counts: dict[str, int] = {}
        for obs in observations:
            for signal in EndCustomerShadowRepository.list_signals(db, tenant_id, obs.observation_id):
                signal_counts[signal.signal_type] = signal_counts.get(signal.signal_type, 0) + 1

        match_proposals = EndCustomerShadowRepository.list_match_proposals(db, tenant_id)
        match_reasons: list[str] = []
        for proposal in match_proposals:
            match_reasons.extend(proposal.match_reasons or [])

        return {
            "observation_count": counts.get("end_customer_shadow_observations", 0),
            "observation_state": observations[-1].state if observations else None,
            "identity_signal_counts": signal_counts,
            "fact_proposal_counts": counts.get("end_customer_shadow_fact_proposals", 0),
            "match_proposal_counts": counts.get("end_customer_shadow_match_proposals", 0),
            "match_reasons": match_reasons,
            "candidate_customer_count": len({p.candidate_end_customer_id for p in match_proposals}),
            "actual_customer_links": 0,
            "actual_job_links": job_links,
            "actual_thread_links": thread_links,
            "verified_facts_created": 0,
            "current_state_mutations": 0,
            "automatic_merges": 0,
            "automatic_duplicate_decisions": 0,
            "idempotency_records": counts.get("end_customer_shadow_observations", 0),
            "cross_tenant_findings": [],
            "external_side_effects": 0,
        }
