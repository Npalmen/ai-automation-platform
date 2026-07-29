"""Shadow evaluation helpers — flag patching and intake adapters."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

from app.core.settings import get_settings
from app.domain.workflows.models import Job, JobType, JobStatus
from app.services.shadow_intake_boundary import MockIntakeMessage, process_job_through_extraction, process_mock_intake


@contextmanager
def shadow_eval_flags(tenant_id: str) -> Iterator[None]:
    env = {
        "END_CUSTOMER_SHADOW_INTAKE_ENABLED": "true",
        "END_CUSTOMER_SHADOW_MATCHING_ENABLED": "true",
        "END_CUSTOMER_SHADOW_PROMOTION_ENABLED": "true",
        "END_CUSTOMER_SHADOW_TENANT_ALLOWLIST": tenant_id,
        "END_CUSTOMER_READ_API_ENABLED": "true",
        "END_CUSTOMER_WRITE_API_ENABLED": "true",
    }
    previous = {key: os.environ.get(key) for key in env}
    try:
        os.environ.update(env)
        get_settings.cache_clear()
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()


def act_shadow_intake(ctx, db, *, message: MockIntakeMessage, confidence: float = 0.85, run_matching: bool = True):
    ctx.production_actions.append("shadow.process_mock_intake")
    if ctx.campaign is not None:
        message.campaign_run_id = ctx.campaign.campaign_run_id
        message.scenario_execution_id = f"{ctx.scenario_id}/1"
    if getattr(ctx, "pipeline_mode", False):
        job = Job(
            job_id=message.message_id,
            tenant_id=message.tenant_id,
            job_type=JobType.LEAD,
            status=JobStatus.PENDING,
            input_data={
                "message_id": message.message_id,
                "thread_id": message.thread_id,
                "subject": message.subject,
                "message_text": message.message_text,
                "sender_email": message.sender_email,
                "sender_name": message.sender_name,
                "sender_phone": message.sender_phone,
                "reply_to_email": message.reply_to_email,
                "_eval_confidence": confidence,
            },
            result={},
        )
        return process_job_through_extraction(
            db,
            job,
            run_matching=run_matching,
            campaign_run_id=message.campaign_run_id,
            scenario_execution_id=message.scenario_execution_id,
        )
    return process_mock_intake(db, message, confidence=confidence, run_matching=run_matching)

