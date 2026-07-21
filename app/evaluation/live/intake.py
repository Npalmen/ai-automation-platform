"""Trusted live-eval intake resolution from Gmail messages."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.evaluation.live.audit import emit_live_eval_audit
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.registry import trusted_snapshot_from_row
from app.evaluation.live.safety import require_tenant_allowed, validate_run_row_for_intake
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.evaluation.live.subject_parser import parse_subject_token
from app.evaluation.live.config import get_live_eval_config
from app.repositories.postgres.live_eval_repository import LiveEvalRunRepository


def resolve_trusted_live_eval_from_message(
    db: Session,
    *,
    tenant_id: str,
    subject: str,
    sender_email: str,
    recipient_email: str,
    query: str,
) -> TrustedLiveEvalSnapshot | None:
    """Validate correlation and return immutable trusted snapshot (no activation)."""
    parsed = parse_subject_token(subject)
    if parsed is None:
        return None

    config = get_live_eval_config()
    if tenant_id not in config.tenant_ids:
        return None

    row = LiveEvalRunRepository.get_run(
        db, parsed.evaluation_run_id, tenant_id=tenant_id
    )
    if row is None:
        emit_live_eval_audit(
            db,
            tenant_id=tenant_id,
            action="safety_rejected",
            status="blocked",
            details={
                "reason": "unknown_evaluation_run_id",
                "evaluation_run_id": parsed.evaluation_run_id,
            },
        )
        raise LiveEvalSafetyError("unknown evaluation_run_id")

    try:
        require_tenant_allowed(tenant_id, config)
        validate_run_row_for_intake(
            row,
            tenant_id=tenant_id,
            scenario_id=parsed.scenario_id,
            attempt_id=parsed.attempt_id,
            sender_email=sender_email,
            recipient_email=recipient_email,
            query=query,
            config=config,
            require_registered=True,
        )
    except LiveEvalSafetyError as exc:
        emit_live_eval_audit(
            db,
            tenant_id=tenant_id,
            action="safety_rejected",
            status="blocked",
            details={
                "evaluation_run_id": parsed.evaluation_run_id,
                "reason": str(exc),
            },
        )
        raise

    return trusted_snapshot_from_row(row)
