"""
System status aggregation service (Kapitel 8).

Read-only. No shell, no self-HTTP, no external API calls.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.admin.operations_overview import (
    _compute_integration_status,
    _count_failed_jobs,
    _count_open_manual_reviews,
    _count_pending_approvals,
    _count_stuck_jobs,
    _derive_scheduler_signal,
    _gmail_status_from_triage_rows,
    _integration_event_breakdown,
)
from app.admin.operations_triage import (
    _FAILED_JOBS_WINDOW_H,
    collect_all_triage_rows,
)
from app.admin.system_status_schemas import (
    ApiRuntimeStatus,
    BackupResilienceStatus,
    BuildDeployStatus,
    DatabaseRuntimeStatus,
    DeploymentBlock,
    DomainStatus,
    IntegrationRuntimeStatus,
    JobsRuntimeStatus,
    LastDeployStatus,
    ReleaseGateStatus,
    ResilienceBlock,
    RestoreResilienceStatus,
    RetentionResilienceStatus,
    RoutingConfigStatus,
    RunbookRef,
    RuntimeBlock,
    SchedulerRuntimeStatus,
    StatusLevel,
    SystemStatusResponse,
    VerificationStatus,
)
from app.admin.system_status_sources import (
    DatabaseUnreachable,
    MetadataReadOutcome,
    MetadataReadResult,
    check_database_reachable,
    read_backup_status,
    read_build_metadata,
    read_restore_status,
)
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

logger = logging.getLogger(__name__)

_STUCK_JOB_WINDOW_H = 48
_API_DESCRIPTION = (
    "API-processen svarade och kunde generera systemstatus. "
    "Detta intygar inte att hela plattformen är frisk."
)

_RUNBOOKS: list[RunbookRef] = [
    RunbookRef(id="backup_failure", label="Backupfel"),
    RunbookRef(id="restore_verification", label="Restore-verifiering"),
    RunbookRef(id="scheduler_failure", label="Schedulerfel"),
    RunbookRef(id="deploy_rollback", label="Deploy-rollback"),
    RunbookRef(id="caddy_verification", label="Caddy-verifiering"),
    RunbookRef(id="database_recovery", label="Databasåterställning"),
]

_LIMITATIONS: list[str] = [
    "Pilot- och onboarding-readiness ingår inte i systemstatusvyn.",
    "Metadata-skrivfel efter lyckad backup/restore syns endast i skriptlogg, inte i systemstatus.",
    "not_reported kan betyda att metadata aldrig skrivits eller att senaste skrivning misslyckades — ej skiljbart i API.",
]


def _parse_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _freshness_from_completed_at(
    completed_at: datetime | None,
    *,
    max_age_hours: float | None = None,
    max_age_days: float | None = None,
) -> tuple[str, str | None]:
    """Returns (freshness, limitation)."""
    if completed_at is None:
        return "not_reported", None
    now = datetime.now(timezone.utc)
    age = now - completed_at
    if max_age_hours is not None:
        if age <= timedelta(hours=max_age_hours):
            return "reported", None
        return "stale", f"Senaste händelse är äldre än {max_age_hours:g} timmar."
    if max_age_days is not None:
        if age <= timedelta(days=max_age_days):
            return "reported", None
        return "stale", f"Senaste händelse är äldre än {max_age_days:g} dagar."
    return "reported", None


def _metadata_freshness(result: MetadataReadResult) -> str:
    if result.outcome == MetadataReadOutcome.VALID:
        return "reported"
    if result.outcome in (MetadataReadOutcome.MISSING, MetadataReadOutcome.UNREADABLE):
        return "not_reported"
    return "not_reported"


def _truncate_sha(sha: str | None) -> str | None:
    if not sha or sha == "unknown":
        return sha
    if len(sha) > 12:
        return sha[:12]
    return sha


def _status_label(status: StatusLevel) -> str:
    return {
        "healthy": "Frisk",
        "warning": "Varning",
        "failed": "Fel",
        "critical": "Kritiskt",
        "paused": "Pausad",
        "unknown": "Okänd",
        "not_configured": "Ej konfigurerad",
    }.get(status, "Okänd")


def _domain_from_status(status: StatusLevel, summary: str) -> DomainStatus:
    return DomainStatus(status=status, label=_status_label(status), summary=summary)


def _count_jobs_by_status(db: Session, status: str) -> int:
    return db.query(JobRecord).filter(JobRecord.status == status).count()


def _oldest_ongoing_job(db: Session) -> datetime | None:
    row = (
        db.query(JobRecord)
        .filter(JobRecord.status.in_(("pending", "processing")))
        .order_by(JobRecord.updated_at.asc())
        .first()
    )
    if row is None:
        return None
    return row.updated_at


def _build_api_status(now: datetime, build_result: MetadataReadResult) -> ApiRuntimeStatus:
    details: dict[str, Any] = {"environment": None}
    limitation = None
    if build_result.outcome == MetadataReadOutcome.VALID and build_result.data:
        details["commit_sha"] = _truncate_sha(build_result.data.get("commit_sha"))
        details["release_id"] = build_result.data.get("release_id")
    elif build_result.outcome != MetadataReadOutcome.VALID:
        limitation = "Buildmetadata saknas eller är ogiltig."
    return ApiRuntimeStatus(
        status="healthy",
        label="API",
        summary=_API_DESCRIPTION,
        checked_at=now,
        source="api_process",
        freshness="reported",
        limitation=limitation,
        details=details,
    )


def _build_database_status(now: datetime, db_info: dict[str, Any]) -> DatabaseRuntimeStatus:
    return DatabaseRuntimeStatus(
        status="healthy",
        label="Databas",
        summary="Databasen svarade på kontrollerad SELECT 1.",
        checked_at=now,
        source="database_ping",
        freshness="reported",
        details={
            "reachable": db_info.get("reachable"),
            "response_time_ms": db_info.get("response_time_ms"),
            "dialect": db_info.get("dialect"),
            "schema_ready": db_info.get("schema_ready"),
        },
    )


def _build_scheduler_status(
    now: datetime,
    scheduler_signal: dict[str, Any],
) -> SchedulerRuntimeStatus:
    status = scheduler_signal.get("status", "unknown")
    return SchedulerRuntimeStatus(
        status=status,  # type: ignore[arg-type]
        label="Scheduler",
        summary=scheduler_signal.get("description") or "Schedulerstatus.",
        checked_at=now,
        source="tenant_scheduler_state",
        freshness="reported",
        details={"aggregated": True},
    )


def _build_jobs_status(
    now: datetime,
    *,
    pending_jobs: int,
    processing_jobs: int,
    pending_approvals: int,
    open_manual_reviews: int,
    failed_jobs: int,
    stuck_jobs: int,
    oldest_ongoing_at: datetime | None,
) -> JobsRuntimeStatus:
    if stuck_jobs > 0:
        status: StatusLevel = "failed"
        summary = f"{stuck_jobs} jobb har fastnat i kön."
    elif failed_jobs > 0:
        status = "warning"
        summary = f"{failed_jobs} misslyckade jobb senaste {_FAILED_JOBS_WINDOW_H} timmarna."
    else:
        status = "healthy"
        summary = "Inga fastnade eller nyligen misslyckade jobb."
    queue_age_hours: float | None = None
    if oldest_ongoing_at is not None:
        queue_age_hours = round(
            (now - oldest_ongoing_at).total_seconds() / 3600,
            1,
        )
    return JobsRuntimeStatus(
        status=status,
        label="Jobb och köer",
        summary=summary,
        checked_at=now,
        source="job_records",
        freshness="reported",
        details={
            "pending_jobs": pending_jobs,
            "processing_jobs": processing_jobs,
            "pending_approvals": pending_approvals,
            "open_manual_reviews": open_manual_reviews,
            "failed_jobs_last_window": failed_jobs,
            "stuck_jobs": stuck_jobs,
            "oldest_ongoing_job_at": oldest_ongoing_at,
            "queue_age_hours": queue_age_hours,
            "failed_jobs_window_hours": _FAILED_JOBS_WINDOW_H,
            "stuck_jobs_window_hours": _STUCK_JOB_WINDOW_H,
        },
    )


def _build_integration_statuses(
    now: datetime,
    integrations: dict[str, Any],
) -> dict[str, IntegrationRuntimeStatus]:
    result: dict[str, IntegrationRuntimeStatus] = {}
    labels = {
        "gmail": "Gmail",
        "visma": "Visma",
        "google_sheets": "Google Sheets",
    }
    for key, label in labels.items():
        data = integrations.get(key, {})
        status = data.get("status", "unknown")
        issues = int(data.get("issues", 0))
        affected = int(data.get("affected_tenants", 0))
        source = data.get("data_source", "integration_aggregation")
        if status == "healthy":
            summary = "Inga verifierade integrationsproblem."
        elif status == "unknown":
            summary = "Otillräcklig lokal data för att verifiera status."
        else:
            summary = f"{issues} problem, {affected} berörda tenants."
        result[key] = IntegrationRuntimeStatus(
            status=status,  # type: ignore[arg-type]
            label=label,
            summary=summary,
            checked_at=now,
            source=source,
            freshness="reported" if status != "unknown" else "not_reported",
            issues=issues,
            affected_tenants=affected,
        )
    return result


def _build_backup_resilience(
    now: datetime,
    result: MetadataReadResult,
    *,
    expected_interval_hours: int,
    max_age_hours: int,
) -> BackupResilienceStatus:
    if result.outcome != MetadataReadOutcome.VALID or not result.data:
        return BackupResilienceStatus(
            status="unknown",
            label="Senaste backup",
            summary="Ingen verifierbar backupmetadata.",
            checked_at=now,
            source="backup_status_file",
            freshness="not_reported",
            limitation="Statusfil saknas, är oläsbar eller ogiltig.",
            operation_status="unknown",
        )
    data = result.data
    op_status = data.get("status", "unknown")
    completed_at = _parse_utc_timestamp(data.get("completed_at"))
    freshness, freshness_note = _freshness_from_completed_at(
        completed_at,
        max_age_hours=max_age_hours,
    )
    integrity = data.get("archive_integrity_verified")
    if op_status == "failed":
        component_status: StatusLevel = "failed"
        summary = "Senaste backup misslyckades."
    elif freshness == "stale":
        component_status = "warning"
        summary = "Senaste backup är för gammal."
    elif integrity is not True:
        component_status = "warning"
        summary = "Backupmetadata saknar verifierad arkivintegritet."
    elif completed_at and (now - completed_at) <= timedelta(hours=expected_interval_hours):
        component_status = "healthy"
        summary = "Senaste backup lyckades inom förväntat intervall."
    else:
        component_status = "warning"
        summary = "Backupmetadata finns men ligger utanför förväntat intervall."
    return BackupResilienceStatus(
        status=component_status,
        label="Senaste backup",
        summary=summary,
        checked_at=now,
        source="backup_status_file",
        freshness=freshness,  # type: ignore[arg-type]
        limitation=freshness_note,
        operation_status=op_status if op_status in ("success", "failed") else "unknown",
        archive_integrity_verified=integrity if isinstance(integrity, bool) else None,
        details={
            "backup_id": data.get("backup_id"),
            "completed_at": data.get("completed_at"),
            "size_bytes": data.get("size_bytes"),
        },
    )


def _build_restore_resilience(
    now: datetime,
    result: MetadataReadResult,
    *,
    max_age_days: int,
) -> RestoreResilienceStatus:
    if result.outcome != MetadataReadOutcome.VALID or not result.data:
        return RestoreResilienceStatus(
            status="not_configured",
            label="Senaste restore-test",
            summary="Inget restore-test har rapporterats.",
            checked_at=now,
            source="restore_status_file",
            freshness="not_reported",
            limitation="Statusfil saknas — restore-test kan vara ogenomfört eller metadata ej skriven.",
            operation_status="unknown",
            schema_verification="unknown",
            application_smoke_verification="not_performed",
        )
    data = result.data
    op_status = data.get("status", "unknown")
    completed_at = _parse_utc_timestamp(data.get("completed_at"))
    freshness, freshness_note = _freshness_from_completed_at(
        completed_at,
        max_age_days=max_age_days,
    )
    schema_ver: VerificationStatus = data.get("schema_verification", "unknown")  # type: ignore[assignment]
    smoke_ver: VerificationStatus = data.get(  # type: ignore[assignment]
        "application_smoke_verification",
        "not_performed",
    )
    if op_status == "failed":
        component_status: StatusLevel = "failed"
        summary = "Senaste restore-test misslyckades."
    elif freshness == "stale":
        component_status = "warning"
        summary = "Senaste restore-test är för gammalt."
    elif schema_ver == "failed":
        component_status = "warning"
        summary = "Restore-test kördes men schemavalidering misslyckades."
    elif op_status == "success":
        component_status = "healthy"
        summary = "Senaste restore-test lyckades."
    else:
        component_status = "unknown"
        summary = "Restore-testmetadata är ofullständig."
    return RestoreResilienceStatus(
        status=component_status,
        label="Senaste restore-test",
        summary=summary,
        checked_at=now,
        source="restore_status_file",
        freshness=freshness,  # type: ignore[arg-type]
        limitation=freshness_note,
        operation_status=op_status if op_status in ("success", "failed") else "unknown",
        schema_verification=schema_ver,
        application_smoke_verification=smoke_ver,
        details={
            "test_id": data.get("test_id"),
            "backup_id": data.get("backup_id"),
            "completed_at": data.get("completed_at"),
        },
    )


def _build_retention_resilience(
    now: datetime,
    backup_result: MetadataReadResult,
) -> RetentionResilienceStatus:
    retention_days: int | None = None
    if backup_result.outcome == MetadataReadOutcome.VALID and backup_result.data:
        raw = backup_result.data.get("retention_days")
        if isinstance(raw, int):
            retention_days = raw
    if retention_days is None:
        return RetentionResilienceStatus(
            status="unknown",
            label="Retention",
            summary="Retention kunde inte härledas från backupmetadata.",
            checked_at=now,
            source="backup_status_file",
            freshness="not_reported",
        )
    return RetentionResilienceStatus(
        status="healthy",
        label="Retention",
        summary=f"Lokal retention: {retention_days} dagar (enligt senaste backupmetadata).",
        checked_at=now,
        source="backup_status_file",
        freshness="reported",
        retention_days=retention_days,
    )


def _build_deployment_block(
    now: datetime,
    build_result: MetadataReadResult,
) -> DeploymentBlock:
    if build_result.outcome == MetadataReadOutcome.VALID and build_result.data:
        data = build_result.data
        build_time = _parse_utc_timestamp(data.get("build_time"))
        current_build = BuildDeployStatus(
            status="healthy",
            label="Aktuell build",
            summary="Buildmetadata verifierad i image.",
            checked_at=now,
            source="build_metadata_file",
            freshness="reported",
            commit_sha=_truncate_sha(data.get("commit_sha")),
            build_time=build_time,
            release_id=data.get("release_id"),
            details={"source": data.get("source")},
        )
    else:
        current_build = BuildDeployStatus(
            status="unknown",
            label="Aktuell build",
            summary="Buildmetadata saknas eller är ogiltig.",
            checked_at=now,
            source="build_metadata_file",
            freshness="not_reported",
            limitation="Ingen verifierad buildmetadata i runtime-image.",
        )

    last_deploy = LastDeployStatus(
        status="unknown",
        label="Senaste deploy",
        summary="Deploytid är inte verifierbar — skiljs från byggtid.",
        checked_at=now,
        source="not_available",
        freshness="not_reported",
        limitation="Ingen deployhistorik lagras ännu.",
        deployed_at=None,
    )

    routing_config = RoutingConfigStatus(
        status="warning",
        label="Routing-konfiguration",
        summary="Caddy-konfiguration: Ej verifierad i versionshanterad källa.",
        checked_at=now,
        source="documentation",
        freshness="not_reported",
        limitation="infra/Caddyfile.example är inte produktionssanning.",
    )

    release_gate = ReleaseGateStatus(
        status="unknown",
        label="Release gate",
        summary="Ingen maskinläsbar release-gate-status i runtime.",
        checked_at=now,
        source="not_available",
        freshness="not_reported",
        limitation="CI publicerar inte gate-resultat till runtime ännu.",
    )

    return DeploymentBlock(
        current_build=current_build,
        last_deploy=last_deploy,
        routing_config=routing_config,
        release_gate=release_gate,
    )


def _compute_runtime_domain(
    runtime: RuntimeBlock,
) -> DomainStatus:
    statuses = [
        runtime.api.status,
        runtime.database.status,
        runtime.scheduler.status,
        runtime.jobs.status,
        *[i.status for i in runtime.integrations.values()],
    ]
    if runtime.database.status == "failed":
        return _domain_from_status("critical", "Databasen är otillgänglig.")
    if "failed" in statuses or runtime.jobs.status == "failed":
        return _domain_from_status("failed", "Minst en runtime-komponent har verifierat fel.")
    if "paused" in statuses:
        return _domain_from_status("warning", "Scheduler är pausad för minst en tenant.")
    if "warning" in statuses or "unknown" in statuses:
        return _domain_from_status("warning", "Runtime har varningar eller okända signaler.")
    return _domain_from_status("healthy", "Alla runtime-signaler verifierat friska.")


def _compute_resilience_domain(resilience: ResilienceBlock) -> DomainStatus:
    statuses = [
        resilience.last_backup.status,
        resilience.last_restore_test.status,
        resilience.retention.status,
    ]
    if "failed" in statuses:
        return _domain_from_status("failed", "Backup eller restore har verifierat fel.")
    backup_ok = resilience.last_backup.status == "healthy"
    restore_ok = resilience.last_restore_test.status == "healthy"
    if backup_ok and not restore_ok:
        return _domain_from_status(
            "warning",
            "Backup finns men restore-test saknas, är för gammalt eller ofullständigt.",
        )
    if "warning" in statuses or "not_configured" in statuses or "unknown" in statuses:
        return _domain_from_status("warning", "Resiliens har varningar eller saknad verifiering.")
    if backup_ok and restore_ok:
        return _domain_from_status("healthy", "Backup och restore-test verifierade.")
    return _domain_from_status("unknown", "Resiliensstatus kunde inte fastställas.")


def _compute_deploy_readiness_domain(deployment: DeploymentBlock) -> DomainStatus:
    statuses = [
        deployment.current_build.status,
        deployment.last_deploy.status,
        deployment.routing_config.status,
        deployment.release_gate.status,
    ]
    if all(s in ("healthy",) for s in statuses):
        return _domain_from_status("healthy", "Deploy readiness verifierad.")
    if any(s == "warning" for s in statuses):
        return _domain_from_status(
            "warning",
            "Deploy readiness har dokumenterade gap (routing, deployhistorik eller gate).",
        )
    return _domain_from_status(
        "warning",
        "Deploy readiness är ofullständig — påverkar inte runtime-status automatiskt.",
    )


def _compute_overall_status(
    runtime_domain: DomainStatus,
    resilience_domain: DomainStatus,
    deploy_domain: DomainStatus,
) -> DomainStatus:
    if runtime_domain.status == "critical":
        return runtime_domain
    if runtime_domain.status == "failed":
        return runtime_domain
    if resilience_domain.status == "failed":
        return resilience_domain
    if runtime_domain.status in ("warning", "paused") or resilience_domain.status == "warning":
        parts = []
        if runtime_domain.status != "healthy":
            parts.append(runtime_domain.summary)
        if resilience_domain.status != "healthy":
            parts.append(resilience_domain.summary)
        if deploy_domain.status == "warning":
            parts.append(f"Deploy readiness: {deploy_domain.summary}")
        return _domain_from_status("warning", " ".join(parts) or "Varningar kräver uppmärksamhet.")
    if deploy_domain.status == "warning":
        return _domain_from_status(
            "warning",
            f"{runtime_domain.summary} Deploy readiness: {deploy_domain.summary}",
        )
    if runtime_domain.status == "unknown" or resilience_domain.status == "unknown":
        return _domain_from_status("unknown", "Obligatoriska signaler saknar data.")
    if runtime_domain.status == "healthy" and resilience_domain.status == "healthy":
        return _domain_from_status("healthy", "Runtime och resiliens verifierat friska.")
    return _domain_from_status("unknown", "Systemstatus kunde inte fastställas.")


def get_system_status(db: Session, *, app_settings: Any) -> SystemStatusResponse:
    now = datetime.now(timezone.utc)

    db_info = check_database_reachable(db)

    build_result = read_build_metadata(app_settings)
    backup_result = read_backup_status(app_settings)
    restore_result = read_restore_status(app_settings)

    tenant_records: list[Any] = []
    scheduler_signal: dict[str, Any] = {"status": "unknown", "description": "Scheduler kunde inte läsas."}
    integrations: dict[str, Any] = {}
    pending_jobs = processing_jobs = pending_approvals = open_manual_reviews = 0
    failed_jobs = stuck_jobs = 0
    oldest_ongoing_at: datetime | None = None

    try:
        tenant_records = TenantConfigRepository.list_all(db)
        scheduler_signal = _derive_scheduler_signal(tenant_records)
        since_48h = now - timedelta(hours=_FAILED_JOBS_WINDOW_H)
        stuck_cutoff = now - timedelta(hours=_STUCK_JOB_WINDOW_H)
        period_start = now - timedelta(hours=24)
        pending_jobs = _count_jobs_by_status(db, "pending")
        processing_jobs = _count_jobs_by_status(db, "processing")
        pending_approvals = _count_pending_approvals(db)
        open_manual_reviews = _count_open_manual_reviews(db)
        failed_jobs = _count_failed_jobs(db, since_48h)
        stuck_jobs = _count_stuck_jobs(db, stuck_cutoff)
        oldest_ongoing_at = _oldest_ongoing_job(db)
        all_triage_rows = collect_all_triage_rows(db, app_settings=app_settings)
        gmail_status = _gmail_status_from_triage_rows(all_triage_rows, len(tenant_records))
        event_breakdown = _integration_event_breakdown(db, period_start)
        integrations = _compute_integration_status(event_breakdown, gmail_status)
    except Exception:
        logger.warning("system_status_runtime_partial_failure", exc_info=True)

    runtime = RuntimeBlock(
        api=_build_api_status(now, build_result),
        database=_build_database_status(now, db_info),
        scheduler=_build_scheduler_status(now, scheduler_signal),
        jobs=_build_jobs_status(
            now,
            pending_jobs=pending_jobs,
            processing_jobs=processing_jobs,
            pending_approvals=pending_approvals,
            open_manual_reviews=open_manual_reviews,
            failed_jobs=failed_jobs,
            stuck_jobs=stuck_jobs,
            oldest_ongoing_at=oldest_ongoing_at,
        ),
        integrations=_build_integration_statuses(now, integrations),
    )

    resilience = ResilienceBlock(
        last_backup=_build_backup_resilience(
            now,
            backup_result,
            expected_interval_hours=int(
                getattr(app_settings, "BACKUP_EXPECTED_INTERVAL_HOURS", 24)
            ),
            max_age_hours=int(getattr(app_settings, "BACKUP_MAX_AGE_HOURS", 25)),
        ),
        last_restore_test=_build_restore_resilience(
            now,
            restore_result,
            max_age_days=int(getattr(app_settings, "RESTORE_TEST_MAX_AGE_DAYS", 30)),
        ),
        retention=_build_retention_resilience(now, backup_result),
    )

    deployment = _build_deployment_block(now, build_result)

    runtime_domain = _compute_runtime_domain(runtime)
    resilience_domain = _compute_resilience_domain(resilience)
    deploy_domain = _compute_deploy_readiness_domain(deployment)
    overall = _compute_overall_status(runtime_domain, resilience_domain, deploy_domain)

    return SystemStatusResponse(
        generated_at=now,
        runtime_status=runtime_domain,
        resilience_status=resilience_domain,
        deploy_readiness_status=deploy_domain,
        overall_status=overall,
        runtime=runtime,
        resilience=resilience,
        deployment=deployment,
        limitations=list(_LIMITATIONS),
        runbooks=list(_RUNBOOKS),
    )
