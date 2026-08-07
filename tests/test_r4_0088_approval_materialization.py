"""Production-equivalent R4 PTB-DCQ-0088 hold→pending approval materialization."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.profile_testbot.qualification.coworker_r4_hold_materialization import (
    apply_r4_0088_hold_materialization_from_job,
    resolve_r4_0088_hold_materialization,
    should_materialize_r4_0088_from_job,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_0088_REVIEWED_BODY_HASH,
    R4_EXECUTE_AI_MODE,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
    R4_LOCKED_REVIEW_ARTIFACT_SHA256,
    R4_TENANT_ID,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_approval_materialization_contract import (
    should_materialize_r3_action_dispatch_despite_hold,
)
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.job_models import JobRecord
from app.workflows.orchestrator import WorkflowOrchestrator
from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session
from app.workflows.processors.action_dispatch_processor import (
    _apply_dispatch_authorization,
    process_action_dispatch_job,
)


def _policy_hold() -> dict:
    return {
        "decision": "hold_for_review",
        "reasons": ["risk:complaint"],
        "risk_categories": ["complaint"],
        "detected_job_type": "customer_inquiry",
        "recommendation": "HOLD",
    }


def _registration_context(**overrides) -> dict:
    base = {
        "candidate_runtime_sha": "b7fd95e075c16feee93a116a6062e402c1fee3df",
        "executor_runtime_sha": "37ca9654358d878d010431bfac207c0f6f7cd3a2",
        "candidate_package_semantic_hash": R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        "human_review_sha256": R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        "planned_gmail_send": True,
        "plan_hash": "locked-plan",
        "reviewed_body_hash": R4_0088_REVIEWED_BODY_HASH,
        "review_status": "PASS",
        "renderer_type": "constrained_llm_v1",
        "model_id": "locked-model",
        "prompt_version": "locked-prompt",
        "automatic_gmail": False,
        "production_activation": False,
        "probe": False,
    }
    base.update(overrides)
    return base


def _r4_0088_job(**reg_overrides) -> Job:
    return Job(
        job_id=str(uuid.uuid4()),
        tenant_id=R4_TENANT_ID,
        job_type=JobType.CUSTOMER_INQUIRY,
        input_data={
            "subject": "Re: reklamation",
            "message_text": "Jag vill reklamera.",
            "live_eval": {
                "evaluation_run_id": str(uuid.uuid4()),
                "tenant_id": R4_TENANT_ID,
                "scenario_id": "PTB-DCQ-0088",
                "attempt_id": 1,
                "transport_mode": "live_gmail",
                "ai_mode": R4_EXECUTE_AI_MODE,
                "campaign_type": R4_LIVE_QUALITY_CAMPAIGN_TYPE,
                "execution_mode": R4_EXECUTION_MODE,
                "config_hash": "cfg",
                "trusted": True,
                "registration_context": _registration_context(**reg_overrides),
            },
        },
        processor_history=[
            {"processor": "policy_processor", "result": {"payload": _policy_hold()}}
        ],
    )


def _sqlite_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    JobRecord.__table__.create(engine, checkfirst=True)
    ApprovalRequestRecord.__table__.create(engine, checkfirst=True)
    DecisionRecordRow.__table__.create(engine, checkfirst=True)
    AuditEventRecord.__table__.create(engine, checkfirst=True)
    ActionExecutionRecord.__table__.create(engine, checkfirst=True)

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


def _seed_job_record(db, job: Job) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        JobRecord(
            job_id=job.job_id,
            tenant_id=job.tenant_id,
            job_type="customer_inquiry",
            status="processing",
            input_data=job.input_data,
            result={"processor_history": job.processor_history},
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def _customer_reply_action(job: Job) -> dict:
    return {
        "type": "send_customer_auto_reply",
        "tenant_id": job.tenant_id,
        "to": "recipient@eval.test",
        "subject": "Re: reklamation",
        "body": "placeholder",
    }


class TestR40088ProductionPath:
    def test_orchestrator_allows_dispatch_from_registration_context(self):
        job = _r4_0088_job()
        orch = WorkflowOrchestrator(db=None)
        assert orch._should_skip_step(job, JobType.ACTION_DISPATCH) is False

    def test_dispatch_authorization_materializes_r4_0088(self):
        job = _r4_0088_job()
        settings = {
            "auto_actions": {"customer_inquiry": "manual"},
            "internal_notification_email": "ops@example.com",
            "followups_enabled": True,
        }
        actions = _apply_dispatch_authorization(
            job,
            [_customer_reply_action(job)],
            settings,
            db=None,
        )
        action = actions[0]
        assert action.get("_r4_0088_materialized") is True
        assert action.get("_needs_approval") is True
        assert action.get("_authorization") == "approval_required"
        assert action.get("_skip") is False

    def test_action_dispatch_creates_pending_approval_and_bind_lookup(self):
        db = _sqlite_session()
        job = _r4_0088_job()
        _seed_job_record(db, job)
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)
        with (
            patch(
                "app.workflows.processors.action_dispatch_processor._read_automation_settings",
                return_value={
                    "followups_enabled": True,
                    "auto_actions": {"customer_inquiry": "manual"},
                    "internal_notification_email": "ops@example.com",
                },
            ),
            patch(
                "app.workflows.processors.action_dispatch_processor._resolve_actions",
                return_value=[_customer_reply_action(job)],
            ),
        ):
            updated = process_action_dispatch_job(job, db=db, trace=trace)

        payload = updated.result["payload"]
        assert payload["pending_approval_count"] == 1
        rows = ApprovalRequestRepository.list_for_job(
            db, tenant_id=job.tenant_id, job_id=job.job_id
        )
        assert len(rows) == 1
        assert rows[0].state == "pending"
        assert rows[0].next_on_approve in ("action_execute", "email_send")
        target = next(
            (
                row
                for row in rows
                if row.state == "pending"
                and row.next_on_approve in ("action_execute", "email_send")
            ),
            None,
        )
        assert target is not None


@pytest.mark.parametrize(
    "reg_overrides",
    [
        {"reviewed_body_hash": "deadbeef"},
        {"candidate_package_semantic_hash": "deadbeef"},
        {"human_review_sha256": "deadbeef"},
    ],
)
def test_negative_controls_remain_hold(reg_overrides):
    job = _r4_0088_job(**reg_overrides)
    policy = _policy_hold()
    assert not should_materialize_r4_0088_from_job(job=job, policy_payload=policy)
    action = apply_r4_0088_hold_materialization_from_job(
        job=job,
        action=_customer_reply_action(job),
        policy_payload=policy,
    )
    assert action.get("_r4_0088_materialized") is not True


def test_wrong_scenario_remains_hold():
    job = _r4_0088_job()
    job.input_data["live_eval"]["scenario_id"] = "PTB-DCQ-0000"
    policy = _policy_hold()
    assert not should_materialize_r4_0088_from_job(job=job, policy_payload=policy)


def test_wrong_campaign_context_remains_hold():
    job = _r4_0088_job()
    job.input_data["live_eval"]["campaign_type"] = "other_campaign"
    policy = _policy_hold()
    assert not should_materialize_r4_0088_from_job(job=job, policy_payload=policy)


def test_blocked_risk_remains_hold():
    job = _r4_0088_job()
    policy = {
        **_policy_hold(),
        "risk_categories": ["legal"],
    }
    assert not should_materialize_r4_0088_from_job(job=job, policy_payload=policy)


def test_ordinary_production_hold_unchanged():
    job = SimpleNamespace(
        job_id="prod-job",
        tenant_id="TENANT_PRODUCTION_PILOT_01",
        input_data={},
    )
    policy = _policy_hold()
    assert not should_materialize_r4_0088_from_job(job=job, policy_payload=policy)
    orch = WorkflowOrchestrator(db=None)
    job_model = Job(
        job_id="prod-job",
        tenant_id="TENANT_PRODUCTION_PILOT_01",
        job_type=JobType.CUSTOMER_INQUIRY,
        input_data={},
        processor_history=[
            {"processor": "policy_processor", "result": {"payload": policy}}
        ],
    )
    assert orch._should_skip_step(job_model, JobType.ACTION_DISPATCH) is True


def test_r3_regression_r4_context_not_materialized_by_r3():
    job = _r4_0088_job()
    assert not should_materialize_r3_action_dispatch_despite_hold(
        job=job,
        db=None,
        policy_payload=_policy_hold(),
    )


def test_never_execution_allowed():
    res = resolve_r4_0088_hold_materialization(
        scenario_id="PTB-DCQ-0088",
        base_authorization="hold_for_review",
        reviewed_body_hash=R4_0088_REVIEWED_BODY_HASH,
        candidate_package_semantic_hash=R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        human_review_artifact_hash=R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        execution_mode=R4_EXECUTION_MODE,
        ai_mode=R4_EXECUTE_AI_MODE,
        tenant_id=R4_TENANT_ID,
    )
    assert res.authorization == "approval_required"
    assert res.details.get("never_execution_allowed") is True
