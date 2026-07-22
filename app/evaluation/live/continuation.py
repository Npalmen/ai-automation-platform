"""Gmail thread continuation rules for trusted live-eval jobs."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.evaluation.live.audit import emit_live_eval_audit
from app.evaluation.live.constants import RUN_STATUS_ACTIVE, TERMINAL_RUN_STATUSES
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.subject_parser import parse_subject_token
from app.evaluation.live.config import get_live_eval_config
from app.repositories.postgres.live_eval_repository import LiveEvalRunRepository


def _root_live_eval(input_data: dict | None) -> dict | None:
    if not isinstance(input_data, dict):
        return None
    raw = input_data.get("live_eval")
    if not isinstance(raw, dict) or not raw.get("trusted"):
        return None
    return raw


def enforce_live_eval_thread_continuation(
    db: Session,
    *,
    root_input_data: dict,
    subject: str,
    tenant_id: str,
) -> dict | None:
    """Reuse immutable root snapshot or reject manipulated continuation tokens."""
    root_snapshot = _root_live_eval(root_input_data)
    parsed = parse_subject_token(subject)
    config = get_live_eval_config()

    if root_snapshot is not None:
        if parsed is not None:
            mismatch = (
                parsed.evaluation_run_id != root_snapshot["evaluation_run_id"]
                or parsed.scenario_id != root_snapshot["scenario_id"]
                or parsed.attempt_id != root_snapshot["attempt_id"]
            )
            if mismatch:
                emit_live_eval_audit(
                    db,
                    tenant_id=tenant_id,
                    action="safety_rejected",
                    status="blocked",
                    details={
                        "reason": "continuation_token_mismatch",
                        "evaluation_run_id": root_snapshot["evaluation_run_id"],
                    },
                )
                raise LiveEvalSafetyError("continuation token mismatch")

        row = LiveEvalRunRepository.get_run(
            db,
            root_snapshot["evaluation_run_id"],
            tenant_id=tenant_id,
        )
        if row is None:
            raise LiveEvalSafetyError("live_eval run not found for continuation")
        now = datetime.now(timezone.utc)
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if row.status in TERMINAL_RUN_STATUSES or expires_at < now:
            emit_live_eval_audit(
                db,
                tenant_id=tenant_id,
                action="safety_rejected",
                status="blocked",
                details={
                    "reason": "continuation_run_not_active",
                    "evaluation_run_id": row.evaluation_run_id,
                    "status": row.status,
                },
            )
            raise LiveEvalSafetyError("live_eval run is not active")
        if row.status != RUN_STATUS_ACTIVE:
            raise LiveEvalSafetyError("live_eval run is not active")
        return dict(root_snapshot)

    if parsed is not None and tenant_id in config.tenant_ids:
        emit_live_eval_audit(
            db,
            tenant_id=tenant_id,
            action="safety_rejected",
            status="blocked",
            details={"reason": "eval_token_on_non_eval_thread"},
        )
        raise LiveEvalSafetyError("cannot start live eval via thread reply")

    return None
