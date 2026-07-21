"""Registry-backed validation for trusted live-eval runtime context."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.evaluation.live.constants import RUN_STATUS_ACTIVE
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.repositories.postgres.live_eval_repository import LiveEvalRunRepository


def validate_trusted_live_eval_context(
    db: Session,
    *,
    job,
    snapshot: TrustedLiveEvalSnapshot | None,
    require_active: bool = False,
) -> TrustedLiveEvalSnapshot | None:
    if snapshot is None or not snapshot.trusted:
        return None

    job_tenant_id = getattr(job, "tenant_id", None) if job is not None else None
    if job_tenant_id is not None and job_tenant_id != snapshot.tenant_id:
        raise LiveEvalSafetyError("live_eval tenant mismatch")

    row = LiveEvalRunRepository.get_run(
        db,
        snapshot.evaluation_run_id,
        tenant_id=snapshot.tenant_id,
    )
    if row is None:
        raise LiveEvalSafetyError("live_eval run not found in registry")

    if row.config_hash != snapshot.config_hash:
        raise LiveEvalSafetyError("live_eval config_hash mismatch")
    if row.ai_mode != snapshot.ai_mode:
        raise LiveEvalSafetyError("live_eval ai_mode mismatch")
    if row.fixture_bundle_id != snapshot.fixture_bundle_id:
        raise LiveEvalSafetyError("live_eval fixture_bundle_id mismatch")
    if row.scenario_id != snapshot.scenario_id:
        raise LiveEvalSafetyError("live_eval scenario_id mismatch")
    if row.attempt_id != snapshot.attempt_id:
        raise LiveEvalSafetyError("live_eval attempt_id mismatch")

    if require_active:
        if row.status != RUN_STATUS_ACTIVE:
            raise LiveEvalSafetyError("live_eval run is not active")
        now = datetime.now(timezone.utc)
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= now:
            raise LiveEvalSafetyError("live_eval run has expired")

    return snapshot
