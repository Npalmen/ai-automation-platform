"""Shared tenant deletion for API and CLI (DEC-032)."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.admin.incident_models import (
    IncidentRecord,
    IncidentSignalRecord,
    IncidentTenantRecord,
    IncidentTimelineEventRecord,
)
from app.admin.onboarding.models import (
    OnboardingIntegrationVerificationRecord,
    OnboardingOAuthStateRecord,
    OnboardingSessionRecord,
    OnboardingStepDraftRecord,
    OnboardingStepStateRecord,
    TenantResourceBindingRecord,
)
from app.admin.tenant_lifecycle.invitation_models import IntegrationInvitationRecord
from app.admin.tenant_lifecycle.models import TenantActivationSnapshotRecord
from app.domain.integrations.models import IntegrationEvent
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.tools.test_environment.inventory import _orphan_incident_ids
from app.tools.test_environment.models import OperationLine, OperationReport, RowAction


@dataclass
class DeletionDryRun:
    tenant_id: str
    is_test_tenant: bool
    deletable: bool
    blocked_reason: str | None = None
    tables: list[dict[str, Any]] = field(default_factory=list)


class TenantDeletionService:
    """Single deletion path for super_admin test-tenant purge."""

    @staticmethod
    def _tenant_steps() -> list[tuple[str, type, RowAction]]:
        return [
            ("onboarding_step_drafts", OnboardingStepDraftRecord, RowAction.DELETE),
            ("onboarding_step_states", OnboardingStepStateRecord, RowAction.DELETE),
            ("onboarding_integration_verifications", OnboardingIntegrationVerificationRecord, RowAction.DELETE),
            ("onboarding_oauth_states", OnboardingOAuthStateRecord, RowAction.DELETE),
            ("onboarding_sessions", OnboardingSessionRecord, RowAction.DELETE),
            ("tenant_resource_bindings", TenantResourceBindingRecord, RowAction.DELETE),
            ("integration_invitations", IntegrationInvitationRecord, RowAction.DELETE),
            ("tenant_activation_snapshots", TenantActivationSnapshotRecord, RowAction.DELETE),
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

    @staticmethod
    def _session_ids(db: Session, tenant_id: str) -> list[str]:
        return [
            row[0]
            for row in db.query(OnboardingSessionRecord.id)
            .filter(OnboardingSessionRecord.tenant_id == tenant_id)
            .all()
        ]

    @staticmethod
    def _scoped_count(db: Session, tenant_id: str, model: type) -> int:
        if hasattr(model, "tenant_id"):
            return (
                db.query(model)
                .filter(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
                .count()
            )
        if hasattr(model, "session_id"):
            session_ids = TenantDeletionService._session_ids(db, tenant_id)
            if not session_ids:
                return 0
            return (
                db.query(model)
                .filter(model.session_id.in_(session_ids))  # type: ignore[attr-defined]
                .count()
            )
        return 0

    @staticmethod
    def _scoped_delete(db: Session, tenant_id: str, model: type) -> int:
        if hasattr(model, "tenant_id"):
            return (
                db.query(model)
                .filter(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
                .delete(synchronize_session=False)
            )
        if hasattr(model, "session_id"):
            session_ids = TenantDeletionService._session_ids(db, tenant_id)
            if not session_ids:
                return 0
            return (
                db.query(model)
                .filter(model.session_id.in_(session_ids))  # type: ignore[attr-defined]
                .delete(synchronize_session=False)
            )
        return 0

    @staticmethod
    def _pending_dispatch_count(db: Session, tenant_id: str) -> int:
        return (
            db.query(ApprovalRequestRecord)
            .filter(
                ApprovalRequestRecord.tenant_id == tenant_id,
                ApprovalRequestRecord.state.in_(("pending", "awaiting_approval")),
            )
            .count()
        )

    @staticmethod
    def dry_run(db: Session, tenant_id: str, *, require_test_tenant: bool = True) -> DeletionDryRun:
        record = db.query(TenantConfigRecord).filter(TenantConfigRecord.tenant_id == tenant_id).first()
        if record is None:
            return DeletionDryRun(
                tenant_id=tenant_id,
                is_test_tenant=False,
                deletable=False,
                blocked_reason="tenant_not_found",
            )
        is_test = bool(record.is_test_tenant)
        if require_test_tenant and not is_test:
            return DeletionDryRun(
                tenant_id=tenant_id,
                is_test_tenant=False,
                deletable=False,
                blocked_reason="not_test_tenant",
            )
        pending = TenantDeletionService._pending_dispatch_count(db, tenant_id)
        if pending > 0:
            return DeletionDryRun(
                tenant_id=tenant_id,
                is_test_tenant=is_test,
                deletable=False,
                blocked_reason=f"pending_dispatch:{pending}",
            )
        tables: list[dict[str, Any]] = []
        for table_name, model, action in TenantDeletionService._tenant_steps():
            count = TenantDeletionService._scoped_count(db, tenant_id, model)
            if count:
                tables.append({"table": table_name, "rows": count, "action": action.value})
        return DeletionDryRun(
            tenant_id=tenant_id,
            is_test_tenant=is_test,
            deletable=True,
            tables=tables,
        )

    @staticmethod
    def execute(
        db: Session,
        *,
        tenant_id: str,
        operator_id: str,
        reason: str,
        confirm_tenant_id: str,
        require_test_tenant: bool = True,
    ) -> OperationReport:
        if confirm_tenant_id != tenant_id:
            raise ValueError("confirm_tenant_id mismatch")
        dry = TenantDeletionService.dry_run(db, tenant_id, require_test_tenant=require_test_tenant)
        if not dry.deletable:
            raise ValueError(dry.blocked_reason or "not_deletable")
        report = OperationReport(command="purge_tenant", dry_run=False)
        db.add(
            AuditEventRecord(
                event_id=str(uuid4()),
                tenant_id=tenant_id,
                category="tenant_lifecycle",
                action="tenant.deleted",
                status="succeeded",
                details={"operator_id": operator_id, "reason": reason},
                created_at=datetime.now(timezone.utc),
            )
        )
        for table_name, model, action in TenantDeletionService._tenant_steps():
            deleted = TenantDeletionService._scoped_delete(db, tenant_id, model)
            if deleted:
                report.lines.append(
                    OperationLine(
                        table=table_name,
                        tenant_id=tenant_id,
                        rows=deleted,
                        action=action,
                    )
                )

        orphan_ids = _orphan_incident_ids(db)
        if orphan_ids:
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

        db.commit()
        return report
