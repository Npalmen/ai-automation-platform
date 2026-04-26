from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event
from app.core.settings import get_settings as _get_settings
from app.workflows.dispatchers.auto_dispatch import maybe_auto_dispatch_job
from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.repositories.postgres.job_repository import JobRepository
from app.workflows.approval_dispatcher import dispatch_approval_request
from app.workflows.approval_service import has_pending_approval
from app.workflows.job_runner import WorkflowStepExecutionError, run_job


BASE_PIPELINE = [
    JobType.INTAKE,
    JobType.CLASSIFICATION,
]


POST_CLASSIFICATION_PIPELINES = {
    JobType.INVOICE: [
        JobType.ENTITY_EXTRACTION,
        JobType.INVOICE,
        JobType.POLICY,
        JobType.HUMAN_HANDOFF,
    ],
    JobType.LEAD: [
        JobType.ENTITY_EXTRACTION,
        JobType.LEAD,
        JobType.DECISIONING,
        JobType.POLICY,
        JobType.ACTION_DISPATCH,
        JobType.HUMAN_HANDOFF,
    ],
    JobType.CUSTOMER_INQUIRY: [
        JobType.ENTITY_EXTRACTION,
        JobType.CUSTOMER_INQUIRY,
        JobType.DECISIONING,
        JobType.POLICY,
        JobType.ACTION_DISPATCH,
        JobType.HUMAN_HANDOFF,
    ],
    JobType.UNKNOWN: [
        JobType.POLICY,
        JobType.HUMAN_HANDOFF,
    ],
}


class PipelineExecutionError(Exception):
    def __init__(self, step: JobType, message: str):
        self.step = step
        self.message = message
        super().__init__(f"Pipeline step '{step.value}' failed: {message}")


