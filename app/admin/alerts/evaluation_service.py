"""Alert evaluation engine (Kapitel 10)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.admin.alerts.audit_events import (
    ALERT_EVALUATION_COMPLETED,
    ALERT_EVALUATION_EVALUATOR_FAILED,
    ALERT_EVALUATION_STARTED,
    write_operator_alert_audit,
)
from app.admin.alerts.evaluation_lock import alert_evaluation_lock
from app.admin.alerts.evaluators import run_evaluator
from app.admin.alerts.lifecycle import apply_candidate, auto_resolve_missing
from app.admin.alerts.models import AlertEvaluationRunRecord
from app.admin.alerts.registry import EVALUATOR_VERSION, enabled_definitions
from app.admin.alerts.repository import AlertRepository
from app.core.settings import Settings
from app.repositories.postgres.session import engine

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def run_alert_evaluation(
    db: Session,
    *,
    settings: Settings,
    dry_run: bool = False,
    scope: str = "platform",
    max_slice: int = 3,
    operator_id: str | None = None,
) -> dict[str, Any]:
    with alert_evaluation_lock(engine) as acquired:
        if not acquired:
            return {
                "run_id": None,
                "status": "skipped_concurrent",
                "dry_run": dry_run,
                "created_count": 0,
                "updated_count": 0,
                "resolved_count": 0,
                "error_count": 0,
                "evaluator_results": [],
                "started_at": _utcnow(),
                "completed_at": _utcnow(),
            }

        run_id = str(uuid4())
        started = _utcnow()
        run = AlertEvaluationRunRecord(
            run_id=run_id,
            started_at=started,
            status="running",
            scope=scope,
            dry_run=dry_run,
            evaluator_version=EVALUATOR_VERSION,
            triggered_by_operator_id=operator_id,
        )
        if not dry_run:
            AlertRepository.add_evaluation_run(db, run)
            write_operator_alert_audit(
                db,
                action=ALERT_EVALUATION_STARTED,
                details={"run_id": run_id, "scope": scope},
            )
            db.commit()
        else:
            db.flush()

        created = updated = resolved = errors = 0
        evaluator_results: list[dict[str, Any]] = []

        for definition in enabled_definitions(max_slice=max_slice):
            if definition.slice > max_slice:
                continue
            try:
                candidates = run_evaluator(db, definition, settings)
                active_keys = {c.deduplication_key for c in candidates}
                type_created = type_updated = 0

                for candidate in candidates:
                    action, _ = apply_candidate(
                        db, candidate, definition=definition, dry_run=dry_run
                    )
                    if action == "created":
                        type_created += 1
                    elif action in ("updated", "reopened"):
                        type_updated += 1

                type_resolved = auto_resolve_missing(
                    db,
                    alert_type=definition.alert_type,
                    active_keys=active_keys,
                    dry_run=dry_run,
                )

                if not dry_run:
                    db.commit()

                created += type_created
                updated += type_updated
                resolved += type_resolved
                evaluator_results.append(
                    {
                        "alert_type": definition.alert_type,
                        "outcome": "ok",
                        "candidates": len(candidates),
                        "created": type_created,
                        "updated": type_updated,
                        "resolved": type_resolved,
                    }
                )
            except Exception as exc:
                logger.exception("Evaluator %s failed", definition.alert_type)
                db.rollback()
                errors += 1
                if not dry_run:
                    write_operator_alert_audit(
                        db,
                        action=ALERT_EVALUATION_EVALUATOR_FAILED,
                        details={
                            "run_id": run_id,
                            "evaluator": definition.alert_type,
                            "error_code": "evaluator_exception",
                        },
                    )
                    db.commit()
                evaluator_results.append(
                    {
                        "alert_type": definition.alert_type,
                        "outcome": "error",
                        "error_code": "evaluator_exception",
                    }
                )

        completed = _utcnow()
        status = "completed" if errors == 0 else "partial"
        if not dry_run:
            run = db.query(AlertEvaluationRunRecord).filter_by(run_id=run_id).first()
            if run:
                run.completed_at = completed
                run.status = status
                run.created_count = created
                run.updated_count = updated
                run.resolved_count = resolved
                run.error_count = errors
                run.evaluator_results_json = evaluator_results
                if errors:
                    run.safe_error_summary = f"{errors} evaluator(s) failed"
                write_operator_alert_audit(
                    db,
                    action=ALERT_EVALUATION_COMPLETED,
                    details={
                        "run_id": run_id,
                        "status": status,
                        **({"error_code": f"errors:{errors}"} if errors else {}),
                    },
                )
                db.commit()

        result = {
            "run_id": run_id,
            "status": status,
            "dry_run": dry_run,
            "created_count": created,
            "updated_count": updated,
            "resolved_count": resolved,
            "error_count": errors,
            "evaluator_results": evaluator_results,
            "started_at": started,
            "completed_at": completed,
        }

        if not dry_run:
            try:
                from app.admin.alerts.notification_service import enqueue_alert_notifications

                enqueue_alert_notifications(db, settings=settings)
                db.commit()
            except Exception:
                logger.exception("Notification intent enqueue failed")
                db.rollback()

        return result
