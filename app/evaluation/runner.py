"""Deterministic evaluation harness runner."""

from __future__ import annotations

import time
import uuid
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.adapter_fakes import (
    eval_get_integration_adapter,
    eval_get_integration_connection_config,
)
from app.evaluation.assertions import evaluate_quality, evaluate_safety
from app.evaluation.db_isolation import unique_eval_tenant_id
from app.evaluation.errors import (
    EXIT_BASELINE_REGRESSION,
    EXIT_FAIL_HARNESS,
    EXIT_FAIL_QUALITY,
    EXIT_FAIL_SAFETY,
    EXIT_PASS,
    FixtureAIError,
    HarnessError,
    QualityFailure,
    SafetyViolation,
)
from app.evaluation.fixture_ai import (
    FixtureAIClient,
    reset_active_prompt_name,
    set_active_prompt_name,
)
from app.evaluation.observations import collect_observation
from app.evaluation.reporting import (
    HarnessRunResult,
    ScenarioResult,
    ScenarioRuntimeObservation,
    normalize_metrics_for_baseline,
)
from app.evaluation.schema.scenario import ScenarioContract
from app.evaluation.scoring import diagnostic_weighted_score, gate_metrics
from app.evaluation.telemetry import reset_telemetry
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.workflows.pipeline_runner import run_pipeline

_AI_STEP_MODULES = (
    "app.workflows.processors.ai_processor_utils",
    "app.workflows.processors.classification_processor",
    "app.workflows.processors.entity_extraction_processor",
    "app.workflows.processors.lead_processor",
    "app.workflows.processors.customer_inquiry_processor",
    "app.workflows.processors.decisioning_processor",
    "app.workflows.processors.invoice_processor",
)


