"""Alert evaluators (Kapitel 10)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.admin.alerts.lifecycle import AlertCandidate
from app.admin.alerts.registry import AlertDefinition
from app.admin.alerts.signal_sources import (
    REPEATED_FAILURE_THRESHOLD,
    collect_failed_job_signals,
    collect_manual_review_stale_signals,
    collect_stale_approval_signals,
    collect_stuck_job_signals,
    count_recent_failed_jobs,
    fingerprint_payload,
    iter_active_tenants,
    scheduler_expected_state,
)
from app.admin.alerts.system_signal_status import (
    allows_auto_alert,
    normalize_backup_status,
    severity_for_system_status,
)
from app.core.settings import Settings
from app.domain.integrations.models import IntegrationEvent
from app.health.integration_health import get_integration_health
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

logger = logging.getLogger(__name__)

_FAILED_JOBS_WINDOW_H = 48
_DISPATCH_WINDOW_H = 48


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _candidate_from_approval(sig, definition: AlertDefinition) -> AlertCandidate:
    dedup = f"tenant:{sig.tenant_id}:approval:{sig.approval_id}:stale"
    fp = fingerprint_payload({"approval_id": sig.approval_id, "age": sig.age_hours})
    return AlertCandidate(
        alert_type=definition.alert_type,
        deduplication_key=dedup,
        scope_type=definition.scope_type,
        tenant_id=sig.tenant_id,
        related_job_id=sig.job_id,
        integration_key=None,
        severity=definition.default_severity,
        title=f"Godkännande väntar ({sig.age_hours} h)",
        summary=f"Approval {sig.approval_id[:8]} väntar på åtgärd.",
        safe_details={
            "source_type": "approval",
            "source_id": sig.source_id,
            "age_hours": sig.age_hours,
            "runbook_ref": definition.runbook_ref,
            "recommended_action": "Granska och godkänn eller avvisa.",
            "approval_kind": sig.kind,
        },
        source_class="intern_db_detected",
        current_fingerprint=fp,
    )


def _candidate_from_stuck(sig, definition: AlertDefinition) -> AlertCandidate:
    dedup = f"tenant:{sig.tenant_id}:job:{sig.job_id}:stuck"
    fp = fingerprint_payload({"job_id": sig.job_id, "status": sig.status})
    return AlertCandidate(
        alert_type=definition.alert_type,
        deduplication_key=dedup,
        scope_type=definition.scope_type,
        tenant_id=sig.tenant_id,
        related_job_id=sig.job_id,
        integration_key=None,
        severity=definition.default_severity,
        title=f"Jobb fastnat ({sig.job_type})",
        summary=f"Jobb {sig.job_id[:8]} i {sig.status} i {sig.age_hours} timmar.",
        safe_details={
            "source_type": "job",
            "source_id": sig.source_id,
            "age_hours": sig.age_hours,
            "runbook_ref": definition.runbook_ref,
            "recommended_action": "Granska jobb och kör recovery om lämpligt.",
            "job_type": sig.job_type,
        },
        source_class="intern_db_detected",
        current_fingerprint=fp,
    )


def evaluate_job_approval_stale(db: Session, definition: AlertDefinition) -> list[AlertCandidate]:
    out: list[AlertCandidate] = []
    for tenant_id, tenant_name in iter_active_tenants(db):
        for sig in collect_stale_approval_signals(db, tenant_id=tenant_id, tenant_name=tenant_name):
            out.append(_candidate_from_approval(sig, definition))
    return out


def evaluate_job_stuck_processing(db: Session, definition: AlertDefinition) -> list[AlertCandidate]:
    out: list[AlertCandidate] = []
    for tenant_id, tenant_name in iter_active_tenants(db):
        for sig in collect_stuck_job_signals(db, tenant_id=tenant_id, tenant_name=tenant_name):
            out.append(_candidate_from_stuck(sig, definition))
    return out


def evaluate_job_failed_recent(db: Session, definition: AlertDefinition) -> list[AlertCandidate]:
    out: list[AlertCandidate] = []
    for tenant_id, tenant_name in iter_active_tenants(db):
        for sig in collect_failed_job_signals(db, tenant_id=tenant_id, tenant_name=tenant_name):
            dedup = f"tenant:{sig.tenant_id}:job:{sig.job_id}:failed"
            fp = fingerprint_payload({"job_id": sig.job_id})
            out.append(
                AlertCandidate(
                    alert_type=definition.alert_type,
                    deduplication_key=dedup,
                    scope_type=definition.scope_type,
                    tenant_id=sig.tenant_id,
                    related_job_id=sig.job_id,
                    integration_key=None,
                    severity=definition.default_severity,
                    title=f"Misslyckat jobb ({sig.job_type})",
                    summary=sig.error_summary,
                    safe_details={
                        "source_type": "job",
                        "source_id": sig.source_id,
                        "runbook_ref": definition.runbook_ref,
                        "recommended_action": "Granska jobbdetalj.",
                    },
                    source_class="intern_db_detected",
                    current_fingerprint=fp,
                )
            )
    return out


def evaluate_job_manual_review_stale(db: Session, definition: AlertDefinition) -> list[AlertCandidate]:
    out: list[AlertCandidate] = []
    for tenant_id, tenant_name in iter_active_tenants(db):
        for sig in collect_manual_review_stale_signals(db, tenant_id=tenant_id, tenant_name=tenant_name):
            dedup = f"tenant:{sig.tenant_id}:job:{sig.job_id}:manual_review_stale"
            fp = fingerprint_payload({"job_id": sig.job_id})
            out.append(
                AlertCandidate(
                    alert_type=definition.alert_type,
                    deduplication_key=dedup,
                    scope_type=definition.scope_type,
                    tenant_id=sig.tenant_id,
                    related_job_id=sig.job_id,
                    integration_key=None,
                    severity=definition.default_severity,
                    title="Manuell granskning väntar",
                    summary=f"Jobb {sig.job_id[:8]} väntar i {sig.age_hours} timmar.",
                    safe_details={
                        "source_type": "job",
                        "source_id": sig.source_id,
                        "age_hours": sig.age_hours,
                        "runbook_ref": definition.runbook_ref,
                        "recommended_action": "Lös manual review.",
                    },
                    source_class="intern_db_detected",
                    current_fingerprint=fp,
                )
            )
    return out


def evaluate_job_repeated_failures(db: Session, definition: AlertDefinition) -> list[AlertCandidate]:
    out: list[AlertCandidate] = []
    for tenant_id, tenant_name in iter_active_tenants(db):
        count = count_recent_failed_jobs(db, tenant_id)
        if count < REPEATED_FAILURE_THRESHOLD:
            continue
        dedup = f"tenant:{tenant_id}:workflow:repeated_failure"
        fp = fingerprint_payload({"count": count})
        out.append(
            AlertCandidate(
                alert_type=definition.alert_type,
                deduplication_key=dedup,
                scope_type=definition.scope_type,
                tenant_id=tenant_id,
                related_job_id=None,
                integration_key=None,
                severity=definition.default_severity,
                title=f"Upprepade jobbfel ({count})",
                summary=f"{count} misslyckade jobb för {tenant_name} inom {_FAILED_JOBS_WINDOW_H}h.",
                safe_details={
                    "source_type": "tenant",
                    "source_id": tenant_id,
                    "failed_count": count,
                    "runbook_ref": definition.runbook_ref,
                    "recommended_action": "Undersök mönster i misslyckade jobb.",
                },
                source_class="intern_db_detected",
                current_fingerprint=fp,
            )
        )
    return out


def evaluate_integration_health_critical(
    db: Session, definition: AlertDefinition, settings: Settings
) -> list[AlertCandidate]:
    out: list[AlertCandidate] = []
    for tenant_id, tenant_name in iter_active_tenants(db):
        try:
            health = get_integration_health(db, tenant_id, settings)
        except Exception:
            continue
        for system, block in (health.get("systems") or {}).items():
            if block.get("status") != "error":
                continue
            dedup = f"tenant:{tenant_id}:integration:{system}:health_error"
            fp = fingerprint_payload({"system": system, "status": "error"})
            out.append(
                AlertCandidate(
                    alert_type=definition.alert_type,
                    deduplication_key=dedup,
                    scope_type=definition.scope_type,
                    tenant_id=tenant_id,
                    related_job_id=None,
                    integration_key=system,
                    severity=definition.default_severity,
                    title=f"Integration {system} i fel",
                    summary=block.get("recommended_action") or f"{system} health error.",
                    safe_details={
                        "source_type": "integration_health",
                        "source_id": f"integration:{system}",
                        "runbook_ref": definition.runbook_ref,
                        "recommended_action": block.get("recommended_action"),
                    },
                    source_class="intern_db_detected",
                    current_fingerprint=fp,
                )
            )
    return out


def evaluate_integration_oauth_failure_recent(
    db: Session, definition: AlertDefinition
) -> list[AlertCandidate]:
    out: list[AlertCandidate] = []
    cutoff = _utcnow() - timedelta(hours=24)
    for tenant_id, tenant_name in iter_active_tenants(db):
        try:
            events = (
                db.query(AuditEventRecord)
                .filter(
                    AuditEventRecord.tenant_id == tenant_id,
                    AuditEventRecord.category.in_(("oauth", "inbox_sync")),
                    AuditEventRecord.status == "failed",
                    AuditEventRecord.created_at >= cutoff,
                )
                .limit(1)
                .all()
            )
        except Exception:
            continue
        if not events:
            continue
        dedup = f"tenant:{tenant_id}:integration:gmail:oauth_failure"
        fp = fingerprint_payload({"tenant": tenant_id})
        out.append(
            AlertCandidate(
                alert_type=definition.alert_type,
                deduplication_key=dedup,
                scope_type=definition.scope_type,
                tenant_id=tenant_id,
                related_job_id=None,
                integration_key="gmail",
                severity=definition.default_severity,
                title="OAuth/inbox-fel nyligen",
                summary="Misslyckad OAuth eller inbox-sync i audit.",
                safe_details={
                    "source_type": "audit_event",
                    "source_id": f"oauth:{tenant_id}",
                    "runbook_ref": definition.runbook_ref,
                    "recommended_action": "Kontrollera Gmail-token och OAuth.",
                },
                source_class="intern_db_detected",
                current_fingerprint=fp,
            )
        )
    return out


def evaluate_integration_dispatch_failures_repeated(
    db: Session, definition: AlertDefinition
) -> list[AlertCandidate]:
    out: list[AlertCandidate] = []
    cutoff = _utcnow() - timedelta(hours=_DISPATCH_WINDOW_H)
    for tenant_id, tenant_name in iter_active_tenants(db):
        try:
            count = (
                db.query(IntegrationEvent)
                .filter(
                    IntegrationEvent.tenant_id == tenant_id,
                    IntegrationEvent.status == "failed",
                    IntegrationEvent.created_at >= cutoff,
                )
                .count()
            )
        except Exception:
            continue
        if count < REPEATED_FAILURE_THRESHOLD:
            continue
        dedup = f"tenant:{tenant_id}:integration:dispatch_repeated"
        fp = fingerprint_payload({"count": count})
        out.append(
            AlertCandidate(
                alert_type=definition.alert_type,
                deduplication_key=dedup,
                scope_type=definition.scope_type,
                tenant_id=tenant_id,
                related_job_id=None,
                integration_key=None,
                severity=definition.default_severity,
                title=f"Upprepade dispatch-fel ({count})",
                summary=f"{count} misslyckade integration events.",
                safe_details={
                    "source_type": "integration_event",
                    "source_id": tenant_id,
                    "failed_count": count,
                    "runbook_ref": definition.runbook_ref,
                    "recommended_action": "Granska integration events.",
                },
                source_class="intern_db_detected",
                current_fingerprint=fp,
            )
        )
    return out


def evaluate_integration_visma_reconciliation(
    db: Session, definition: AlertDefinition
) -> list[AlertCandidate]:
    from app.admin.operations_triage import _reconciliation_required_signals

    out: list[AlertCandidate] = []
    for tenant_id, tenant_name in iter_active_tenants(db):
        rows = _reconciliation_required_signals(db, tenant_id, tenant_name)
        for row in rows:
            source_id = row.get("source_id") or f"visma:{tenant_id}"
            dedup = f"tenant:{tenant_id}:integration:visma:reconciliation"
            fp = fingerprint_payload({"source_id": source_id})
            out.append(
                AlertCandidate(
                    alert_type=definition.alert_type,
                    deduplication_key=dedup,
                    scope_type=definition.scope_type,
                    tenant_id=tenant_id,
                    related_job_id=row.get("job_id"),
                    integration_key="visma",
                    severity=definition.default_severity,
                    title=row.get("title") or "Visma avstämning krävs",
                    summary=str(row.get("detail") or "")[:500],
                    safe_details={
                        "source_type": row.get("source_type") or "integration_event",
                        "source_id": source_id,
                        "runbook_ref": definition.runbook_ref,
                        "recommended_action": row.get("recommended_action"),
                    },
                    source_class="intern_db_detected",
                    current_fingerprint=fp,
                )
            )
    return out


def evaluate_tenant_scheduler_failed(db: Session, definition: AlertDefinition) -> list[AlertCandidate]:
    out: list[AlertCandidate] = []
    for tenant_id, tenant_name in iter_active_tenants(db):
        settings = TenantConfigRepository.get_settings(db, tenant_id) or {}
        if scheduler_expected_state(settings) != "running":
            continue
        state = settings.get("scheduler_state") or {}
        if state.get("last_status") != "failed":
            continue
        dedup = f"tenant:{tenant_id}:scheduler:failed"
        fp = fingerprint_payload({"last_status": "failed"})
        out.append(
            AlertCandidate(
                alert_type=definition.alert_type,
                deduplication_key=dedup,
                scope_type=definition.scope_type,
                tenant_id=tenant_id,
                related_job_id=None,
                integration_key=None,
                severity=definition.default_severity,
                title="Scheduler misslyckades",
                summary=state.get("last_error") or "Scheduler last_status failed.",
                safe_details={
                    "source_type": "scheduler",
                    "source_id": tenant_id,
                    "runbook_ref": definition.runbook_ref,
                    "recommended_action": "Kontrollera scheduler och kör om.",
                },
                source_class="intern_db_detected",
                current_fingerprint=fp,
            )
        )
    return out


def evaluate_system_backup_stale(db: Session, definition: AlertDefinition, settings: Settings) -> list[AlertCandidate]:
    from app.admin.system_status_sources import read_backup_status

    backup = read_backup_status(settings)
    if not backup.get("available"):
        return []
    status = normalize_backup_status(
        operation_status=backup.get("operation_status"),
        age_hours=backup.get("age_hours"),
        max_age_hours=float(getattr(settings, "BACKUP_MAX_AGE_HOURS", 25) or 25),
        source_available=True,
    )
    if status not in ("stale", "failed"):
        return []
    sev = severity_for_system_status(status, failed_severity="high") or definition.default_severity
    return [
        AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key="system:backup:stale",
            scope_type=definition.scope_type,
            tenant_id=None,
            related_job_id=None,
            integration_key=None,
            severity=sev,
            title="Backup för gammal eller fel",
            summary=backup.get("message") or "Backup status degraded.",
            safe_details={
                "source_type": "backup",
                "source_id": "system:backup",
                "normalized_status": status,
                "runbook_ref": definition.runbook_ref,
                "recommended_action": "Kör backup och verifiera.",
            },
            source_class="intern_metadata_detected",
            current_fingerprint=fingerprint_payload({"status": status}),
        )
    ]


def evaluate_system_backup_last_failed(
    db: Session, definition: AlertDefinition, settings: Settings
) -> list[AlertCandidate]:
    from app.admin.system_status_sources import read_backup_status

    backup = read_backup_status(settings)
    if not backup.get("available"):
        return []
    status = normalize_backup_status(
        operation_status=backup.get("operation_status"),
        age_hours=backup.get("age_hours"),
        max_age_hours=float(getattr(settings, "BACKUP_MAX_AGE_HOURS", 25) or 25),
        source_available=True,
    )
    if status != "failed":
        return []
    return [
        AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key="system:backup:last_failed",
            scope_type=definition.scope_type,
            tenant_id=None,
            related_job_id=None,
            integration_key=None,
            severity=definition.default_severity,
            title="Senaste backup misslyckades",
            summary=backup.get("message") or "Backup failed.",
            safe_details={
                "source_type": "backup",
                "source_id": "system:backup",
                "normalized_status": status,
                "runbook_ref": definition.runbook_ref,
                "recommended_action": "Åtgärda backup.",
            },
            source_class="intern_metadata_detected",
            current_fingerprint=fingerprint_payload({"status": "failed"}),
        )
    ]


def evaluate_system_restore_verification_stale(
    db: Session, definition: AlertDefinition, settings: Settings
) -> list[AlertCandidate]:
    from app.admin.system_status_sources import read_restore_status

    restore = read_restore_status(settings)
    if not restore.get("available"):
        return []
    age = restore.get("age_hours")
    if age is None or age < 168:
        return []
    return [
        AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key="system:restore:stale",
            scope_type=definition.scope_type,
            tenant_id=None,
            related_job_id=None,
            integration_key=None,
            severity=definition.default_severity,
            title="Restore-test för gammalt",
            summary=restore.get("message") or "Restore verification stale.",
            safe_details={
                "source_type": "restore",
                "source_id": "system:restore",
                "age_hours": int(age),
                "runbook_ref": definition.runbook_ref,
                "recommended_action": "Kör restore rehearsal.",
            },
            source_class="intern_metadata_detected",
            current_fingerprint=fingerprint_payload({"age": int(age)}),
        )
    ]


def evaluate_system_deploy_metadata_stale(
    db: Session, definition: AlertDefinition, settings: Settings
) -> list[AlertCandidate]:
    from app.admin.system_status_sources import read_build_metadata

    build = read_build_metadata(settings)
    if build.get("available"):
        return []
    return [
        AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key="system:deploy:metadata_stale",
            scope_type=definition.scope_type,
            tenant_id=None,
            related_job_id=None,
            integration_key=None,
            severity=definition.default_severity,
            title="Deploy-metadata saknas",
            summary="Build metadata not available.",
            safe_details={
                "source_type": "deploy",
                "source_id": "system:deploy",
                "normalized_status": "missing_expected",
                "runbook_ref": definition.runbook_ref,
                "recommended_action": "Verifiera deploy metadata.",
            },
            source_class="intern_metadata_detected",
            current_fingerprint=fingerprint_payload({"available": False}),
        )
    ]


def evaluate_system_evaluation_health(db: Session, definition: AlertDefinition) -> list[AlertCandidate]:
    from app.admin.alerts.models import AlertEvaluationRunRecord

    cutoff = _utcnow() - timedelta(hours=24)
    try:
        runs = (
            db.query(AlertEvaluationRunRecord)
            .filter(AlertEvaluationRunRecord.started_at >= cutoff)
            .order_by(AlertEvaluationRunRecord.started_at.desc())
            .limit(5)
            .all()
        )
    except Exception:
        return []
    error_runs = [r for r in runs if r.error_count > 0]
    if len(error_runs) < 2:
        return []
    return [
        AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key="system:evaluation:health",
            scope_type=definition.scope_type,
            tenant_id=None,
            related_job_id=None,
            integration_key=None,
            severity=definition.default_severity,
            title="Alert-evaluering degraderad",
            summary=f"{len(error_runs)} av senaste körningar hade evaluatorfel.",
            safe_details={
                "source_type": "evaluation_run",
                "source_id": "system:evaluation",
                "error_run_count": len(error_runs),
                "runbook_ref": definition.runbook_ref,
                "recommended_action": "Granska evaluation run history.",
            },
            source_class="intern_db_detected",
            current_fingerprint=fingerprint_payload({"errors": len(error_runs)}),
        )
    ]


def evaluate_tenant_activity_anomaly_low(
    db: Session, definition: AlertDefinition
) -> list[AlertCandidate]:
    """Slice 3 preview — skip if baseline insufficient."""
    from app.repositories.postgres.job_models import JobRecord

    out: list[AlertCandidate] = []
    cutoff = _utcnow() - timedelta(days=7)
    for tenant_id, tenant_name in iter_active_tenants(db):
        record = next(
            (t for t in TenantConfigRepository.list_all(db) if t.tenant_id == tenant_id),
            None,
        )
        if not record or getattr(record, "status", "active") != "active":
            continue
        try:
            recent = (
                db.query(JobRecord)
                .filter(
                    JobRecord.tenant_id == tenant_id,
                    JobRecord.created_at >= cutoff,
                )
                .count()
            )
            older = (
                db.query(JobRecord)
                .filter(
                    JobRecord.tenant_id == tenant_id,
                    JobRecord.created_at < cutoff,
                    JobRecord.created_at >= cutoff - timedelta(days=30),
                )
                .count()
            )
        except Exception:
            continue
        if older < 5:
            continue
        if recent > 0:
            continue
        dedup = f"tenant:{tenant_id}:activity:low"
        out.append(
            AlertCandidate(
                alert_type=definition.alert_type,
                deduplication_key=dedup,
                scope_type=definition.scope_type,
                tenant_id=tenant_id,
                related_job_id=None,
                integration_key=None,
                severity="warning",
                title="Ovanligt låg aktivitet (preview)",
                summary=f"Inga jobb senaste 7 dagar för aktiv tenant {tenant_name}.",
                safe_details={
                    "source_type": "tenant",
                    "source_id": tenant_id,
                    "preview": True,
                    "runbook_ref": definition.runbook_ref,
                    "recommended_action": "Verifiera att intag fungerar.",
                },
                source_class="intern_db_detected",
                current_fingerprint=fingerprint_payload({"recent": 0}),
            )
        )
    return out


EVALUATOR_DISPATCH: dict[str, Any] = {
    "job.approval_stale": lambda db, d, s: evaluate_job_approval_stale(db, d),
    "job.stuck_processing": lambda db, d, s: evaluate_job_stuck_processing(db, d),
    "job.failed_recent": lambda db, d, s: evaluate_job_failed_recent(db, d),
    "job.manual_review_stale": lambda db, d, s: evaluate_job_manual_review_stale(db, d),
    "job.repeated_failures": lambda db, d, s: evaluate_job_repeated_failures(db, d),
    "integration.health_critical": lambda db, d, s: evaluate_integration_health_critical(db, d, s),
    "integration.oauth_failure_recent": lambda db, d, s: evaluate_integration_oauth_failure_recent(db, d),
    "integration.dispatch_failures_repeated": lambda db, d, s: evaluate_integration_dispatch_failures_repeated(db, d),
    "integration.visma_reconciliation_required": lambda db, d, s: evaluate_integration_visma_reconciliation(db, d),
    "tenant.scheduler_failed": lambda db, d, s: evaluate_tenant_scheduler_failed(db, d),
    "system.backup_stale": lambda db, d, s: evaluate_system_backup_stale(db, d, s),
    "system.backup_last_failed": lambda db, d, s: evaluate_system_backup_last_failed(db, d, s),
    "system.restore_verification_stale": lambda db, d, s: evaluate_system_restore_verification_stale(db, d, s),
    "system.deploy_metadata_stale": lambda db, d, s: evaluate_system_deploy_metadata_stale(db, d, s),
    "system.evaluation_health": lambda db, d, s: evaluate_system_evaluation_health(db, d),
    "tenant.activity_anomaly_low": lambda db, d, s: evaluate_tenant_activity_anomaly_low(db, d),
}


def run_evaluator(
    db: Session,
    definition: AlertDefinition,
    settings: Settings,
) -> list[AlertCandidate]:
    fn = EVALUATOR_DISPATCH.get(definition.evaluator_module)
    if fn is None:
        raise ValueError(f"Unknown evaluator: {definition.evaluator_module}")
    return fn(db, definition, settings)
