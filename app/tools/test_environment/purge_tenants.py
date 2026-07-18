from __future__ import annotations

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

from .inventory import _orphan_incident_ids, resolve_purge_tenant_ids
from .models import OperationLine, OperationReport, RowAction


def _delete_tenant_scoped(db: Session, tenant_id: str, report: OperationReport) -> None:
  steps: list[tuple[str, type, RowAction]] = [
      ("incident_signals", IncidentSignalRecord, RowAction.DELETE),
      ("incident_tenants", IncidentTenantRecord, RowAction.UNLINK),
      ("integration_events", IntegrationEvent, RowAction.DELETE),
      ("action_executions", ActionExecutionRecord, RowAction.DELETE),
      ("approval_requests", ApprovalRequestRecord, RowAction.DELETE),
      ("jobs", JobRecord, RowAction.DELETE),
      ("audit_events", AuditEventRecord, RowAction.DELETE),
      ("oauth_credentials", OAuthCredentialRecord, RowAction.DELETE),
      ("tenant_api_keys", TenantApiKeyRecord, RowAction.DELETE),
      ("tenant_configs", TenantConfigRecord, RowAction.DELETE),
  ]

  for table_name, model, action in steps:
      deleted = (
          db.query(model)
          .filter(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
          .delete(synchronize_session=False)
      )
      if deleted:
          report.lines.append(
              OperationLine(
                  table=table_name,
                  tenant_id=tenant_id,
                  rows=deleted,
                  action=action,
              )
          )


def _delete_orphan_incidents(db: Session, report: OperationReport) -> None:
    orphan_ids = _orphan_incident_ids(db)
    if not orphan_ids:
        return

    timeline_deleted = (
        db.query(IncidentTimelineEventRecord)
        .filter(IncidentTimelineEventRecord.incident_id.in_(orphan_ids))
        .delete(synchronize_session=False)
    )
    if timeline_deleted:
        report.lines.append(
            OperationLine(
                table="incident_timeline_events",
                tenant_id="*",
                rows=timeline_deleted,
                action=RowAction.ORPHAN_INCIDENT_DELETE,
            )
        )

    incidents_deleted = (
        db.query(IncidentRecord)
        .filter(IncidentRecord.incident_id.in_(orphan_ids))
        .delete(synchronize_session=False)
    )
    if incidents_deleted:
        report.lines.append(
            OperationLine(
                table="incidents",
                tenant_id="*",
                rows=incidents_deleted,
                action=RowAction.ORPHAN_INCIDENT_DELETE,
            )
        )


def purge_tenants(
    db: Session,
    *,
    explicit_tenant_ids: list[str],
    profile: str | None,
    dry_run: bool,
) -> OperationReport:
    targets, _ = resolve_purge_tenant_ids(
        explicit_tenant_ids=explicit_tenant_ids,
        profile=profile,
    )
    report = OperationReport(command="purge-tenants", dry_run=dry_run)

    if not targets:
        report.lines.append(
            OperationLine(
                table="(none)",
                tenant_id="",
                rows=0,
                action=RowAction.SKIP,
                note="no tenant targets resolved; pass --tenant-id or --profile local-standard",
            )
        )
        return report

    existing = {
        row[0]
        for row in db.query(TenantConfigRecord.tenant_id)
        .filter(TenantConfigRecord.tenant_id.in_(targets))
        .all()
    }

    for tenant_id in targets:
        if tenant_id not in existing:
            report.lines.append(
                OperationLine(
                    table="tenant_configs",
                    tenant_id=tenant_id,
                    rows=0,
                    action=RowAction.SKIP,
                    note="tenant not found",
                )
            )
            continue

        if dry_run:
            for table_name, model, action in (
                ("incident_signals", IncidentSignalRecord, RowAction.DELETE),
                ("incident_tenants", IncidentTenantRecord, RowAction.UNLINK),
                ("integration_events", IntegrationEvent, RowAction.DELETE),
                ("action_executions", ActionExecutionRecord, RowAction.DELETE),
                ("approval_requests", ApprovalRequestRecord, RowAction.DELETE),
                ("jobs", JobRecord, RowAction.DELETE),
                ("audit_events", AuditEventRecord, RowAction.DELETE),
                ("oauth_credentials", OAuthCredentialRecord, RowAction.DELETE),
                ("tenant_api_keys", TenantApiKeyRecord, RowAction.DELETE),
                ("tenant_configs", TenantConfigRecord, RowAction.DELETE),
            ):
                count = (
                    db.query(model)
                    .filter(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
                    .count()
                )
                if count:
                    report.lines.append(
                        OperationLine(
                            table=table_name,
                            tenant_id=tenant_id,
                            rows=count,
                            action=action,
                        )
                    )
            continue

        _delete_tenant_scoped(db, tenant_id, report)

    if not dry_run:
        _delete_orphan_incidents(db, report)
        db.commit()
    elif targets:
        orphan_ids = _orphan_incident_ids(db)
        for tenant_id in targets:
            if tenant_id not in existing:
                continue
            # Simulate which incidents might become orphan after unlink — report only.
            pass
        if orphan_ids:
            timeline_count = (
                db.query(IncidentTimelineEventRecord)
                .filter(IncidentTimelineEventRecord.incident_id.in_(orphan_ids))
                .count()
            )
            if timeline_count:
                report.lines.append(
                    OperationLine(
                        table="incident_timeline_events",
                        tenant_id="*",
                        rows=timeline_count,
                        action=RowAction.ORPHAN_INCIDENT_DELETE,
                        note="existing orphans (dry-run)",
                    )
                )
            report.lines.append(
                OperationLine(
                    table="incidents",
                    tenant_id="*",
                    rows=len(orphan_ids),
                    action=RowAction.ORPHAN_INCIDENT_DELETE,
                    note="existing orphans (dry-run)",
                )
            )

    return report
