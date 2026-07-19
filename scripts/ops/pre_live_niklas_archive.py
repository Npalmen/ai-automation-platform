#!/usr/bin/env python3
"""Del H — secret-free archive snapshot before Niklas operational reset."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import func, text

from app.admin.alerts.models import OperatorAlertRecord
from app.admin.incident_models import IncidentRecord, IncidentTenantRecord
from app.core.settings import get_settings
from app.domain.integrations.models import IntegrationEvent
from app.integrations.google.oauth_token_resolver import PROVIDER, gmail_connection_status
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

TENANT = sys.argv[1] if len(sys.argv) > 1 else "T_NIKLAS_DEMO_001"
OUT_CANDIDATES = [
    Path("/opt/krowolf/storage/status/pre_live_niklas_archive.json"),
    Path("/app/storage/status/pre_live_niklas_archive.json"),
]


def _count_group(db, model, tenant_id: str, column) -> dict:
    rows = (
        db.query(column, func.count())
        .filter(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
        .group_by(column)
        .all()
    )
    return {str(k): int(v) for k, v in rows}


def main() -> int:
    settings = get_settings()
    db = SessionLocal()
    try:
        wf = TenantConfigRepository.get_settings(db, TENANT).get("workflow_scan") or {}
        gmail = gmail_connection_status(db, TENANT, settings=settings)
        oauth = OAuthCredentialRepository.get(db, TENANT, PROVIDER)

        audit_actions = (
            db.query(AuditEventRecord.action, func.count())
            .filter(AuditEventRecord.tenant_id == TENANT)
            .group_by(AuditEventRecord.action)
            .order_by(func.count().desc())
            .limit(30)
            .all()
        )

        failed_integrations = (
            db.query(IntegrationEvent.integration_type, func.count())
            .filter(IntegrationEvent.tenant_id == TENANT, IntegrationEvent.status == "failed")
            .group_by(IntegrationEvent.integration_type)
            .all()
        )

        visma_failed = int(
            db.execute(
                text(
                    "SELECT count(*) FROM integration_events "
                    "WHERE tenant_id=:t AND status='failed' AND integration_type ILIKE '%visma%'"
                ),
                {"t": TENANT},
            ).scalar()
            or 0
        )

        report = {
            "report": "pre_live_niklas_archive",
            "tenant": TENANT,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "jobs_by_type": _count_group(db, JobRecord, TENANT, JobRecord.job_type),
            "jobs_by_status": _count_group(db, JobRecord, TENANT, JobRecord.status),
            "approvals_by_state": _count_group(db, ApprovalRequestRecord, TENANT, ApprovalRequestRecord.state),
            "alerts_by_status": _count_group(db, OperatorAlertRecord, TENANT, OperatorAlertRecord.status),
            "alerts_by_type": _count_group(db, OperatorAlertRecord, TENANT, OperatorAlertRecord.alert_type),
            "integration_events_by_status": _count_group(db, IntegrationEvent, TENANT, IntegrationEvent.status),
            "action_executions_total": (
                db.query(func.count()).select_from(ActionExecutionRecord).filter_by(tenant_id=TENANT).scalar() or 0
            ),
            "audit_events_total": (
                db.query(func.count()).select_from(AuditEventRecord).filter_by(tenant_id=TENANT).scalar() or 0
            ),
            "audit_top_actions": {a: int(c) for a, c in audit_actions},
            "incidents_linked": (
                db.query(func.count()).select_from(IncidentTenantRecord).filter_by(tenant_id=TENANT).scalar() or 0
            ),
            "incidents_total_db": db.query(func.count()).select_from(IncidentRecord).scalar() or 0,
            "integration_failures_by_type": {str(k): int(v) for k, v in failed_integrations},
            "visma_failed_events": visma_failed,
            "gmail_checkpoint": {
                "workflow_scan_status": wf.get("status"),
                "last_scan_at": wf.get("last_scan_at"),
                "gmail_summary_status": (wf.get("summary") or {}).get("gmail", {}).get("status"),
            },
            "oauth_status": {
                "credential_source": gmail.get("credential_source"),
                "connection_state": gmail.get("connection_state"),
                "scopes_set": bool(oauth and oauth.scopes),
                "email_domain": ((oauth.metadata_json or {}).get("email") or "").split("@")[-1] or None,
            },
        }

        out = next((p for p in OUT_CANDIDATES if p.parent.exists()), OUT_CANDIDATES[-1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
        print(json.dumps({"written": str(out), "summary": {
            "jobs": sum(report["jobs_by_status"].values()),
            "approvals": sum(report["approvals_by_state"].values()),
            "alerts": sum(report["alerts_by_status"].values()),
            "audit_events": report["audit_events_total"],
        }}, indent=2))
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
