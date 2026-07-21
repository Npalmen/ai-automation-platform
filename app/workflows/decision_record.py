"""Decision trace domain types (Kapitel 2C)."""

from __future__ import annotations

from enum import Enum
from typing import Any

METADATA_MAX_BYTES = 2048

ALLOWED_METADATA_KEYS = frozenset({
    "approval_id",
    "resolution",
    "execution_id",
    "audit_event_id",
    "operator_actor",
    "operator_action",
    "action_operation_id",
    "action_fingerprint",
    "pipeline_run_id",
    "parent_pipeline_run_id",
    "integration_provider",
    "external_id",
    "adapter_status",
    "error_class",
    "prompt_name",
    "used_fallback",
    "duration_ms",
    "supersedes_decision_id",
    "reconciliation_required",
    "evaluation_run_id",
})


class DecisionRecordType(str, Enum):
    PIPELINE_RUN_STARTED = "pipeline_run_started"
    CLASSIFICATION = "classification"
    DECISIONING_RECOMMENDATION = "decisioning_recommendation"
    POLICY_AUTHORIZATION = "policy_authorization"
    ACTION_AUTHORIZATION = "action_authorization"
    EXECUTION_INTENT = "execution_intent"
    EXECUTION_OUTCOME = "execution_outcome"
    APPROVAL_RESOLUTION = "approval_resolution"
    ACTION_APPROVAL_RESOLUTION = "action_approval_resolution"
    DISPATCH_APPROVAL_RESOLUTION = "dispatch_approval_resolution"
    OPERATOR_RECOVERY = "operator_recovery"


class PipelineRunSource(str, Enum):
    INTAKE = "intake"
    APPROVAL_RESUME = "approval_resume"
    RETRY = "retry"
    REPLAY = "replay"
    RECLASSIFY = "reclassify"
    RE_EXTRACT = "re_extract"
    GMAIL_CONTINUATION = "gmail_continuation"


class ExecutionPhase(str, Enum):
    AUTHORIZATION = "authorization"
    INTENT = "intent"
    OUTCOME = "outcome"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"
    RECONCILIATION_REQUIRED = "reconciliation_required"


def validate_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    unknown = set(metadata.keys()) - ALLOWED_METADATA_KEYS
    if unknown:
        raise ValueError(f"DecisionRecord metadata contains disallowed keys: {sorted(unknown)}")
    import json

    encoded = json.dumps(metadata, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > METADATA_MAX_BYTES:
        raise ValueError("DecisionRecord metadata exceeds size limit")
    return metadata
