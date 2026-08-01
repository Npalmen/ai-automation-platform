"""Hermetic PTB-SEM-0024 regression and inbox quality current-truth tests (Todo A/B)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.profile_testbot.generator.profile_generator import generate_semi_auto_campaign
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.workflows.processors.action_dispatch_processor import process_action_dispatch_job
from app.workflows.processors.classification_processor import process_classification_job
from app.workflows.processors.intake_processor import process_universal_intake_job
from app.workflows.processors.policy_processor import process_policy_job
from app.workflows.threat_assessment import assess_threat

LIVE_EVAL_TENANT = "TENANT_LIVE_EVAL"


def _sqlite_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    for table in (
        JobRecord.__table__,
        ApprovalRequestRecord.__table__,
        TenantConfigRecord.__table__,
        ActionExecutionRecord.__table__,
    ):
        table.create(engine, checkfirst=True)
    return sessionmaker(bind=engine)()


def _append_processor(job: Job, processor: str, payload: dict) -> Job:
    job.processor_history = list(job.processor_history or [])
    job.processor_history.append({"processor": processor, "result": {"payload": payload}})
    job.result = job.processor_history[-1]["result"]
    return job


def _ptb_sem_0024_scenario():
    profile = load_customer_profile("niklas-demo-live-eval-v1")
    return next(
        s for s in generate_semi_auto_campaign(profile, seed=0) if s.scenario_id == "PTB-SEM-0024"
    )


class TestPTBSem0024ThreatBlock:
    def test_threat_assessment_blocks_before_classification(self):
        scenario = _ptb_sem_0024_scenario()
        threat = assess_threat(
            subject=scenario.input.subject,
            body=scenario.input.message_text,
        )
        assert threat.threat_class in ("phishing", "prompt_injection")
        assert threat.customer_draft_allowed is False

    def test_intake_records_threat_assessment(self):
        scenario = _ptb_sem_0024_scenario()
        job = Job(
            tenant_id=LIVE_EVAL_TENANT,
            job_type=JobType.INTAKE,
            input_data={
                "subject": scenario.input.subject,
                "message_text": scenario.input.message_text,
                "sender": {"email": scenario.input.sender_email},
            },
        )
        job = process_universal_intake_job(job)
        threat = job.result["payload"]["threat_assessment"]
        assert threat["customer_draft_allowed"] is False
        assert threat["hard_blockers"]

    def test_pipeline_blocks_customer_draft_for_ptb_sem_0024(self):
        scenario = _ptb_sem_0024_scenario()
        job = Job(
            tenant_id=LIVE_EVAL_TENANT,
            job_type=JobType.POLICY,
            job_id=str(uuid.uuid4()),
            input_data={
                "subject": scenario.input.subject,
                "message_text": scenario.input.message_text,
                "sender": {"email": scenario.input.sender_email},
            },
        )
        job = process_universal_intake_job(job)
        intake_payload = job.result["payload"]

        def _fake_run_ai_step(**kwargs):
            from types import SimpleNamespace

            parsed = SimpleNamespace(
                detected_job_type="lead",
                confidence=0.95,
                reasons=["llm_misclassification"],
            )
            payload = kwargs["success_payload_builder"](parsed)
            result = {
                "status": "completed",
                "summary": "test",
                "payload": payload,
            }
            kwargs["job"].processor_history.append(
                {"processor": kwargs["processor_name"], "result": result}
            )
            kwargs["job"].result = result
            return kwargs["job"]

        with patch(
            "app.workflows.processors.classification_processor.run_ai_step",
            side_effect=_fake_run_ai_step,
        ):
            job = process_classification_job(job)

        classification = job.processor_history[-1]["result"]["payload"]
        assert classification.get("detected_job_type") in ("unknown", "spam")
        assert classification.get("threat_override") is True

        job = _append_processor(
            job,
            "entity_extraction_processor",
            {
                "entities": {"email": scenario.input.sender_email, "requested_service": "price quote"},
                "confidence": 0.95,
                "validation": {"is_valid": False, "issues": ["missing_identity"]},
            },
        )
        job = _append_processor(
            job,
            "lead_processor",
            {"confidence": 0.95, "low_confidence": True},
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
        payload = job.result["payload"]
        assert payload.get("safe_acknowledgement_path") is not True
        assert payload.get("threat_assessment", {}).get("customer_draft_allowed") is False

        db = _sqlite_session()
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
                settings={},
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            JobRecord(
                job_id=job.job_id,
                tenant_id=LIVE_EVAL_TENANT,
                job_type="policy",
                status="processing",
                input_data=job.input_data,
                result={"processor_history": job.processor_history},
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True, "email_signature_name": "Niklas"},
        ), patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
        ) as mock_execute:
            result = process_action_dispatch_job(job, db=db)

        assert result.result["payload"]["pending_approval_count"] == 0
        replies = [
            a for a in result.result["payload"]["actions_requested"]
            if a.get("type") == "send_customer_auto_reply" and not a.get("_skip")
        ]
        assert not replies
        mock_execute.assert_not_called()

        rows = ApprovalRequestRepository.list_for_job(
            db, tenant_id=LIVE_EVAL_TENANT, job_id=job.job_id,
        )
        customer_rows = [
            r for r in rows
            if (r.delivery_payload or {}).get("type") == "send_customer_auto_reply"
        ]
        assert not customer_rows