class WorkflowOrchestrator:
    def __init__(self, db: Session | None):
        self.db = db

    def run(self, job: Job) -> Job:
        current = job.model_copy(deep=True)
        current.status = JobStatus.PROCESSING
        current.updated_at = self._utcnow()
        current = self._persist(current)

        resolved_job_type = current.job_type

        try:
            for step in BASE_PIPELINE:
                current = self._run_step(current, step)

            resolved_job_type = self._detect_job_type(current)

            pipeline = POST_CLASSIFICATION_PIPELINES.get(
                resolved_job_type,
                POST_CLASSIFICATION_PIPELINES[JobType.UNKNOWN],
            )

            for step in pipeline:
                if self._should_skip_step(current, step):
                    continue
                current = self._run_step(current, step)

            return self._finalize_success(current, resolved_job_type)

        except PipelineExecutionError as exc:
            return self._finalize_failure(
                job=current,
                resolved_job_type=resolved_job_type,
                failed_step=exc.step,
                error_message=exc.message,
            )

    def resume_after_approval(self, job: Job) -> Job:
        """
        Resume only the post-approval execution path.
        This must NOT rerun intake/classification/policy or create a new approval.
        """
        current = job.model_copy(deep=True)
        current.status = JobStatus.PROCESSING
        current.updated_at = self._utcnow()
        current = self._persist(current)

        resolved_job_type = self._detect_job_type(current)

        try:
            current = self._run_step(current, JobType.ACTION_DISPATCH)
            return self._finalize_success(current, resolved_job_type)

        except PipelineExecutionError as exc:
            return self._finalize_failure(
                job=current,
                resolved_job_type=resolved_job_type,
                failed_step=exc.step,
                error_message=exc.message,
            )

    def _run_step(self, job: Job, step: JobType) -> Job:
        working_job = job.model_copy(deep=True)
        working_job.job_type = step
        working_job.status = JobStatus.PROCESSING
        working_job.updated_at = self._utcnow()
        working_job = self._persist(working_job)

        self._audit_step_start(working_job, step)

        try:
            processed_job = run_job(working_job, self.db)
        except WorkflowStepExecutionError as exc:
            self._audit_step_failure(working_job, step, exc.message)
            raise PipelineExecutionError(step=step, message=exc.message) from exc
        except Exception as exc:
            self._audit_step_failure(working_job, step, str(exc))
            raise PipelineExecutionError(step=step, message=str(exc)) from exc

        processed_job.status = JobStatus.PROCESSING
        processed_job.updated_at = self._utcnow()
        processed_job = self._persist(processed_job)

        self._audit_step_success(processed_job, step)

        return processed_job

    def _should_skip_step(self, job: Job, step: JobType) -> bool:
        """
        Dynamic routing after policy:
        - approval flow: skip ACTION_DISPATCH, keep HUMAN_HANDOFF
        - manual review flow: skip ACTION_DISPATCH, keep HUMAN_HANDOFF
        - auto execute flow: run ACTION_DISPATCH, then HUMAN_HANDOFF may no-op
        """
        if step != JobType.ACTION_DISPATCH:
            return False

        policy_payload = self._get_latest_processor_payload(job, "policy_processor")
        decision = policy_payload.get("decision")
        recommended_next_step = policy_payload.get("recommended_next_step")

        if decision == "send_for_approval":
            return True

        if decision == "hold_for_review":
            return True

        if recommended_next_step == "awaiting_approval":
            return True

        if recommended_next_step == "manual_review":
            return True

        return False

    def _finalize_success(self, job: Job, resolved_job_type: JobType) -> Job:
        final_job = job.model_copy(deep=True)
        final_job.job_type = resolved_job_type

        action_dispatch_payload = self._get_latest_processor_payload(final_job, "action_dispatch_processor")
        action_dispatch_failed = action_dispatch_payload.get("failed_count", 0) > 0

        if action_dispatch_failed:
            failed_actions = action_dispatch_payload.get("actions_failed", [])
            error_summary = "; ".join(
                f"{f.get('type', 'unknown')}: {f.get('error', 'unknown error')}"
                for f in failed_actions
            )
            return self._finalize_failure(
                job=final_job,
                resolved_job_type=resolved_job_type,
                failed_step=JobType.ACTION_DISPATCH,
                error_message=error_summary or "Action dispatch failed",
            )

        requires_human_review = bool(
            (final_job.result or {}).get("requires_human_review", False)
        )

        if has_pending_approval(final_job):
            final_job.status = JobStatus.AWAITING_APPROVAL
        elif requires_human_review:
            final_job.status = JobStatus.MANUAL_REVIEW
        else:
            final_job.status = JobStatus.COMPLETED

        final_job.updated_at = self._utcnow()
        final_job = self._persist(final_job)

        if final_job.status == JobStatus.AWAITING_APPROVAL:
            final_job = dispatch_approval_request(self.db, final_job)

        if final_job.status == JobStatus.COMPLETED:
            self._maybe_auto_dispatch(final_job)

        self._audit(
            final_job,
            action="workflow_completed",
            details={
                "resolved_job_type": resolved_job_type.value,
                "final_status": final_job.status.value,
                "awaiting_approval": final_job.status == JobStatus.AWAITING_APPROVAL,
            },
        )

        return final_job

    def _maybe_auto_dispatch(self, job: Job) -> None:
        """
        Attempt auto-dispatch after pipeline completes with COMPLETED status.
        Never raises — failures are recorded in audit but do not affect job status.
        """
        if self.db is None:
            return
        try:
            result = maybe_auto_dispatch_job(
                db=self.db,
                tenant_id=job.tenant_id,
                job=job,
                settings=_get_settings(),
            )
            if result.status in ("success", "skipped"):
                return
            # failed — record in audit without touching job status
            self._audit(
                job,
                action="auto_dispatch_failed",
                status="failed",
                details={"reason": result.reason},
            )
        except Exception:
            pass  # auto-dispatch must never crash pipeline

    def _finalize_failure(
        self,
        job: Job,
        resolved_job_type: JobType,
        failed_step: JobType,
        error_message: str,
    ) -> Job:
        failed_job = job.model_copy(deep=True)
        failed_job.job_type = resolved_job_type
        failed_job.status = JobStatus.FAILED
        failed_job.updated_at = self._utcnow()

        failed_job.result = {
            **(failed_job.result or {}),
            "status": "failed",
            "requires_human_review": True,
            "payload": {
                "failed_step": failed_step.value,
                "error": error_message,
            },
        }

        failed_job.processor_history.append(
            {
                "processor": "orchestrator",
                "result": failed_job.result,
            }
        )

        failed_job = self._persist(failed_job)

        self._audit(
            failed_job,
            action="workflow_failed",
            status="failed",
            details={
                "failed_step": failed_step.value,
                "error": error_message,
            },
        )

        return failed_job

    def _detect_job_type(self, job: Job) -> JobType:
        payload = self._get_latest_processor_payload(job, "classification_processor")
        detected = payload.get("detected_job_type", JobType.UNKNOWN.value)

        try:
            return JobType(detected)
        except ValueError:
            return JobType.UNKNOWN

    def _get_latest_processor_payload(
        self,
        job: Job,
        processor_name: str,
    ) -> dict[str, Any]:
        for item in reversed(job.processor_history):
            if item.get("processor") == processor_name:
                result = item.get("result") or {}
                return result.get("payload") or {}
        return {}

    def _persist(self, job: Job) -> Job:
        if self.db is None:
            return job

        return JobRepository.update_job(self.db, job)

    def _audit_step_start(self, job: Job, step: JobType):
        self._audit(job, "step_started", {"step": step.value})

    def _audit_step_success(self, job: Job, step: JobType):
        payload = (job.result or {}).get("payload") or {}

        self._audit(
            job,
            "step_completed",
            {
                "step": step.value,
                "processor": payload.get("processor_name"),
                "confidence": payload.get("confidence"),
                "requires_human_review": (job.result or {}).get("requires_human_review"),
                "approval_requested": bool(payload.get("approval_request")),
                "executed_count": payload.get("executed_count"),
                "failed_count": payload.get("failed_count"),
            },
        )

    def _audit_step_failure(self, job: Job, step: JobType, error: str):
        self._audit(
            job,
            "step_failed",
            {
                "step": step.value,
                "error": error,
            },
            status="failed",
        )

    def _audit(
        self,
        job: Job,
        action: str,
        details: dict[str, Any],
        status: str = "success",
    ):
        if self.db is None:
            return

        create_audit_event(
            db=self.db,
            tenant_id=job.tenant_id,
            category="workflow",
            action=action,
            status=status,
            details={
                "job_id": job.job_id,
                **details,
            },
        )

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)