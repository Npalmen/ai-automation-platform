"""API schemas for production pilot ground-truth reviews."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ClassificationVerdict = Literal["correct", "incorrect", "ambiguous"]
ExtractionVerdict = Literal["acceptable", "corrected", "failed"]
RoutingVerdict = Literal["correct", "incorrect"]
ManualReviewVerdict = Literal["required", "not_required", "unclear"]
ShadowObservationVerdict = Literal["acceptable", "incorrect", "incomplete"]
MatchProposalVerdict = Literal["acceptable", "ambiguous", "incorrect", "not_applicable"]
IncidentSeverity = Literal["none", "minor", "major", "critical"]
BusinessRisk = Literal["low", "medium", "high", "critical"]


class PilotMessageReviewRequest(BaseModel):
    provider_message_ref_hash: str = Field(min_length=16, max_length=64)
    job_id: str
    intake_event_id: str | None = None
    classification_verdict: ClassificationVerdict
    extraction_verdict: ExtractionVerdict
    routing_verdict: RoutingVerdict
    manual_review_verdict: ManualReviewVerdict
    shadow_observation_verdict: ShadowObservationVerdict
    match_proposal_verdict: MatchProposalVerdict
    incident_severity: IncidentSeverity = "none"
    error_category: str | None = None
    business_risk: BusinessRisk | None = None
    blocks_next_phase: bool = False
    review_version: int = 1


class PilotMessageReviewResponse(BaseModel):
    id: str
    tenant_id: str
    pilot_phase: str
    provider_message_ref_hash: str
    intake_event_id: str | None
    job_id: str
    reviewed_by: str
    reviewed_at: datetime
    classification_verdict: str
    extraction_verdict: str
    routing_verdict: str
    manual_review_verdict: str
    shadow_observation_verdict: str
    match_proposal_verdict: str
    incident_severity: str
    error_category: str | None
    business_risk: str | None
    blocks_next_phase: bool
    review_version: int