@dataclass
class EvalHarnessRunner:
    run_id: str
    baseline: dict[str, Any] | None = None
    fail_on_regression: bool = False

    def run_scenario(self, db: Session, scenario: ScenarioContract) -> ScenarioResult:
        started = time.perf_counter()
        reset_telemetry()
        tenant_id = unique_eval_tenant_id(scenario.scenario_id, self.run_id)
        violations: list[str] = []
        exit_code = EXIT_PASS
        status = "pass"
        metrics: dict[str, Any] = {}
        diagnostic_score: float | None = None
        regression: dict[str, Any] = {"is_regression": False}
        runtime = ScenarioRuntimeObservation(run_id=self.run_id, llm_mode="deterministic_fixture")

        try:
            self._validate_scenario_contract(scenario)
            job = self._execute(db, scenario, tenant_id)
            obs = collect_observation(db, job)
            runtime.real_external_calls = int(obs.telemetry.get("real_external_calls") or 0)
            runtime.fake_adapter_calls = int(obs.telemetry.get("fake_adapter_calls") or 0)
            runtime.execution_function_calls = int(obs.telemetry.get("execution_function_calls") or 0)
            try:
                evaluate_safety(scenario, obs)
            except SafetyViolation as exc:
                violations.append(str(exc))
                exit_code = EXIT_FAIL_SAFETY
                status = "fail_safety"
            else:
                metrics = evaluate_quality(scenario, obs)
                try:
                    gate_metrics(metrics)
                except QualityFailure as exc:
                    violations.append(str(exc))
                    exit_code = EXIT_FAIL_QUALITY
                    status = "fail_quality"
                else:
                    diagnostic_score = diagnostic_weighted_score(metrics)

            regression = self._compare_baseline(scenario.scenario_id, status, normalize_metrics_for_baseline(metrics))
            if regression.get("is_regression") and self.fail_on_regression:
                exit_code = EXIT_BASELINE_REGRESSION
                status = "baseline_regression"

        except (HarnessError, FixtureAIError) as exc:
            violations.append(str(exc))
            exit_code = EXIT_FAIL_HARNESS
            status = "fail_harness"
        except Exception as exc:
            violations.append(f"unexpected: {exc}")
            exit_code = EXIT_FAIL_HARNESS
            status = "fail_harness"

        duration_ms = int((time.perf_counter() - started) * 1000)
        return ScenarioResult(
            scenario_id=scenario.scenario_id,
            status=status,
            safety_passed=exit_code not in (EXIT_FAIL_SAFETY,),
            safety_violations=violations,
            quality_metrics=metrics,
            normalized_metrics=normalize_metrics_for_baseline(metrics),
            diagnostic_score=diagnostic_score,
            duration_ms=duration_ms,
            exit_code=exit_code,
            regression=regression,
            runtime=runtime,
        )

    def _validate_scenario_contract(self, scenario: ScenarioContract) -> None:
        if scenario.source_mode != "fixture":
            raise HarnessError(
                f"2E runner is fixture-only; got source_mode={scenario.source_mode!r}"
            )
        if scenario.pipeline.pre_seed and "contract_edge" not in scenario.tags and "legacy" not in scenario.tags:
            raise HarnessError(
                "pre_seed requires contract_edge or legacy tag on scenario"
            )

    def _execute(self, db: Session, scenario: ScenarioContract, tenant_id: str) -> Job:
        self._seed_tenant(db, scenario, tenant_id)
        fixture_client = FixtureAIClient(
            scenario.ai.fixtures,
            mode=scenario.ai.mode,
        )

        with self._patches(fixture_client):
            job = self._create_job(db, scenario, tenant_id)
            if scenario.pipeline.pre_seed:
                job.processor_history = list(scenario.pipeline.pre_seed)
            for step in scenario.pipeline.steps:
                job = self._run_step(db, scenario, job, step)
            fixture_client.finalize()
            return job

    def _run_step(self, db: Session, scenario: ScenarioContract, job: Job, step) -> Job:
        run = step.run
        approval_index = step.approval_index
        expect_blocked = step.expect_blocked
        try:
            if run == "pipeline":
                return run_pipeline(job, db)
            if run == "dispatch":
                from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session
                from app.workflows.processors.action_dispatch_processor import process_action_dispatch_job

                trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)
                return process_action_dispatch_job(job, db=db, trace=trace)
            if run == "retry_dispatch":
                from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session
                from app.workflows.processors.action_dispatch_processor import process_action_dispatch_job

                trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)
                return process_action_dispatch_job(job, db=db, trace=trace)
            if run == "seed_pending_intent":
                return self._seed_pending_intent(db, job)
            if run == "approve_action":
                return self._approve_action(db, job, approval_index)
            if run == "resume_dispatch":
                from app.workflows.orchestrator import WorkflowOrchestrator

                return WorkflowOrchestrator(db).resume_after_approval(job)
            raise HarnessError(f"Unknown pipeline step '{run}'")
        except Exception as exc:
            from app.workflows.decision_trace_errors import ReconciliationRequired

            if expect_blocked and isinstance(exc, ReconciliationRequired):
                return job
            raise

    def _seed_pending_intent(self, db: Session, job: Job) -> Job:
        from app.workflows.decision_record_service import record_execution_intent
        from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session

        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)
        op_id = str(uuid.uuid4())
        action = {
            "type": "send_customer_auto_reply",
            "to": "test@example.com",
            "_action_operation_id": op_id,
        }
        record_execution_intent(
            db,
            trace,
            job,
            action,
            operation_id=op_id,
            fingerprint=None,
            key_version=None,
        )
        return JobRepository.get_job_by_id(db, job.tenant_id, job.job_id) or job

    def _patches(self, fixture_client: FixtureAIClient):
        from contextlib import contextmanager

        @contextmanager
        def _ctx():
            stack = ExitStack()
            try:
                from app.workflows import action_executor

                original_execute = action_executor.execute_action

                def _wrap_execute_action(*args, **kwargs):
                    from app.evaluation.telemetry import get_telemetry

                    get_telemetry().record_execution_call()
                    return original_execute(*args, **kwargs)

                stack.enter_context(
                    patch(
                        "app.workflows.processors.ai_processor_utils.get_llm_client",
                        return_value=fixture_client,
                    )
                )
                import importlib

                from app.workflows.processors.ai_processor_utils import run_ai_step as _original_run_ai_step

                def _patched_run_ai_step(*args, **kwargs):
                    token = set_active_prompt_name(kwargs.get("prompt_name"))
                    try:
                        return _original_run_ai_step(*args, **kwargs)
                    finally:
                        reset_active_prompt_name(token)

                for mod_name in _AI_STEP_MODULES:
                    mod = importlib.import_module(mod_name)
                    if hasattr(mod, "run_ai_step"):
                        stack.enter_context(
                            patch.object(mod, "run_ai_step", new=_patched_run_ai_step)
                        )
                stack.enter_context(
                    patch(
                        "app.integrations.factory.get_integration_adapter",
                        side_effect=eval_get_integration_adapter,
                    )
                )
                stack.enter_context(
                    patch(
                        "app.workflows.action_executor.get_integration_adapter",
                        side_effect=eval_get_integration_adapter,
                    )
                )
                stack.enter_context(
                    patch(
                        "app.workflows.action_executor.is_integration_configured",
                        return_value=True,
                    )
                )
                stack.enter_context(
                    patch(
                        "app.workflows.action_executor.get_integration_connection_config",
                        side_effect=eval_get_integration_connection_config,
                    )
                )
                stack.enter_context(
                    patch("app.integrations.service.is_integration_configured", return_value=True)
                )
                stack.enter_context(
                    patch(
                        "app.integrations.policies.is_integration_enabled_for_tenant",
                        return_value=True,
                    )
                )
                stack.enter_context(
                    patch(
                        "app.workflows.action_executor.execute_action",
                        side_effect=_wrap_execute_action,
                    )
                )
                stack.enter_context(
                    patch(
                        "app.workflows.processors.action_dispatch_processor.execute_action",
                        side_effect=_wrap_execute_action,
                    )
                )
                stack.enter_context(
                    patch(
                        "app.workflows.dispatchers.auto_dispatch.maybe_auto_dispatch_job",
                        return_value=None,
                    )
                )
                stack.enter_context(
                    patch(
                        "app.workflows.manual_review_handoff.maybe_apply_gmail_manual_review_handoff",
                        return_value=None,
                    )
                )
                yield
            finally:
                stack.close()

        return _ctx()

    def _seed_tenant(self, db: Session, scenario: ScenarioContract, tenant_id: str) -> None:
        tenant = scenario.tenant
        enabled = tenant.enabled_job_types or ["intake", "lead", "customer_inquiry", "invoice"]
        if "intake" not in enabled:
            enabled = ["intake", *enabled]
        TenantConfigRepository.upsert(
            db,
            tenant_id=tenant_id,
            name=f"Eval {scenario.scenario_id}",
            status="active",
            enabled_job_types=enabled,
            allowed_integrations=tenant.allowed_integrations,
            auto_actions=tenant.auto_actions,
        )
        TenantConfigRepository.update_settings(
            db,
            tenant_id,
            {
                "automation": {
                    "followups_enabled": tenant.followups_enabled,
                    "leads_enabled": True,
                    "support_enabled": True,
                },
                "branding": {
                    "email_signature_name": tenant.email_signature_name,
                    "internal_notification_email": tenant.internal_notification_email,
                },
            },
            merge=True,
        )

    def _create_job(self, db: Session, scenario: ScenarioContract, tenant_id: str) -> Job:
        input_data = {
            "subject": scenario.input.subject,
            "message_text": scenario.input.message_text,
            "sender": scenario.input.sender,
        }
        if scenario.input.actions:
            input_data["actions"] = scenario.input.actions
        if scenario.input.cross_tenant_reference:
            input_data["cross_tenant_reference"] = scenario.input.cross_tenant_reference
        job = Job(
            job_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            job_type=JobType.INTAKE,
            input_data=input_data,
        )
        return JobRepository.create_job(db, job)

    def _approve_action(self, db: Session, job: Job, approval_index: int) -> Job:
        from app.repositories.postgres.approval_repository import ApprovalRequestRepository
        from app.workflows.action_approval_resolution import resolve_per_action_approval

        pending = ApprovalRequestRepository.list_for_job(db, tenant_id=job.tenant_id, job_id=job.job_id)
        pending = [p for p in pending if (p.state or "") == "pending"]
        if approval_index >= len(pending):
            raise HarnessError(f"No pending approval at index {approval_index}")
        approval = pending[approval_index]
        resolve_per_action_approval(db, approval, approved=True, actor="eval_operator")
        refreshed = JobRepository.get_job_by_id(db, job.tenant_id, job.job_id)
        return refreshed or job

    def _compare_baseline(self, scenario_id: str, status: str, normalized_metrics: dict) -> dict[str, Any]:
        if not self.baseline:
            return {"is_regression": False}
        prev_status = (self.baseline.get("scenario_status") or {}).get(scenario_id)
        if prev_status is None:
            return {"is_regression": False, "baseline_status": None}
        is_regression = prev_status == "pass" and status != "pass"
        out: dict[str, Any] = {
            "is_regression": is_regression,
            "baseline_status": prev_status,
            "current_status": status,
        }
        prev_metrics = (self.baseline.get("scenario_metric_scores") or {}).get(scenario_id) or {}
        if not prev_metrics:
            prev_metrics = (self.baseline.get("metric_scores") or {}).get(scenario_id) or {}
        if prev_metrics and normalized_metrics:
            for key, prev_score in prev_metrics.items():
                current = normalized_metrics.get(key)
                if current is not None and current < prev_score:
                    out["is_regression"] = True
                    out.setdefault("metric_regressions", []).append(
                        f"{key}: {current} < {prev_score}"
                    )
        return out

    def aggregate(self, results: list[ScenarioResult]) -> HarnessRunResult:
        exit_code = EXIT_PASS
        for r in results:
            if r.exit_code != EXIT_PASS:
                exit_code = r.exit_code
                break
        return HarnessRunResult(run_id=self.run_id, scenarios=results, exit_code=exit_code)
