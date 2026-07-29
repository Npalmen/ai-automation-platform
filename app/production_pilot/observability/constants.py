"""Schema versions and allowed ground-truth verdict enums."""

from __future__ import annotations

P1_DAILY_REPORT_SCHEMA_VERSION = "production-pilot.p1-daily-report.v1"
P1_OPERATIONAL_EVAL_SCHEMA_VERSION = "production-pilot.p1-operational-eval.v1"
P1_RUNTIME_READINESS_SCHEMA_VERSION = "production-pilot.p1-runtime-readiness.v1"
P1_QUERY_SCHEMA_VERSION = "production-pilot.observability-queries.v1"

CLASSIFICATION_VERDICTS = frozenset({"correct", "incorrect", "ambiguous"})
EXTRACTION_VERDICTS = frozenset({"acceptable", "corrected", "failed"})
ROUTING_VERDICTS = frozenset({"correct", "incorrect"})
MANUAL_REVIEW_VERDICTS = frozenset({"required", "not_required", "unclear"})
SHADOW_OBSERVATION_VERDICTS = frozenset({"acceptable", "incorrect", "incomplete"})
MATCH_PROPOSAL_VERDICTS = frozenset({"acceptable", "ambiguous", "incorrect", "not_applicable"})
INCIDENT_SEVERITIES = frozenset({"none", "minor", "major", "critical"})
BUSINESS_RISKS = frozenset({"low", "medium", "high", "critical"})

GO_FOR_P2_APPROVAL_GMAIL = "GO_FOR_P2_APPROVAL_GMAIL"
NO_GO_FOR_P2_APPROVAL_GMAIL = "NO_GO_FOR_P2_APPROVAL_GMAIL"
