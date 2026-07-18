from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.admin.incident_models import (
    IncidentRecord,
    IncidentSignalRecord,
    IncidentTenantRecord,
    IncidentTimelineEventRecord,
)
from app.domain.integrations.models import IntegrationEvent
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

from .models import OperationLine, OperationReport, RowAction
from .reserved_tenants import LOCAL_STANDARD_PURGE_ALLOWLIST


def _count(db: Session, model, tenant_id: str) -> int:
    return (
        db.query(func.count())
        .select_from(model)
        .filter(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
        .scalar()
        or 0
    )


def list_tenant_ids(db: Session) -> list[str]:
    rows = db.query(TenantConfigRecord.tenant_id).order_by(TenantConfigRecord.tenant_id).all()
    return [row[0] for row in rows]


def build_inventory_report(db: Session, *, target_tenant_ids: set[str] | None = None) -> OperationReport:
    report = OperationReport(command="inventory", dry_run=True)
    tenant_ids = list_tenant_ids(db)

    for tenant_id in tenant_ids:
        in_scope = target_tenant_ids is None or tenant_id in target_tenant_ids
        action = RowAction.DELETE if in_scope else RowAction.SKIP
        note = "" if in_scope else "not in explicit purge scope"

        for table_name, model in (
            ("incident_signals", IncidentSignalRecord),
            ("incident_tenants", IncidentTenantRecord),
            ("integration_events", IntegrationEvent),
            ("action_executions", ActionExecutionRecord),
            ("approval_requests", ApprovalRequestRecord),
            ("jobs", JobRecord),
            ("audit_events", AuditEventRecord),
            ("oauth_credentials", OAuthCredentialRecord),
            ("tenant_api_keys", TenantApiKeyRecord),
            ("tenant_configs", TenantConfigRecord),
        ):
            count = _count(db, model, tenant_id)
            if count:
                row_action = RowAction.UNLINK if table_name == "incident_tenants" and in_scope else action
                report.lines.append(
                    OperationLine(
                        table=table_name,
                        tenant_id=tenant_id,
                        rows=count,
                        action=row_action if in_scope else RowAction.SKIP,
                        note=note,
                    )
                )

    orphan_incidents = _orphan_incident_ids(db)
    if orphan_incidents:
        timeline_count = (
            db.query(func.count())
            .select_from(IncidentTimelineEventRecord)
            .filter(IncidentTimelineEventRecord.incident_id.in_(orphan_incidents))
            .scalar()
            or 0
        )
        if timeline_count:
            report.lines.append(
                OperationLine(
                    table="incident_timeline_events",
                    tenant_id="*",
                    rows=timeline_count,
                    action=RowAction.ORPHAN_INCIDENT_DELETE,
                    note="incidents with no tenant links",
                )
            )
        report.lines.append(
            OperationLine(
                table="incidents",
                tenant_id="*",
                rows=len(orphan_incidents),
                action=RowAction.ORPHAN_INCIDENT_DELETE,
                note="no remaining incident_tenants",
            )
        )

    return report


def resolve_purge_tenant_ids(
    *,
    explicit_tenant_ids: list[str],
    profile: str | None,
) -> tuple[list[str], list[OperationLine]]:
    """Resolve purge targets. Unknown profile tenants are never auto-included."""
    skip_lines: list[OperationLine] = []
    targets: list[str] = []

    if profile == "local-standard":
        for tenant_id in sorted(LOCAL_STANDARD_PURGE_ALLOWLIST):
            targets.append(tenant_id)
        return targets, skip_lines

    for tenant_id in explicit_tenant_ids:
        normalized = tenant_id.strip()
        if not normalized:
            continue
        targets.append(normalized)

    return sorted(set(targets)), skip_lines


def _orphan_incident_ids(db: Session) -> list[str]:
    linked = {
        row[0]
        for row in db.query(IncidentTenantRecord.incident_id).distinct().all()
    }
    if not linked:
        all_incidents = [row[0] for row in db.query(IncidentRecord.incident_id).all()]
        return all_incidents
    return [
        row[0]
        for row in db.query(IncidentRecord.incident_id)
        .filter(~IncidentRecord.incident_id.in_(linked))
        .all()
    ]
