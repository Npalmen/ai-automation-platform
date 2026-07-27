"""R3 regression: superseded / unexpected secondary approval lifecycle (canary 30294376010).

Subtype locked: unexpected_secondary_approval_pending — create_monday_item when Monday
integration is not enabled for the tenant (live-eval: google_mail only).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.decision_record_repository import DecisionRecordRepository
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.workflows.action_approval_resolution import resolve_per_action_approval
from app.workflows.approval_dispatcher import dispatch_approval_request
from app.workflows.approval_service import (
    build_approval_request,
    count_pending_approvals_for_job,
)
from app.workflows.decision_record_service import record_action_authorization
from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session
from app.workflows.processors.action_dispatch_processor import (
    _apply_dispatch_authorization,
    _build_lead_default_actions,
    process_action_dispatch_job,
)
from app.workflows.processors.ai_processor_utils import append_processor_result

R3_SUBTYPE = "unexpected_secondary_approval_pending"
R3_PENDING_ACTION = "create_monday_item"


def _sqlite_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    for table in (
        JobRecord.__table__,
        ApprovalRequestRecord.__table__,
        DecisionRecordRow.__table__,
        AuditEventRecord.__table__,
        ActionExecutionRecord.__table__,
        TenantConfigRecord.__table__,
    ):
        table.create(engine, checkfirst=True)

    @event.listens_for(DecisionRecordRow, "before_insert")
    def _assign_event_sequence(mapper, connection, target):
        if connection.dialect.name != "sqlite":
            return
        if getattr(target, "event_sequence", None) is None:
            result = connection.execute(
                DecisionRecordRow.__table__.select().with_only_columns(
                    DecisionRecordRow.event_sequence
                )
            )
            max_seq = 0
            for row in result:
                max_seq = max(max_seq, int(row[0] or 0))
            target.event_sequence = max_seq + 1

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_decision_records_idempotency "
                "ON decision_records (tenant_id, idempotency_key)"
            )
        )
    return sessionmaker(bind=engine)()


def _seed_tenant(
    db,
    tenant_id: str,
    *,
    allowed_integrations: list[str],
    internal_notification_email: str = "",
) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        TenantConfigRecord(
            tenant_id=tenant_id,
            name=f"Tenant {tenant_id}",
            slug=tenant_id.lower(),
            status="active",
            lifecycle_status="active",
            is_test_tenant=True,
            allowed_integrations=allowed_integrations,
            auto_actions={"lead": "manual"},
            settings={
                "automation": {"followups_enabled": True},
                "branding": {
                    "internal_notification_email": internal_notification_email,
                    "email_signature_name": "Team",
                },
            },
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def _live_eval_snapshot(tenant_id: str) -> dict:
    return {
        "evaluation_run_id": "run-r3-repro",
        "tenant_id": tenant_id,
        "scenario_id": "TBSM01_lead_approve_reply",
        "attempt_id": 1,
        "transport_mode": "live_gmail",
        "ai_mode": "fixture_ai",
        "config_hash": "abc123",
        "trusted": True,
    }


def _tbsm01_lead_job(tenant_id: str) -> Job:
    return Job(
        job_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        job_type=JobType.LEAD,
        input_data={
            "subject": "Offert solceller",
            "message_text": "Hej, jag vill ha offert på solceller.",
            "sender": {"name": "Anna", "email": "anna@example.com"},
            "live_eval": _live_eval_snapshot(tenant_id),
        },
        processor_history=[
            {
                "processor": "policy_processor",
                "result": {
                    "payload": {
                        "decision": "send_for_approval",
                        "detected_job_type": "lead",
                        "recommended_next_step": "awaiting_approval",
                    }
                },
            },
            {
                "processor": "classification_processor",
                "result": {"payload": {"detected_job_type": "lead"}},
            },
            {
                "processor": "lead_processor",
                "result": {"payload": {"priority": "normal"}},
            },
            {
                "processor": "lead_analyzer_processor",
                "result": {
                    "payload": {
                        "service_profile_type": "solar_installation",
                        "generated_question_message": "Vilken adress gäller det?",
                    }
                },
            },
        ],
    )


def _seed_job_record(db, job: Job, *, status: str = "processing") -> None:
    now = datetime.now(timezone.utc)
    db.add(
        JobRecord(
            job_id=job.job_id,
            tenant_id=job.tenant_id,
            job_type="lead",
            status=status,
            input_data=job.input_data,
            result={"processor_history": job.processor_history},
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def _dump_approval_rows(db, tenant_id: str, job_id: str) -> list[dict]:
    rows = ApprovalRequestRepository.list_for_job(db, tenant_id=tenant_id, job_id=job_id)
    return [
        {
            "approval_id": row.approval_id,
            "action_type": (row.delivery_payload or {}).get("type"),
            "next_on_approve": row.next_on_approve,
            "state": row.state,
            "action_operation_id": (row.request_payload or {}).get("action_operation_id"),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]


class TestR3ReproductionAndSubtype:
    """Documents canary 30294376010 pending row before fix."""

    SUBTYPE = R3_SUBTYPE
    PENDING_ACTION = R3_PENDING_ACTION

    def test_pre_fix_integration_gate_missing_leaves_monday_pending(self):
        """Without dispatch integration gate, Monday is materialized and stays pending after target approve."""
        db = _sqlite_session()
        tenant_id = "T_R3_PRE"
        _seed_tenant(db, tenant_id, allowed_integrations=["google_mail"])
        job = _tbsm01_lead_job(tenant_id)
        _seed_job_record(db, job)
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)

        with patch(
            "app.workflows.processors.action_dispatch_processor._integration_allowed_for_action",
            return_value=True,
        ):
            updated = process_action_dispatch_job(job, db=db, trace=trace)

        payload = updated.result["payload"]
        assert payload["pending_approval_count"] == 2
        rows = _dump_approval_rows(db, tenant_id, job.job_id)
        pending_types = sorted(
            row["action_type"] for row in rows if row["state"] == "pending"
        )
        assert pending_types == ["create_monday_item", "send_customer_auto_reply"]
        assert count_pending_approvals_for_job(updated, db=db) == 2

        target = next(
            row for row in rows if row["action_type"] == "send_customer_auto_reply"
        )
        approval = db.get(ApprovalRequestRecord, target["approval_id"])
        with (
            patch(
                "app.workflows.action_executor._integration_allowed_for_action",
                return_value=True,
            ),
            patch(
                "app.workflows.action_executor.is_integration_configured",
                return_value=True,
            ),
            patch(
                "app.workflows.action_executor.get_integration_connection_config",
                return_value={"configured": True},
            ),
            patch(
                "app.workflows.action_executor.get_integration_adapter",
                return_value=MagicMock(
                    execute_action=MagicMock(return_value={"provider": "gmail", "message_id": "m1"})
                ),
            ),
            patch("app.workflows.email_approval_resolution.finalize_email_approval_resolution"),
        ):
            resolve_per_action_approval(db, approval, approved=True, actor="op")
        db.commit()

        assert count_pending_approvals_for_job(updated, db=db) == 1
        remaining = [
            row for row in _dump_approval_rows(db, tenant_id, job.job_id)
            if row["state"] == "pending"
        ]
        assert len(remaining) == 1
        assert remaining[0]["action_type"] == self.PENDING_ACTION
        assert self.SUBTYPE == "unexpected_secondary_approval_pending"


class TestDispatchIntegrationGate:
    def test_monday_skipped_when_integration_not_allowed(self):
        db = _sqlite_session()
        tenant_id = "T_GATE"
        _seed_tenant(db, tenant_id, allowed_integrations=["google_mail"])
        job = _tbsm01_lead_job(tenant_id)
        settings = {
            "followups_enabled": True,
            "auto_actions": {"lead": "manual"},
            "internal_notification_email": "",
        }
        actions = _build_lead_default_actions(job, settings)
        authorized = _apply_dispatch_authorization(job, actions, settings, db=db)
        monday = next(a for a in authorized if a.get("type") == "create_monday_item")
        handoff = next(a for a in authorized if a.get("type") == "send_internal_handoff")
        reply = next(a for a in authorized if a.get("type") == "send_customer_auto_reply")
        assert monday.get("_skip") is True
        assert monday.get("_skip_reason") == "integration_not_allowed"
        assert handoff.get("_skip") is True
        assert handoff.get("_skip_reason") == "no_internal_recipient"
        assert reply.get("_needs_approval") is True

    def test_tbsm01_materializes_exactly_one_target_approval(self):
        db = _sqlite_session()
        tenant_id = "T_TBSM01"
        _seed_tenant(db, tenant_id, allowed_integrations=["google_mail"])
        job = _tbsm01_lead_job(tenant_id)
        _seed_job_record(db, job)
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)

        updated = process_action_dispatch_job(job, db=db, trace=trace)
        rows = _dump_approval_rows(db, tenant_id, job.job_id)
        pending = [row for row in rows if row["state"] == "pending"]
        assert len(pending) == 1
        assert pending[0]["action_type"] == "send_customer_auto_reply"
        assert pending[0]["next_on_approve"] == "action_execute"
        assert count_pending_approvals_for_job(updated, db=db) == 1
        assert updated.result["payload"]["pending_approval_count"] == 1

    def test_tenant_with_internal_notification_still_materializes_handoff(self):
        db = _sqlite_session()
        tenant_id = "T_HANDOFF"
        _seed_tenant(
            db,
            tenant_id,
            allowed_integrations=["google_mail"],
            internal_notification_email="ops@example.com",
        )
        job = _tbsm01_lead_job(tenant_id)
        settings = {
            "followups_enabled": True,
            "auto_actions": {"lead": "manual"},
            "internal_notification_email": "ops@example.com",
        }
        actions = _build_lead_default_actions(job, settings)
        authorized = _apply_dispatch_authorization(job, actions, settings, db=db)
        handoff = next(a for a in authorized if a.get("type") == "send_internal_handoff")
        assert handoff.get("_needs_approval") is True
        assert handoff.get("_skip") is not True

    def test_tenant_with_monday_enabled_materializes_monday_approval(self):
        db = _sqlite_session()
        tenant_id = "T_MONDAY"
        _seed_tenant(db, tenant_id, allowed_integrations=["google_mail", "monday"])
        job = _tbsm01_lead_job(tenant_id)
        settings = {
            "followups_enabled": True,
            "auto_actions": {"lead": "manual"},
            "internal_notification_email": "",
        }
        actions = _build_lead_default_actions(job, settings)
        authorized = _apply_dispatch_authorization(job, actions, settings, db=db)
        monday = next(a for a in authorized if a.get("type") == "create_monday_item")
        assert monday.get("_needs_approval") is True


class TestTBSM01ApproveLifecycle:
    def test_after_target_approve_pending_count_zero_and_resume_once(self):
        db = _sqlite_session()
        tenant_id = "T_APPROVE"
        _seed_tenant(db, tenant_id, allowed_integrations=["google_mail"])
        job = _tbsm01_lead_job(tenant_id)
        job.input_data = {
            key: value for key, value in job.input_data.items() if key != "live_eval"
        }
        _seed_job_record(db, job)
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)
        updated = process_action_dispatch_job(job, db=db, trace=trace)
        rows = ApprovalRequestRepository.list_for_job(db, tenant_id=tenant_id, job_id=job.job_id)
        target = next(
            row for row in rows
            if (row.delivery_payload or {}).get("type") == "send_customer_auto_reply"
        )
        operation_id = target.request_payload["action_operation_id"]
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)
        action = dict(target.delivery_payload or {})
        action["_action_operation_id"] = operation_id
        record_action_authorization(
            db, trace, job, action, authorization="approval_required",
        )
        db.commit()

        adapter = MagicMock(
            execute_action=MagicMock(
                return_value={
                    "provider": "gmail",
                    "external_id": "msg-provider-1",
                    "payload": {
                        "google_message_id": "msg-provider-1",
                        "rfc_message_id": "<rfc@example.com>",
                    },
                    "status": "sent",
                }
            )
        )
        with (
            patch(
                "app.workflows.action_executor._integration_allowed_for_action",
                return_value=True,
            ),
            patch("app.workflows.action_executor.is_integration_configured", return_value=True),
            patch(
                "app.workflows.action_executor.get_integration_connection_config",
                return_value={"configured": True},
            ),
            patch("app.workflows.action_executor.get_integration_adapter", return_value=adapter),
            patch(
                "app.workflows.action_approval_resolution.finalize_email_approval_resolution",
            ) as finalize_mock,
        ):
            result = resolve_per_action_approval(db, target, approved=True, actor="op")
        db.commit()

        assert result.approval_state == "approved"
        assert count_pending_approvals_for_job(updated, db=db) == 0
        finalize_mock.assert_called_once()
        adapter.execute_action.assert_called_once()

        records = DecisionRecordRepository.list_for_job(db, tenant_id=tenant_id, job_id=job.job_id)
        resolutions = [r for r in records if r.record_type == "action_approval_resolution"]
        intents = [r for r in records if r.record_type == "execution_intent"]
        outcomes = [r for r in records if r.record_type == "execution_outcome"]
        assert len(resolutions) == 1
        assert len(intents) == 1
        assert len(outcomes) == 1
        assert intents[0].action_operation_id == operation_id
        assert outcomes[0].action_operation_id == operation_id
        assert outcomes[0].metadata_json.get("provider_message_id") == "msg-provider-1"
        assert outcomes[0].metadata_json.get("adapter_recipient") == "anna@example.com"

    def test_db_and_service_pending_count_match(self):
        db = _sqlite_session()
        tenant_id = "T_PARITY"
        _seed_tenant(db, tenant_id, allowed_integrations=["google_mail"])
        job = _tbsm01_lead_job(tenant_id)
        _seed_job_record(db, job)
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)
        updated = process_action_dispatch_job(job, db=db, trace=trace)
        service_count = count_pending_approvals_for_job(updated, db=db)
        repo_count = ApprovalRequestRepository.count_pending_for_job(
            db, tenant_id=tenant_id, job_id=job.job_id,
        )
        assert service_count == repo_count == 1


class TestTBSM04RejectLifecycle:
    def test_reject_leaves_zero_pending_without_intent_or_outcome(self):
        db = _sqlite_session()
        tenant_id = "T_REJECT"
        job_id = str(uuid.uuid4())
        operation_id = str(uuid.uuid4())
        delivery = {
            "type": "send_customer_auto_reply",
            "to": "anna@example.com",
            "subject": "Hej",
            "body": "Tack",
            "tenant_id": tenant_id,
        }
        now = datetime.now(timezone.utc)
        db.add(
            JobRecord(
                job_id=job_id,
                tenant_id=tenant_id,
                job_type="lead",
                status=JobStatus.AWAITING_APPROVAL.value,
                input_data={},
                result={"processor_history": []},
                created_at=now,
                updated_at=now,
            )
        )
        job = Job(job_id=job_id, tenant_id=tenant_id, job_type=JobType.LEAD, input_data={})
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)
        action = dict(delivery)
        action["_action_operation_id"] = operation_id
        record_action_authorization(
            db, trace, job, action, authorization="approval_required",
        )
        approval_id = f"eml_{uuid.uuid4().hex[:12]}"
        db.add(
            ApprovalRequestRecord(
                approval_id=approval_id,
                tenant_id=tenant_id,
                job_id=job_id,
                job_type="lead",
                state="pending",
                channel="dashboard",
                title="Reply",
                summary="Pending",
                next_on_approve="action_execute",
                request_payload={
                    "approval_id": approval_id,
                    "action_operation_id": operation_id,
                },
                delivery_payload=delivery,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        approval = db.get(ApprovalRequestRecord, approval_id)

        with patch(
            "app.workflows.email_approval_resolution.finalize_email_approval_resolution",
        ):
            resolve_per_action_approval(db, approval, approved=False, actor="op")
        db.commit()

        assert ApprovalRequestRepository.count_pending_for_job(
            db, tenant_id=tenant_id, job_id=job_id,
        ) == 0
        records = DecisionRecordRepository.list_for_job(db, tenant_id=tenant_id, job_id=job_id)
        assert not any(r.record_type == "execution_intent" for r in records)
        assert not any(r.record_type == "execution_outcome" for r in records)


class TestLegacyJobLevelSuperseded:
    def test_materialization_cancels_legacy_job_level_without_intent(self):
        db = _sqlite_session()
        tenant_id = "T_LEGACY"
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        legacy_id = f"job_{uuid.uuid4().hex[:12]}"
        db.add(
            JobRecord(
                job_id=job_id,
                tenant_id=tenant_id,
                job_type="lead",
                status=JobStatus.AWAITING_APPROVAL.value,
                input_data={
                    "subject": "Offert solceller",
                    "message_text": "Hej, jag vill ha offert.",
                    "sender": {"name": "Anna", "email": "anna@example.com"},
                    "live_eval": _live_eval_snapshot(tenant_id),
                },
                result={"processor_history": []},
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ApprovalRequestRecord(
                approval_id=legacy_id,
                tenant_id=tenant_id,
                job_id=job_id,
                job_type="lead",
                state="pending",
                channel="dashboard",
                title="Job approval",
                summary="Legacy",
                next_on_approve="action_dispatch",
                request_payload={"approval_id": legacy_id},
                delivery_payload={},
                created_at=now,
                updated_at=now,
            )
        )
        _seed_tenant(db, tenant_id, allowed_integrations=["google_mail"])
        job = Job(
            job_id=job_id,
            tenant_id=tenant_id,
            job_type=JobType.LEAD,
            input_data={
                "subject": "Offert solceller",
                "message_text": "Hej, jag vill ha offert.",
                "sender": {"name": "Anna", "email": "anna@example.com"},
                "live_eval": _live_eval_snapshot(tenant_id),
            },
        )
        job.processor_history = [
            {
                "processor": "policy_processor",
                "result": {
                    "payload": {
                        "decision": "send_for_approval",
                        "detected_job_type": "lead",
                    }
                },
            }
        ]
        approval_request = build_approval_request(job)
        job = append_processor_result(
            job,
            "human_handoff_processor",
            {"status": "completed", "payload": {"approval_request": approval_request}},
        )

        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={
                "followups_enabled": True,
                "auto_actions": {"lead": "manual"},
                "internal_notification_email": "",
            },
        ):
            dispatch_approval_request(db, job)

        rows = ApprovalRequestRepository.list_for_job(db, tenant_id=tenant_id, job_id=job_id)
        legacy = db.get(ApprovalRequestRecord, legacy_id)
        assert legacy.state == "rejected"
        assert legacy.resolution_note == "superseded_by_per_action_approval"
        per_action = [r for r in rows if r.next_on_approve == "action_execute"]
        assert len(per_action) == 1
        records = DecisionRecordRepository.list_for_job(db, tenant_id=tenant_id, job_id=job_id)
        assert not any(r.record_type == "execution_intent" for r in records)

    def test_dispatch_skips_job_level_upsert_when_per_action_in_db(self):
        db = _sqlite_session()
        tenant_id = "T_NO_JOB_LEVEL"
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        per_action_id = f"eml_{uuid.uuid4().hex[:12]}"
        db.add(
            JobRecord(
                job_id=job_id,
                tenant_id=tenant_id,
                job_type="lead",
                status=JobStatus.AWAITING_APPROVAL.value,
                input_data={},
                result={"processor_history": []},
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ApprovalRequestRecord(
                approval_id=per_action_id,
                tenant_id=tenant_id,
                job_id=job_id,
                job_type="lead",
                state="pending",
                channel="dashboard",
                title="Per-action",
                summary="Reply",
                next_on_approve="action_execute",
                request_payload={"action_operation_id": str(uuid.uuid4())},
                delivery_payload={"type": "send_customer_auto_reply", "to": "a@b.com"},
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        job = Job(job_id=job_id, tenant_id=tenant_id, job_type=JobType.LEAD, input_data={})
        job = append_processor_result(
            job,
            "human_handoff_processor",
            {
                "status": "completed",
                "payload": {"approval_request": build_approval_request(job)},
            },
        )
        dispatch_approval_request(db, job)
        rows = ApprovalRequestRepository.list_for_job(db, tenant_id=tenant_id, job_id=job_id)
        assert len(rows) == 1
        assert rows[0].approval_id == per_action_id
        assert not any(r.next_on_approve == "action_dispatch" for r in rows)


class TestMaterializationIdempotency:
    def test_dispatcher_skips_re_materialization_when_processor_pending(self):
        db = _sqlite_session()
        tenant_id = "T_IDEM"
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        per_action_id = f"eml_{uuid.uuid4().hex[:12]}"
        db.add(
            JobRecord(
                job_id=job_id,
                tenant_id=tenant_id,
                job_type="lead",
                status=JobStatus.AWAITING_APPROVAL.value,
                input_data={"live_eval": _live_eval_snapshot(tenant_id)},
                result={"processor_history": []},
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            ApprovalRequestRecord(
                approval_id=per_action_id,
                tenant_id=tenant_id,
                job_id=job_id,
                job_type="lead",
                state="pending",
                channel="dashboard",
                title="Reply",
                summary="Pending",
                next_on_approve="action_execute",
                request_payload={"action_operation_id": str(uuid.uuid4())},
                delivery_payload={"type": "send_customer_auto_reply", "to": "a@b.com"},
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        job = Job(
            job_id=job_id,
            tenant_id=tenant_id,
            job_type=JobType.LEAD,
            input_data={"live_eval": _live_eval_snapshot(tenant_id)},
        )
        job = append_processor_result(
            job,
            "action_dispatch_processor",
            {
                "status": "completed",
                "payload": {
                    "actions_pending_approval": [{"approval_id": per_action_id}],
                    "pending_approval_count": 1,
                },
            },
        )
        job = append_processor_result(
            job,
            "human_handoff_processor",
            {
                "status": "completed",
                "payload": {"approval_request": build_approval_request(job)},
            },
        )
        dispatch_approval_request(db, job)
        rows = ApprovalRequestRepository.list_for_job(db, tenant_id=tenant_id, job_id=job_id)
        assert len(rows) == 1
        assert rows[0].approval_id == per_action_id
