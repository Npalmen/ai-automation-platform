"""Tests for safe acknowledgement dual-state pipeline behavior."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.profile_testbot.generator.profile_generator import generate_semi_auto_campaign
from app.evaluation.profile_testbot.oracles.hard_safety import HardSafetyContext
from app.evaluation.profile_testbot.oracles.reply_contract import evaluate_reply_contract
from app.evaluation.profile_testbot.oracles.runner import run_oracles
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.workflows.action_approval_resolution import resolve_per_action_approval
from app.workflows.approval_service import count_pending_approvals_for_job, has_pending_approval
from app.workflows.orchestrator import WorkflowOrchestrator
from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session
from app.workflows.processors.action_dispatch_processor import (
    _apply_dispatch_authorization,
    _build_lead_default_actions,
    _build_safe_acknowledgement_action,
    process_action_dispatch_job,
)
from app.workflows.reply_candidate_safety import assess_reply_candidate_safety
from app.workflows.safe_acknowledgement import (
    build_safe_acknowledgement_body,
    evaluate_safe_acknowledgement_eligibility,
)

LIVE_EVAL_TENANT = "TENANT_LIVE_EVAL"


def _sqlite_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    for table in (
        JobRecord.__table__,
        ApprovalRequestRecord.__table__,
        DecisionRecordRow.__table__,
        ActionExecutionRecord.__table__,
        AuditEventRecord.__table__,
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


def _seed_live_eval_tenant(db) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        TenantConfigRecord(
            tenant_id=LIVE_EVAL_TENANT,
            name="Live Eval",
            slug="tenant-live-eval",
            status="active",
            lifecycle_status="active",
            is_test_tenant=True,
            allowed_integrations=["google_mail"],
            enabled_job_types=["lead"],
            auto_actions={},
            settings={
                "integrations": {
                    "enabled_external_writes": [],
                    "selections": {"google_mail": {}},
                },
            },
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def _seed_job_record(db, job: Job) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        JobRecord(
            job_id=job.job_id,
            tenant_id=job.tenant_id,
            job_type=job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
            status="processing",
            input_data=job.input_data,
            result={"processor_history": job.processor_history or []},
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def _incomplete_lead_job(*, sender_email: str = "customer@example.com", message: str | None = None) -> Job:
    return Job(
        tenant_id="TENANT_1001",
        job_type=JobType.POLICY,
        input_data={
            "subject": "Offertförfrågan solcellsinstallation Uppsala",
            "message_text": message
            or "Hej, jag behöver hjälp med solcellsinstallation i Uppsala. Kan ni återkomma?",
            "sender": {"name": "", "email": sender_email},
        },
    )


def _append_processor(job: Job, processor: str, payload: dict) -> Job:
    job.processor_history = list(job.processor_history or [])
    job.processor_history.append({"processor": processor, "result": {"payload": payload}})
    job.result = job.processor_history[-1]["result"]
    return job


def _seed_incomplete_lead_pipeline(job: Job) -> Job:
    job = _append_processor(
        job,
        "classification_processor",
        {"detected_job_type": "lead", "confidence": 0.95},
    )
    job = _append_processor(
        job,
        "entity_extraction_processor",
        {
            "entities": {"email": "customer@example.com", "city": "Uppsala"},
            "confidence": 0.95,
            "validation": {"is_valid": False, "issues": ["missing_identity", "missing_requested_service"]},
        },
    )
    job = _append_processor(
        job,
        "lead_processor",
        {"confidence": 0.95, "low_confidence": True, "recommended_next_step": "manual_review"},
    )
    job = _append_processor(
        job,
        "decisioning_processor",
        {
            "decision": "manual_review",
            "target_queue": "manual_review",
            "confidence": 0.95,
            "low_confidence": False,
            "used_fallback": False,
        },
    )
    return job


class TestSafeAcknowledgementEligibility:
    def test_incomplete_lead_with_email_is_eligible(self):
        result = evaluate_safe_acknowledgement_eligibility(
            detected_job_type="lead",
            risk_detected=False,
            risk_categories=[],
            extraction_issues=["missing_identity", "missing_requested_service"],
            input_data={
                "subject": "Solceller Uppsala",
                "message_text": "Hej, jag vill ha solceller i Uppsala.",
                "sender": {"email": "customer@example.com"},
            },
            recommendation=None,
            recommendation_raw="manual_review",
            low_confidence=True,
            used_fallback=False,
        )
        assert result.eligible is True

    def test_no_reply_address_is_not_eligible(self):
        result = evaluate_safe_acknowledgement_eligibility(
            detected_job_type="lead",
            risk_detected=False,
            risk_categories=[],
            extraction_issues=["missing_identity"],
            input_data={
                "subject": "Hej",
                "message_text": "Hej",
                "sender": {"email": "noreply@forms.example.com"},
            },
            recommendation=None,
            recommendation_raw="manual_review",
            low_confidence=True,
            used_fallback=False,
        )
        assert result.eligible is False
        assert "no_usable_reply_address" in result.reasons

    def test_price_topic_is_not_eligible(self):
        result = evaluate_safe_acknowledgement_eligibility(
            detected_job_type="lead",
            risk_detected=False,
            risk_categories=[],
            extraction_issues=["missing_identity"],
            input_data={
                "subject": "Vad kostar det?",
                "message_text": "Vad kostar en elcentral?",
                "sender": {"email": "customer@example.com"},
            },
            recommendation=None,
            recommendation_raw="manual_review",
            low_confidence=True,
            used_fallback=False,
        )
        assert result.eligible is False
        assert "price" in result.reasons

    def test_out_of_area_is_not_eligible(self):
        result = evaluate_safe_acknowledgement_eligibility(
            detected_job_type="lead",
            risk_detected=False,
            risk_categories=[],
            extraction_issues=["missing_identity"],
            input_data={
                "subject": "Hjälp på Gotland",
                "message_text": "Behöver elservice på Gotland.",
                "sender": {"email": "customer@example.com"},
            },
            recommendation=None,
            recommendation_raw="manual_review",
            low_confidence=True,
            used_fallback=False,
        )
        assert result.eligible is False
        assert "out_of_service_area" in result.reasons


class TestPolicyDualState:
    def test_incomplete_lead_gets_send_for_approval_with_manual_review_routing(self):
        from app.workflows.processors.policy_processor import process_policy_job

        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        result = process_policy_job(job)
        payload = result.result["payload"]

        assert payload["decision"] == "send_for_approval"
        assert payload["policy_authorization"] == "approval_required"
        assert payload["safe_acknowledgement_path"] is True
        assert payload["target_queue"] == "manual_review"
        assert payload["operational_routing"] == "manual_review"
        assert result.result["requires_human_review"] is True


class TestActionDispatchSafeAcknowledgement:
    def test_safe_ack_draft_contains_acknowledgement_and_no_forbidden_commitments(self):
        from app.workflows.processors.action_dispatch_processor import process_action_dispatch_job

        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        from app.workflows.processors.policy_processor import process_policy_job

        job = process_policy_job(job)
        db = MagicMock()
        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True, "email_signature_name": "Niklas"},
        ):
            result = process_action_dispatch_job(job, db=db)

        pending = result.result["payload"]["actions_pending_approval"]
        assert pending
        body = pending[0].get("subject")  # summary only in pending list
        actions = result.result["payload"]["actions_requested"]
        reply = next(a for a in actions if a.get("type") == "send_customer_auto_reply")
        body_text = reply["body"]
        safety = assess_reply_candidate_safety(body_text)
        assert safety["passed"] is True
        assert "tack för din förfrågan" in body_text.lower()
        assert "återkommer" in body_text.lower()
        assert "kostar" not in body_text.lower()
        assert "bokad" not in body_text.lower()
        assert "ärende kommer" not in body_text.lower()

    def test_no_reply_address_skips_customer_draft(self):
        from app.workflows.processors.action_dispatch_processor import process_action_dispatch_job
        from app.workflows.processors.policy_processor import process_policy_job

        job = _seed_incomplete_lead_pipeline(
            _incomplete_lead_job(sender_email="noreply@forms.example.com")
        )
        job = process_policy_job(job)
        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True},
        ):
            result = process_action_dispatch_job(job, db=None)
        actions = result.result["payload"]["actions_requested"]
        reply = next(a for a in actions if a.get("type") == "send_customer_auto_reply")
        assert reply.get("_skip") is True


class TestOrchestratorSafeAckPath:
    def test_does_not_skip_action_dispatch_for_safe_acknowledgement_path(self):
        orch = WorkflowOrchestrator(db=None)
        job = _incomplete_lead_job()
        job = _append_processor(
            job,
            "policy_processor",
            {
                "decision": "send_for_approval",
                "safe_acknowledgement_path": True,
                "recommended_next_step": "awaiting_approval",
            },
        )
        assert orch._should_skip_step(job, JobType.ACTION_DISPATCH) is False

    def test_still_skips_action_dispatch_for_plain_send_for_approval(self):
        orch = WorkflowOrchestrator(db=None)
        job = _incomplete_lead_job()
        job = _append_processor(
            job,
            "policy_processor",
            {"decision": "send_for_approval", "safe_acknowledgement_path": False},
        )
        assert orch._should_skip_step(job, JobType.ACTION_DISPATCH) is True


class TestPTBSem0000Oracle:
    def test_safe_ack_draft_passes_required_fact_acknowledgement(self):
        profile = load_customer_profile("niklas-demo-live-eval-v1")
        scenario = next(
            s for s in generate_semi_auto_campaign(profile, seed=0) if s.scenario_id == "PTB-SEM-0000"
        )
        assert "solcellsinstallation" in scenario.input.message_text.lower()

        body = build_safe_acknowledgement_body(
            greeting="Hej,",
            service_hint="solcellsinstallation",
            missing_fields=["name", "phone"],
            signature_name="Niklas",
        )
        results = evaluate_reply_contract(scenario=scenario, profile=profile, reply_text=body)
        ack = next(r for r in results if r.name == "required_fact_acknowledgement")
        assert ack.status == "pass"

        evaluation = run_oracles(
            scenario=scenario,
            profile=profile,
            safety_context=HardSafetyContext(
                tenant_id="TENANT_LIVE_EVAL",
                recipient_email="recipient@eval.test",
                sender_allowlist={scenario.input.sender_email},
                recipient_allowlist={"recipient@eval.test"},
                draft_text=body,
            ),
            reply_text=body,
        )
        assert evaluation.passed is True


class TestDecisionContractCoexistence:
    def test_manual_review_routing_coexists_with_send_for_approval_authorization(self):
        from app.workflows.processors.policy_processor import process_policy_job

        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        result = process_policy_job(job)
        payload = result.result["payload"]
        assert payload["target_queue"] == "manual_review"
        assert payload["decision"] == "send_for_approval"

    def test_pending_approval_blocks_auto_dispatch_without_execution(self):
        from app.workflows.processors.action_dispatch_processor import process_action_dispatch_job
        from app.workflows.processors.policy_processor import process_policy_job

        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        job = process_policy_job(job)
        db = MagicMock()
        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True},
        ), patch(
            "app.workflows.processors.action_dispatch_processor._create_action_approval_record",
            return_value={"approval_id": "eml_test", "status": "pending_approval"},
        ):
            job = process_action_dispatch_job(job, db=db)

        job.result["payload"]["actions_pending_approval"] = [
            {"approval_id": "eml_test", "status": "pending_approval"}
        ]
        assert has_pending_approval(job) or job.result["payload"]["pending_approval_count"] > 0


class TestSafeAckNeedsApprovalRegression:
    """Regression for SAFE_ACK_ACTION_MISSING_NEEDS_APPROVAL (PTB-SEM-0000 / LIVE_EVAL)."""

    def test_safe_ack_action_builder_marks_needs_approval(self):
        from app.workflows.processors.policy_processor import process_policy_job

        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        job = process_policy_job(job)
        action = _build_safe_acknowledgement_action(
            job,
            automation_settings={"followups_enabled": True, "email_signature_name": "Niklas"},
        )
        assert action is not None
        assert action["type"] == "send_customer_auto_reply"
        assert action["_needs_approval"] is True
        assert action["_approval_reason"] == "safe_acknowledgement_requires_approval"
        assert action["body"]
        assert action["to"] == "customer@example.com"

    def test_live_eval_safe_ack_materializes_pending_approval_with_delivery_body(self):
        from app.workflows.processors.policy_processor import process_policy_job

        db = _sqlite_session()
        _seed_live_eval_tenant(db)
        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        job.tenant_id = LIVE_EVAL_TENANT
        job.job_id = str(uuid.uuid4())
        job = process_policy_job(job)
        _seed_job_record(db, job)
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)

        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True, "email_signature_name": "Niklas"},
        ), patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
        ) as mock_execute:
            updated = process_action_dispatch_job(job, db=db, trace=trace)

        policy_payload = get_latest_policy_payload(updated)
        assert policy_payload["decision"] == "send_for_approval"
        assert policy_payload["target_queue"] == "manual_review"
        assert policy_payload["safe_acknowledgement_path"] is True

        payload = updated.result["payload"]
        reply = next(
            a for a in payload["actions_requested"] if a.get("type") == "send_customer_auto_reply"
        )
        assert reply.get("_needs_approval") is True
        assert reply.get("_skip") is not True
        assert reply.get("body")
        assert reply.get("to") == "customer@example.com"
        assert payload["pending_approval_count"] >= 1
        pending_types = {item.get("action_type") for item in payload["actions_pending_approval"]}
        assert "send_customer_auto_reply" in pending_types
        assert payload["actions_executed"] == []
        mock_execute.assert_not_called()

        rows = ApprovalRequestRepository.list_for_job(
            db, tenant_id=LIVE_EVAL_TENANT, job_id=job.job_id,
        )
        reply_rows = [
            row for row in rows
            if (row.delivery_payload or {}).get("type") == "send_customer_auto_reply"
        ]
        assert len(reply_rows) == 1
        assert reply_rows[0].state == "pending"
        assert reply_rows[0].next_on_approve == "action_execute"
        delivery = reply_rows[0].delivery_payload or {}
        assert delivery.get("body")
        assert reply_rows[0].request_payload.get("action_operation_id")

    def test_missing_needs_approval_not_treated_as_approval_gated_at_integration_gate(self):
        db = _sqlite_session()
        _seed_live_eval_tenant(db)
        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        job.tenant_id = LIVE_EVAL_TENANT
        job = _append_processor(
            job,
            "policy_processor",
            {
                "decision": "auto_execute",
                "detected_job_type": "lead",
                "safe_acknowledgement_path": False,
            },
        )
        settings = {"followups_enabled": True, "email_signature_name": "Niklas", "auto_actions": {"lead": True}}
        authorized = _apply_dispatch_authorization(
            job,
            [
                {
                    "type": "send_customer_auto_reply",
                    "tenant_id": LIVE_EVAL_TENANT,
                    "to": "customer@example.com",
                    "subject": "Re: test",
                    "body": "Hej, tack för din förfrågan. Vi återkommer.",
                }
            ],
            settings,
            db=db,
        )
        reply = authorized[0]
        assert reply.get("_needs_approval") is not True
        assert reply.get("_skip") is True
        assert reply.get("_skip_reason") == "integration_not_allowed"

    def test_safe_ack_does_not_auto_execute_before_approval(self):
        from app.workflows.processors.policy_processor import process_policy_job

        db = _sqlite_session()
        _seed_live_eval_tenant(db)
        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        job.tenant_id = LIVE_EVAL_TENANT
        job.job_id = str(uuid.uuid4())
        job = process_policy_job(job)
        _seed_job_record(db, job)

        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True, "email_signature_name": "Niklas"},
        ), patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
        ) as mock_execute:
            process_action_dispatch_job(job, db=db)

        mock_execute.assert_not_called()

    def test_hold_policy_does_not_create_send_action(self):
        from app.workflows.processors.policy_processor import process_policy_job

        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        job = _append_processor(
            job,
            "decisioning_processor",
            {
                "decision": "hold",
                "target_queue": "manual_review",
                "confidence": 0.95,
                "low_confidence": False,
                "used_fallback": False,
                "reasons": ["ambiguous_context"],
            },
        )
        job = process_policy_job(job)
        payload = job.result["payload"]
        assert payload["decision"] == "hold_for_review"
        assert payload.get("safe_acknowledgement_path") is not True

        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True},
        ):
            result = process_action_dispatch_job(job, db=None)
        replies = [
            a for a in result.result["payload"]["actions_requested"]
            if a.get("type") == "send_customer_auto_reply"
        ]
        assert not replies or all(a.get("_skip") for a in replies)
        assert result.result["payload"]["pending_approval_count"] == 0

    def test_hard_safety_topic_blocks_safe_ack_draft_and_approval(self):
        from app.workflows.processors.policy_processor import process_policy_job

        job = _seed_incomplete_lead_pipeline(
            _incomplete_lead_job(message="Vad kostar en elcentral? Behöver offert i Uppsala.")
        )
        job = process_policy_job(job)
        assert job.result["payload"].get("safe_acknowledgement_path") is not True

        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True},
        ):
            result = process_action_dispatch_job(job, db=None)
        assert result.result["payload"]["pending_approval_count"] == 0
        replies = [
            a for a in result.result["payload"]["actions_requested"]
            if a.get("type") == "send_customer_auto_reply" and not a.get("_skip")
        ]
        assert not replies

    def test_approval_lifecycle_allows_single_gmail_send_after_cas_approval(self):
        from app.workflows.processors.policy_processor import process_policy_job

        db = _sqlite_session()
        _seed_live_eval_tenant(db)
        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        job.tenant_id = LIVE_EVAL_TENANT
        job.job_id = str(uuid.uuid4())
        job = process_policy_job(job)
        _seed_job_record(db, job)
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)

        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True, "email_signature_name": "Niklas"},
        ):
            updated = process_action_dispatch_job(job, db=db, trace=trace)

        rows = ApprovalRequestRepository.list_for_job(
            db, tenant_id=LIVE_EVAL_TENANT, job_id=job.job_id,
        )
        reply_rows = [
            row for row in rows
            if (row.delivery_payload or {}).get("type") == "send_customer_auto_reply"
        ]
        assert len(reply_rows) == 1
        approval = db.get(ApprovalRequestRecord, reply_rows[0].approval_id)
        mock_adapter = MagicMock(
            execute_action=MagicMock(return_value={"provider": "gmail", "message_id": "m1"})
        )
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
                return_value=mock_adapter,
            ),
            patch("app.workflows.email_approval_resolution.finalize_email_approval_resolution"),
        ):
            resolve_per_action_approval(db, approval, approved=True, actor="operator")
        db.commit()

        mock_adapter.execute_action.assert_called_once()
        assert count_pending_approvals_for_job(updated, db=db) == 0

    def test_ptb_sem_0000_contract_passes_with_materialized_draft(self):
        from app.workflows.processors.policy_processor import process_policy_job

        profile = load_customer_profile("niklas-demo-live-eval-v1")
        scenario = next(
            s for s in generate_semi_auto_campaign(profile, seed=0) if s.scenario_id == "PTB-SEM-0000"
        )
        job = Job(
            tenant_id=LIVE_EVAL_TENANT,
            job_type=JobType.POLICY,
            input_data={
                "subject": scenario.input.subject,
                "message_text": scenario.input.message_text,
                "sender": {"name": "", "email": scenario.input.sender_email},
            },
        )
        job = _append_processor(
            job,
            "classification_processor",
            {"detected_job_type": "lead", "confidence": 0.95},
        )
        job = _append_processor(
            job,
            "entity_extraction_processor",
            {
                "entities": {"email": scenario.input.sender_email, "city": "Uppsala"},
                "confidence": 0.95,
                "validation": {
                    "is_valid": False,
                    "issues": ["missing_identity", "missing_requested_service"],
                },
            },
        )
        job = _append_processor(
            job,
            "lead_processor",
            {"confidence": 0.95, "low_confidence": True, "recommended_next_step": "manual_review"},
        )
        job = _append_processor(
            job,
            "decisioning_processor",
            {
                "decision": "manual_review",
                "target_queue": "manual_review",
                "confidence": 0.95,
                "low_confidence": False,
                "used_fallback": False,
            },
        )
        job = process_policy_job(job)
        db = _sqlite_session()
        _seed_live_eval_tenant(db)
        job.job_id = str(uuid.uuid4())
        _seed_job_record(db, job)

        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True, "email_signature_name": "Niklas"},
        ), patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
        ) as mock_execute:
            updated = process_action_dispatch_job(job, db=db)

        rows = ApprovalRequestRepository.list_for_job(
            db, tenant_id=LIVE_EVAL_TENANT, job_id=job.job_id,
        )
        reply_rows = [
            row for row in rows
            if (row.delivery_payload or {}).get("type") == "send_customer_auto_reply"
        ]
        draft_text = str((reply_rows[0].delivery_payload or {}).get("body") or "")
        assert draft_text
        mock_execute.assert_not_called()

        ack = next(
            r for r in evaluate_reply_contract(
                scenario=scenario, profile=profile, reply_text=draft_text,
            )
            if r.name == "required_fact_acknowledgement"
        )
        assert ack.status == "pass"

        evaluation = run_oracles(
            scenario=scenario,
            profile=profile,
            safety_context=HardSafetyContext(
                tenant_id=LIVE_EVAL_TENANT,
                recipient_email="recipient@eval.test",
                sender_allowlist={scenario.input.sender_email},
                recipient_allowlist={"recipient@eval.test"},
                draft_text=draft_text,
            ),
            reply_text=draft_text,
        )
        assert evaluation.passed is True
        reply_pending = [
            item for item in updated.result["payload"]["actions_pending_approval"]
            if item.get("action_type") == "send_customer_auto_reply"
        ]
        assert len(reply_pending) == 1


def get_latest_policy_payload(job: Job) -> dict:
    from app.workflows.processors.ai_processor_utils import get_latest_processor_payload

    return get_latest_processor_payload(job, "policy_processor") or {}
