"""Alert type registry — backend source of truth (Kapitel 10)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.admin.alerts.schemas import AlertScopeType, AlertSeverity, ReopenPolicy

EVALUATOR_VERSION = "1"


@dataclass(frozen=True)
class AlertDefinition:
    alert_type: str
    label_sv: str
    description_sv: str
    default_severity: AlertSeverity
    scope_type: AlertScopeType
    detection_class: Literal[
        "intern_db_detected", "intern_metadata_detected", "externally_detected"
    ]
    evaluator_module: str
    dedup_key_template: str
    cooldown_minutes: int
    reopen_policy: ReopenPolicy
    reopen_grace_minutes: int
    manual_resolve_allowed: bool
    suppress_allowed: bool
    runbook_ref: str | None
    enabled_by_default: bool
    slice: int


def _defs() -> dict[str, AlertDefinition]:
    items = [
        AlertDefinition(
            alert_type="job.approval_stale",
            label_sv="Gammal väntande godkännande",
            description_sv="Godkännande har väntat längre än tröskel.",
            default_severity="warning",
            scope_type="job",
            detection_class="intern_db_detected",
            evaluator_module="job.approval_stale",
            dedup_key_template="tenant:{tenant_id}:approval:{approval_id}:stale",
            cooldown_minutes=240,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=15,
            manual_resolve_allowed=True,
            suppress_allowed=False,
            runbook_ref="pilot_support",
            enabled_by_default=True,
            slice=1,
        ),
        AlertDefinition(
            alert_type="job.stuck_processing",
            label_sv="Jobb fastnat i kö",
            description_sv="Jobb i pending/processing längre än tröskel.",
            default_severity="high",
            scope_type="job",
            detection_class="intern_db_detected",
            evaluator_module="job.stuck_processing",
            dedup_key_template="tenant:{tenant_id}:job:{job_id}:stuck",
            cooldown_minutes=240,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=15,
            manual_resolve_allowed=True,
            suppress_allowed=False,
            runbook_ref="pilot_support",
            enabled_by_default=True,
            slice=1,
        ),
        AlertDefinition(
            alert_type="job.failed_recent",
            label_sv="Misslyckat jobb",
            description_sv="Jobb med status failed inom tidsfönster.",
            default_severity="warning",
            scope_type="job",
            detection_class="intern_db_detected",
            evaluator_module="job.failed_recent",
            dedup_key_template="tenant:{tenant_id}:job:{job_id}:failed",
            cooldown_minutes=60,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=15,
            manual_resolve_allowed=True,
            suppress_allowed=False,
            runbook_ref="pilot_support",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="job.manual_review_stale",
            label_sv="Gammal manuell granskning",
            description_sv="Olöst manual_review-jobb väntar för länge.",
            default_severity="warning",
            scope_type="job",
            detection_class="intern_db_detected",
            evaluator_module="job.manual_review_stale",
            dedup_key_template="tenant:{tenant_id}:job:{job_id}:manual_review_stale",
            cooldown_minutes=240,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=15,
            manual_resolve_allowed=True,
            suppress_allowed=False,
            runbook_ref="pilot_support",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="job.repeated_failures",
            label_sv="Upprepade jobbfel",
            description_sv="Flera misslyckade jobb inom tidsfönster.",
            default_severity="high",
            scope_type="tenant",
            detection_class="intern_db_detected",
            evaluator_module="job.repeated_failures",
            dedup_key_template="tenant:{tenant_id}:workflow:repeated_failure",
            cooldown_minutes=240,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=15,
            manual_resolve_allowed=True,
            suppress_allowed=False,
            runbook_ref="pilot_support",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="system.backup_stale",
            label_sv="Backup för gammal",
            description_sv="Senaste backup är äldre än tillåten ålder.",
            default_severity="high",
            scope_type="backup",
            detection_class="intern_metadata_detected",
            evaluator_module="system.backup_stale",
            dedup_key_template="system:backup:stale",
            cooldown_minutes=360,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=30,
            manual_resolve_allowed=False,
            suppress_allowed=True,
            runbook_ref="backup_failure",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="system.backup_last_failed",
            label_sv="Senaste backup misslyckades",
            description_sv="Backup-metadata visar misslyckad körning.",
            default_severity="critical",
            scope_type="backup",
            detection_class="intern_metadata_detected",
            evaluator_module="system.backup_last_failed",
            dedup_key_template="system:backup:last_failed",
            cooldown_minutes=360,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=30,
            manual_resolve_allowed=False,
            suppress_allowed=True,
            runbook_ref="backup_failure",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="system.restore_verification_stale",
            label_sv="Restore-test för gammalt",
            description_sv="Senaste restore-verifiering är för gammal.",
            default_severity="warning",
            scope_type="backup",
            detection_class="intern_metadata_detected",
            evaluator_module="system.restore_verification_stale",
            dedup_key_template="system:restore:stale",
            cooldown_minutes=720,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=30,
            manual_resolve_allowed=False,
            suppress_allowed=True,
            runbook_ref="backup_failure",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="system.deploy_metadata_stale",
            label_sv="Deploy-metadata för gammal",
            description_sv="Build/deploy-metadata saknas eller är inaktuell.",
            default_severity="warning",
            scope_type="deploy",
            detection_class="intern_metadata_detected",
            evaluator_module="system.deploy_metadata_stale",
            dedup_key_template="system:deploy:metadata_stale",
            cooldown_minutes=720,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=30,
            manual_resolve_allowed=False,
            suppress_allowed=True,
            runbook_ref="deploy_rollback",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="integration.health_critical",
            label_sv="Integration i kritiskt tillstånd",
            description_sv="Integration health rapporterar error.",
            default_severity="critical",
            scope_type="integration",
            detection_class="intern_db_detected",
            evaluator_module="integration.health_critical",
            dedup_key_template="tenant:{tenant_id}:integration:{integration_key}:health_error",
            cooldown_minutes=240,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=15,
            manual_resolve_allowed=True,
            suppress_allowed=False,
            runbook_ref="integration_general",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="integration.oauth_failure_recent",
            label_sv="OAuth-fel nyligen",
            description_sv="Misslyckad OAuth/inbox-sync i audit.",
            default_severity="high",
            scope_type="integration",
            detection_class="intern_db_detected",
            evaluator_module="integration.oauth_failure_recent",
            dedup_key_template="tenant:{tenant_id}:integration:{integration_key}:oauth_failure",
            cooldown_minutes=240,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=15,
            manual_resolve_allowed=True,
            suppress_allowed=False,
            runbook_ref="oauth_integration",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="integration.dispatch_failures_repeated",
            label_sv="Upprepade dispatch-fel",
            description_sv="Flera misslyckade integration events.",
            default_severity="high",
            scope_type="tenant",
            detection_class="intern_db_detected",
            evaluator_module="integration.dispatch_failures_repeated",
            dedup_key_template="tenant:{tenant_id}:integration:dispatch_repeated",
            cooldown_minutes=240,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=15,
            manual_resolve_allowed=True,
            suppress_allowed=False,
            runbook_ref="integration_general",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="integration.visma_reconciliation_required",
            label_sv="Visma avstämning krävs",
            description_sv="Visma write safety kräver operatör.",
            default_severity="high",
            scope_type="integration",
            detection_class="intern_db_detected",
            evaluator_module="integration.visma_reconciliation_required",
            dedup_key_template="tenant:{tenant_id}:integration:visma:reconciliation",
            cooldown_minutes=240,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=15,
            manual_resolve_allowed=True,
            suppress_allowed=False,
            runbook_ref="visma_write_safety",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="tenant.scheduler_failed",
            label_sv="Scheduler misslyckades",
            description_sv="Scheduler förväntas köra men rapporterar failed.",
            default_severity="high",
            scope_type="tenant",
            detection_class="intern_db_detected",
            evaluator_module="tenant.scheduler_failed",
            dedup_key_template="tenant:{tenant_id}:scheduler:failed",
            cooldown_minutes=240,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=15,
            manual_resolve_allowed=True,
            suppress_allowed=False,
            runbook_ref="scheduler",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="system.evaluation_health",
            label_sv="Alert-evaluering degraderad",
            description_sv="Flera evaluatorfel i senaste körningar.",
            default_severity="warning",
            scope_type="system",
            detection_class="intern_db_detected",
            evaluator_module="system.evaluation_health",
            dedup_key_template="system:evaluation:health",
            cooldown_minutes=360,
            reopen_policy="never_reopen",
            reopen_grace_minutes=30,
            manual_resolve_allowed=False,
            suppress_allowed=True,
            runbook_ref="monitoring",
            enabled_by_default=True,
            slice=2,
        ),
        AlertDefinition(
            alert_type="tenant.activity_anomaly_low",
            label_sv="Ovanligt låg aktivitet",
            description_sv="Aktiv tenant utan inkommande aktivitet (preview).",
            default_severity="warning",
            scope_type="tenant",
            detection_class="intern_db_detected",
            evaluator_module="tenant.activity_anomaly_low",
            dedup_key_template="tenant:{tenant_id}:activity:low",
            cooldown_minutes=1440,
            reopen_policy="reopen_existing",
            reopen_grace_minutes=60,
            manual_resolve_allowed=True,
            suppress_allowed=False,
            runbook_ref="pilot_support",
            enabled_by_default=False,
            slice=3,
        ),
    ]
    return {d.alert_type: d for d in items}


ALERT_REGISTRY: dict[str, AlertDefinition] = _defs()


def get_definition(alert_type: str) -> AlertDefinition | None:
    return ALERT_REGISTRY.get(alert_type)


def enabled_definitions(*, max_slice: int) -> list[AlertDefinition]:
    return [
        d
        for d in ALERT_REGISTRY.values()
        if d.enabled_by_default and d.slice <= max_slice
    ]


def validate_registry() -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for key, d in ALERT_REGISTRY.items():
        if key != d.alert_type:
            errors.append(f"registry key mismatch: {key} != {d.alert_type}")
        if key in seen:
            errors.append(f"duplicate alert_type: {key}")
        seen.add(key)
        if d.detection_class == "externally_detected":
            errors.append(f"externally_detected must not be in registry: {key}")
    return errors
