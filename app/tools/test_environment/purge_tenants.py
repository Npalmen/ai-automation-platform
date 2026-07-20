from __future__ import annotations

from sqlalchemy.orm import Session

from app.admin.tenant_lifecycle.deletion_service import TenantDeletionService
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.tools.test_environment.models import OperationLine, OperationReport, RowAction

from .inventory import resolve_purge_tenant_ids


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

        dry = TenantDeletionService.dry_run(db, tenant_id, require_test_tenant=False)
        if not dry.deletable:
            report.lines.append(
                OperationLine(
                    table="tenant_configs",
                    tenant_id=tenant_id,
                    rows=0,
                    action=RowAction.SKIP,
                    note=dry.blocked_reason or "not_deletable",
                )
            )
            continue

        if dry_run:
            for table in dry.tables:
                report.lines.append(
                    OperationLine(
                        table=table["table"],
                        tenant_id=tenant_id,
                        rows=table["rows"],
                        action=RowAction(table["action"].upper()),
                    )
                )
            continue

        try:
            tenant_report = TenantDeletionService.execute(
                db,
                tenant_id=tenant_id,
                operator_id="cli:purge_tenants",
                reason="CLI purge-tenants",
                confirm_tenant_id=tenant_id,
                require_test_tenant=False,
            )
        except ValueError as exc:
            report.lines.append(
                OperationLine(
                    table="tenant_configs",
                    tenant_id=tenant_id,
                    rows=0,
                    action=RowAction.SKIP,
                    note=str(exc),
                )
            )
            continue

        report.lines.extend(tenant_report.lines)

    return report
