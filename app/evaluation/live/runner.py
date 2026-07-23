"""Live Gmail eval scenario runner and state machine."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.evaluation.live.assertions import (
    assert_no_unexpected_reply,
    assert_s01_pipeline,
    assert_safety_invariants,
    assert_telemetry_summary,
)
from app.evaluation.live.cleanup import cleanup_recipient_message, cleanup_unexpected_reply
from app.evaluation.live.cleanup_phase import resolve_cleanup_phase
from app.evaluation.live.cleanup_resolver import resolve_recipient_from_journal
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.constants import (
    CLEANUP_STATE_ALREADY_ARCHIVED,
    CLEANUP_STATE_DEFERRED,
    CLEANUP_STATE_FAILED,
    CLEANUP_STATE_IN_PROGRESS,
    CLEANUP_STATE_SUCCESS,
    TELEMETRY_TESTBOT_SEND_RECONCILE,
    TERMINAL_CLEANUP_STATES,
)
from app.evaluation.live.errors import (
    LiveEvalIntakeSkippedError,
    LiveEvalPipelinePollError,
    LiveEvalSafetyError,
    LiveEvalSafetyRejectedError,
)
from app.evaluation.live.exit_codes import (
    EXIT_ASSERTION,
    EXIT_CLEANUP,
    EXIT_CONFIG,
    EXIT_INFRASTRUCTURE,
    EXIT_SUCCESS,
    EXIT_TIMEOUT,
    EXIT_TRANSPORT,
    EXIT_UNRESOLVED_SEND,
)
from app.evaluation.live.gmail_transport import (
    SendOutcome,
    _TRANSPORT_ERRORS,
    observe_unexpected_sender_reply,
    reconcile_sent_message,
    run_sender_readiness_read_only,
    send_scenario_email,
)
from app.evaluation.live.journal import (
    RunWriterLock,
    acquire_run_writer_lock,
    append_transition,
    derive_resume_state,
    ensure_run_directory,
    load_checkpoint,
    release_run_writer_lock,
    write_report_atomic,
    write_run_config,
    write_run_id_file,
)
from app.evaluation.live.observer import LiveEvalObserver
from app.evaluation.live.registry import new_evaluation_run_id
from app.evaluation.live.reporting import (
    build_failure_summary,
    compute_final_exit_code,
    emit_run_summary_stdout,
    write_github_step_summary,
)
from app.evaluation.live.safety import require_scenario_allowed_for_2f2, validate_config_readiness
from app.evaluation.live.schemas import LiveEvalReport


@dataclass
class _RunContext:
    send_outcome: SendOutcome | None = None
    confirmed: dict[str, Any] | None = None
    unexpected_reply: dict[str, Any] | None = None


class LiveEvalRunner:
    def __init__(
        self,
        *,
        base_url: str,
        admin_api_key: str,
        tenant_id: str,
        scenario_id: str,
        expected_sender: str,
        expected_recipient: str,
        evaluation_run_id: str | None = None,
        attempt_id: int = 1,
        resume: bool = False,
        force_unlock: bool = False,
        run_id_file: str | None = None,
    ):
        self.config = get_live_eval_config()
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self.scenario_id = scenario_id
        self.expected_sender = expected_sender.strip().lower()
        self.expected_recipient = expected_recipient.strip().lower()
        self.evaluation_run_id = evaluation_run_id or new_evaluation_run_id()
        self.attempt_id = attempt_id
        self.resume = resume
        self.force_unlock = force_unlock
        self.run_id_file = run_id_file
        self.observer = LiveEvalObserver(
            base_url=self.base_url,
            admin_api_key=admin_api_key,
            tenant_id=tenant_id,
        )
        self.testbot_events: list[dict[str, Any]] = []
        self.started_at = datetime.now(timezone.utc)
        self.send_window_start = self.started_at
        self.failure_category: str | None = None
        self._intake_skip_reason: str | None = None
        self._safety_reason: str | None = None
        self._registry_run: dict[str, Any] | None = None
        self._resume_phase: str = "pre_send"
        self._checkpoint = None
        self._failed_stage: str = "starting"
        self._send_state: str = "not_attempted"
        self._reconciliation_result: str = "not_run"
        self._cleanup_state: str = "not_run"
        self._last_error: BaseException | None = None
        self._primary_exit_code: int | None = None
        self._cleanup_exit_code: int | None = None
        self._artifact_status: str = "not_checked"
        self._gmail_mutations: int = 0
        self._last_failure_summary: dict[str, Any] | None = None
        self._timeout_reason: str | None = None
        self._timeout_job_snapshot: dict[str, Any] | None = None
        self._poll_attempts: int | None = None
        self._poll_duration_seconds: float | None = None

    def _transition(self, state: str, **extra: Any) -> None:
        self._failed_stage = state
        append_transition(
            self.evaluation_run_id,
            {"state": state, **extra},
        )

    def _fingerprint(self, email: str) -> str:
        return hashlib.sha256(email.encode("utf-8")).hexdigest()[:12]

    def _send_attempted(self) -> bool:
        from app.evaluation.live.journal import load_transitions

        transitions = load_transitions(self.evaluation_run_id)
        return any(t.get("state") == "sending" for t in transitions) or any(
            e.get("category") == "testbot_gmail_send_attempt" for e in self.testbot_events
        )

    def _send_confirmed(self) -> bool:
        from app.evaluation.live.journal import load_transitions

        transitions = load_transitions(self.evaluation_run_id)
        return any(
            t.get("state") in ("send_response_received", "sent")
            and t.get("sender_gmail_message_id")
            for t in transitions
        )

    def _delivery_observed(self) -> bool:
        from app.evaluation.live.journal import load_transitions

        transitions = load_transitions(self.evaluation_run_id)
        return any(t.get("state") == "delivery_confirmed" for t in transitions)

    def _record_send_confirmed(self, outcome: SendOutcome) -> None:
        self._send_state = "confirmed"
        self._transition(
            "send_response_received",
            sender_gmail_message_id=outcome.sender_gmail_message_id,
            sender_gmail_thread_id=outcome.sender_gmail_thread_id,
            rfc_message_id=outcome.rfc_message_id,
            reconciled=outcome.reconciled,
        )
        self._transition(
            "sent",
            sender_gmail_message_id=outcome.sender_gmail_message_id,
            sender_gmail_thread_id=outcome.sender_gmail_thread_id,
            rfc_message_id=outcome.rfc_message_id,
        )

    def _set_primary_failure(self, code: int, *, category: str | None = None) -> None:
        if self._primary_exit_code is None:
            self._primary_exit_code = code
            if category is not None:
                self.failure_category = category

    def _write_preliminary_report(self) -> None:
        report = LiveEvalReport(
            evaluation_run_id=self.evaluation_run_id,
            scenario_id=self.scenario_id,
            attempt_id=self.attempt_id,
            transport_mode="live_gmail",
            ai_mode="fixture_ai",
            result="preflight",
            started_at=self.started_at,
            sender_account_fingerprint=self._fingerprint(self.expected_sender),
            recipient_account_fingerprint=self._fingerprint(self.expected_recipient),
        )
        write_report_atomic(self.evaluation_run_id, report)

    def _validate_static_config(self) -> None:
        issues = validate_config_readiness(self.config)
        if issues:
            raise LiveEvalSafetyError("; ".join(issues))

    def _verify_sender_profile(self) -> None:
        report = run_sender_readiness_read_only(
            expected_sender=self.expected_sender,
            expected_recipient=self.expected_recipient,
            config=self.config,
        )
        if not report.ready:
            raise LiveEvalSafetyError("; ".join(report.issues))

    def _verify_sender_send_scope(self) -> None:
        from app.evaluation.live.sender_scope import verify_sender_send_scope

        report = verify_sender_send_scope()
        if report.unverifiable:
            self.failure_category = "sender_scope_unverifiable"
            raise LiveEvalSafetyError("sender_scope_unverifiable")
        if not report.verified:
            raise LiveEvalSafetyError("; ".join(report.issues))

    def _run_preflight(self) -> None:
        self._validate_static_config()
        self._transition("config_validated")
        self._verify_sender_profile()
        self._transition("sender_profile_ready")
        self._verify_sender_send_scope()
        self._transition("sender_scope_ready")
        self._validate_runtime()
        self._transition("app_ready")

    def _check_artifact_status(self) -> None:
        from app.evaluation.live.paths import resolved_run_directory

        report_path = resolved_run_directory(self.evaluation_run_id) / "report.json"
        self._artifact_status = "present" if report_path.is_file() else "missing"

    def _finalize_exit(self) -> int:
        self._check_artifact_status()
        if self._primary_exit_code is None:
            self._primary_exit_code = EXIT_SUCCESS
        registry = self._registry_run or {}
        summary = build_failure_summary(
            evaluation_run_id=self.evaluation_run_id,
            scenario_id=self.scenario_id,
            attempt_id=self.attempt_id,
            failure_category=self.failure_category,
            failed_stage=self._failed_stage,
            primary_exit_code=self._primary_exit_code,
            cleanup_exit_code=self._cleanup_exit_code,
            artifact_status=self._artifact_status,
            send_state=self._send_state,
            send_attempted=self._send_attempted(),
            send_confirmed=self._send_confirmed(),
            reconciliation_result=self._reconciliation_result,
            recipient_delivery_observed=self._delivery_observed(),
            root_job_bound=bool(registry.get("root_job_id")),
            cleanup_state=self._cleanup_state,
            gmail_mutations=self._gmail_mutations,
            error=self._last_error,
            intake_skip_reason=self._intake_skip_reason,
            safety_reason=self._safety_reason,
            workflow_sha=(
                os.environ.get("BUILD_GIT_SHA") or os.environ.get("GITHUB_SHA") or ""
            ).strip()
            or None,
            timeout_reason=self._timeout_reason,
            timeout_job_snapshot=self._timeout_job_snapshot,
            poll_attempts=self._poll_attempts,
            poll_duration_seconds=self._poll_duration_seconds,
        )
        emit_run_summary_stdout(summary)
        write_github_step_summary(summary)
        self._last_failure_summary = summary.to_dict()
        self._attach_summary_to_report()
        return summary.final_exit_code

    def _write_run_id_file(self) -> None:
        if self.run_id_file:
            write_run_id_file(self.run_id_file, self.evaluation_run_id)

    def _persist_run_config(self, *, config_hash: str = "") -> None:
        write_run_config(
            self.evaluation_run_id,
            {
                "evaluation_run_id": self.evaluation_run_id,
                "scenario_id": self.scenario_id,
                "attempt_id": self.attempt_id,
                "tenant_id": self.tenant_id,
                "transport_mode": "live_gmail",
                "ai_mode": "fixture_ai",
                "config_hash": config_hash,
                "send_window_start": self.send_window_start.isoformat(),
                "sender_account_fingerprint": self._fingerprint(self.expected_sender),
                "recipient_account_fingerprint": self._fingerprint(self.expected_recipient),
            },
        )

    def _load_registry_run(self) -> dict[str, Any]:
        if self._registry_run is None:
            self._registry_run = self.observer.get_run(self.evaluation_run_id)
        return self._registry_run

    def _refresh_registry_run(self) -> dict[str, Any]:
        self._registry_run = self.observer.get_run(self.evaluation_run_id)
        return self._registry_run

    def _validate_resume_consistency(self) -> None:
        checkpoint = load_checkpoint(self.evaluation_run_id)
        self._checkpoint = checkpoint
        self.send_window_start = checkpoint.send_window_start
        self.started_at = checkpoint.send_window_start

        if checkpoint.scenario_id and checkpoint.scenario_id != self.scenario_id:
            raise LiveEvalSafetyError("registry_journal_mismatch: scenario_id")
        if checkpoint.attempt_id and checkpoint.attempt_id != self.attempt_id:
            raise LiveEvalSafetyError("registry_journal_mismatch: attempt_id")
        if checkpoint.tenant_id and checkpoint.tenant_id != self.tenant_id:
            raise LiveEvalSafetyError("registry_journal_mismatch: tenant_id")
        if (
            checkpoint.sender_account_fingerprint
            and checkpoint.sender_account_fingerprint != self._fingerprint(self.expected_sender)
        ):
            raise LiveEvalSafetyError("registry_journal_mismatch: sender fingerprint")
        if (
            checkpoint.recipient_account_fingerprint
            and checkpoint.recipient_account_fingerprint
            != self._fingerprint(self.expected_recipient)
        ):
            raise LiveEvalSafetyError("registry_journal_mismatch: recipient fingerprint")

        registry = self._load_registry_run()
        if registry.get("scenario_id") and registry["scenario_id"] != self.scenario_id:
            raise LiveEvalSafetyError("registry_journal_mismatch: registry scenario")
        if registry.get("attempt_id") and int(registry["attempt_id"]) != self.attempt_id:
            raise LiveEvalSafetyError("registry_journal_mismatch: registry attempt")
        if registry.get("tenant_id") and registry["tenant_id"] != self.tenant_id:
            raise LiveEvalSafetyError("registry_journal_mismatch: registry tenant")
        if registry.get("ai_mode") and registry["ai_mode"] != "fixture_ai":
            raise LiveEvalSafetyError("registry_journal_mismatch: ai_mode")
        if registry.get("transport_mode") and registry["transport_mode"] != "live_gmail":
            raise LiveEvalSafetyError("registry_journal_mismatch: transport_mode")

        config_hash = str(registry.get("config_hash") or "")
        if checkpoint.config_hash and config_hash and checkpoint.config_hash[:16] != config_hash[:16]:
            raise LiveEvalSafetyError("registry_journal_mismatch: config_hash")

        if checkpoint.job_id and not registry.get("root_job_id"):
            raise LiveEvalSafetyError("registry_journal_mismatch: missing root_job_id")
        if checkpoint.recipient_gmail_message_id and registry.get("root_gmail_message_id"):
            if registry["root_gmail_message_id"] != checkpoint.recipient_gmail_message_id:
                raise LiveEvalSafetyError("registry_journal_mismatch: root_gmail_message_id")

        resume_state = derive_resume_state(checkpoint)
        self._resume_phase = resume_state.phase

    def run(self) -> int:
        writer_lock: RunWriterLock | None = None
        try:
            require_scenario_allowed_for_2f2(self.scenario_id)
            ensure_run_directory(self.evaluation_run_id)
            writer_lock = acquire_run_writer_lock(
                self.evaluation_run_id,
                force_unlock=self.force_unlock,
            )

            if self.resume:
                self._validate_resume_consistency()
                if self._resume_phase == "cleanup_only":
                    self._primary_exit_code = self._resume_cleanup_only()
                else:
                    self._persist_run_config(
                        config_hash=str(self._load_registry_run().get("config_hash") or "")
                    )
                    self._run_main_scenario()
            else:
                self._transition("created")
                self._write_preliminary_report()
                self._write_run_id_file()
                self._run_preflight()
                self._register_run()
                registry = self._load_registry_run()
                self._persist_run_config(config_hash=str(registry.get("config_hash") or ""))
                self._transition("run_registered")
                self._run_main_scenario()
        except LiveEvalPipelinePollError as exc:
            self._last_error = exc
            self._timeout_reason = exc.timeout_reason
            self._timeout_job_snapshot = exc.job_snapshot
            self._poll_attempts = exc.poll_attempts
            self._poll_duration_seconds = exc.poll_duration_seconds
            self._set_primary_failure(EXIT_TIMEOUT, category=exc.timeout_reason)
            self._abort_run()
            self._write_report("failed", [exc.timeout_reason])
        except TimeoutError as exc:
            self._last_error = exc
            self._set_primary_failure(EXIT_TIMEOUT, category=str(exc))
            self._abort_run()
            self._write_report("failed", [str(exc)])
        except LiveEvalIntakeSkippedError as exc:
            self._last_error = exc
            self._intake_skip_reason = str(
                exc.payload.get("intake_skip_reason") or "intake_skipped_unknown"
            )
            self._set_primary_failure(EXIT_CONFIG, category="intake_skipped")
            self._abort_run()
            self._write_report("failed", [self._intake_skip_reason])
        except LiveEvalSafetyRejectedError as exc:
            self._last_error = exc
            self._safety_reason = str(exc.payload.get("safety_reason") or "safety_rejected_unknown")
            self._set_primary_failure(EXIT_CONFIG, category="safety_rejected")
            self._abort_run()
            self._write_report("failed", [self._safety_reason])
        except LiveEvalSafetyError as exc:
            self._last_error = exc
            msg = str(exc)
            if "send_outcome_unresolved" in msg:
                self._set_primary_failure(EXIT_UNRESOLVED_SEND, category="send_outcome_unresolved")
                self._send_state = "outcome_unknown"
            elif self.failure_category == "sender_scope_unverifiable":
                self._set_primary_failure(EXIT_CONFIG, category="sender_scope_unverifiable")
            else:
                if self._send_state == "not_attempted":
                    self._send_state = "failed_before_send"
                self._set_primary_failure(EXIT_CONFIG, category=self.failure_category or "configuration")
            self._abort_run()
            self._write_report("failed", [msg])
        except _TRANSPORT_ERRORS as exc:
            self._last_error = exc
            if self._send_state == "sending":
                self._send_state = "outcome_unknown"
                self._set_primary_failure(EXIT_TRANSPORT, category="outcome_unknown")
            elif self._send_state == "not_attempted":
                self._send_state = "failed_before_send"
                self._set_primary_failure(EXIT_TRANSPORT, category="infrastructure")
            else:
                self._set_primary_failure(EXIT_TRANSPORT, category="infrastructure")
            self._abort_run()
            self._write_report("failed", [str(exc)])
        finally:
            if writer_lock is not None:
                try:
                    release_run_writer_lock(writer_lock)
                except LiveEvalSafetyError:
                    pass
        return self._finalize_exit()

    def _run_main_scenario(self) -> None:
        ctx = _RunContext()
        if self._resume_phase in ("pre_send",):
            self._transition("sender_ready")
            ctx.send_outcome = self._send_or_reconcile()
        elif self._resume_phase == "reconcile_only":
            ctx.send_outcome = self._reconcile_only()
        elif self._resume_phase in ("post_send", "post_delivery", "post_intake"):
            ctx.send_outcome = SendOutcome(
                sender_gmail_message_id=checkpoint_sender_id(self._checkpoint),
                sender_gmail_thread_id=self._checkpoint.sender_gmail_thread_id or "",
                rfc_message_id=self._checkpoint.rfc_message_id,
                reconciled=True,
            )
        else:
            raise LiveEvalSafetyError(f"unexpected resume phase {self._resume_phase!r}")

        if self._resume_phase in ("pre_send", "reconcile_only", "post_send"):
            if not ctx.send_outcome:
                raise LiveEvalSafetyError("send_outcome_unresolved")
            if not self.resume or self._resume_phase in ("pre_send", "reconcile_only"):
                self._record_send_confirmed(ctx.send_outcome)
            delivery = self._wait_for_delivery()
            confirmed = delivery.get("confirmed") or {}
            ctx.confirmed = confirmed
            recipient_id = confirmed.get("message_id")
            if recipient_id and self._resume_phase != "post_delivery":
                self._transition(
                    "delivery_confirmed",
                    recipient_gmail_message_id=recipient_id,
                    recipient_gmail_thread_id=confirmed.get("thread_id"),
                )
        elif self._resume_phase == "post_delivery":
            recipient_id = self._checkpoint.recipient_gmail_message_id
            ctx.confirmed = {"message_id": recipient_id}
        elif self._resume_phase == "post_intake":
            recipient_id = self._checkpoint.recipient_gmail_message_id
            ctx.confirmed = {"message_id": recipient_id}
            ctx.send_outcome = SendOutcome(
                sender_gmail_message_id=checkpoint_sender_id(self._checkpoint),
                sender_gmail_thread_id=self._checkpoint.sender_gmail_thread_id or "",
                rfc_message_id=self._checkpoint.rfc_message_id,
                reconciled=True,
            )
        else:
            recipient_id = None

        registry = self._refresh_registry_run()
        if self._resume_phase in ("pre_send", "reconcile_only", "post_send", "post_delivery"):
            recipient_id = (ctx.confirmed or {}).get("message_id")
            if not registry.get("root_job_id"):
                intake = self._process_delivery(recipient_id)
                self._refresh_registry_run()
                self._transition(
                    "intake_completed",
                    job_id=intake.get("root_job_id") or intake.get("job_id"),
                    pipeline_run_id=intake.get("pipeline_run_id"),
                    job_status=intake.get("job_status"),
                )
            else:
                self._transition(
                    "intake_completed",
                    job_id=registry.get("root_job_id"),
                    pipeline_run_id=None,
                )

        observation = self._wait_for_pipeline()
        self._transition("pipeline_completed")

        registry = self._load_registry_run()
        expires_raw = registry.get("expires_at")
        expires_at = None
        if expires_raw:
            expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))

        reply_evidence = observe_unexpected_sender_reply(
            evaluation_run_id=self.evaluation_run_id,
            scenario_id=self.scenario_id,
            attempt_id=self.attempt_id,
            expected_recipient=self.expected_recipient,
            send_window_start=self.send_window_start,
            expires_at=expires_at,
        )
        if reply_evidence:
            ctx.unexpected_reply = {
                "message_id": reply_evidence.message_id,
                "subject_truncated": reply_evidence.subject_truncated,
                "from_masked": reply_evidence.from_masked,
                "internal_date_ms": reply_evidence.internal_date_ms,
            }
            self.testbot_events.append(
                {
                    "category": "testbot_unexpected_sender_reply_detected",
                    "message_id": reply_evidence.message_id,
                }
            )

        violations = self._assert_all(observation, ctx)
        self._transition("asserting", violations=violations)
        if violations:
            self._set_primary_failure(EXIT_ASSERTION, category=violations[0].split(":")[0])
            if ctx.unexpected_reply:
                self.failure_category = "unexpected_external_write"
            self._abort_run()
            self._write_report("failed", violations, ctx)
            if ctx.unexpected_reply:
                cleanup_unexpected_reply(message_id=ctx.unexpected_reply["message_id"])
            return

        self._cleanup_state = CLEANUP_STATE_DEFERRED
        self._transition("passed")
        self._write_report("passed", [], ctx)
        self._set_primary_failure(EXIT_SUCCESS)

    def _resume_cleanup_only(self) -> int:
        checkpoint = self._checkpoint or load_checkpoint(self.evaluation_run_id)
        sender_id = checkpoint_sender_id(checkpoint)
        recipient_id = checkpoint.recipient_gmail_message_id
        if not sender_id or not recipient_id:
            self._write_report("cleanup_failed", ["missing ids for cleanup_failed resume"])
            return EXIT_CLEANUP
        ctx = _RunContext(
            send_outcome=SendOutcome(
                sender_gmail_message_id=sender_id,
                sender_gmail_thread_id=checkpoint.sender_gmail_thread_id or "",
                rfc_message_id=checkpoint.rfc_message_id,
                reconciled=True,
            ),
            confirmed={"message_id": recipient_id},
        )
        cleanup_ok = self._cleanup_all(ctx)
        if not cleanup_ok:
            self._write_report("cleanup_failed", ["cleanup failed"], ctx)
            return EXIT_CLEANUP
        self.observer.complete_run(self.evaluation_run_id, "completed")
        self._write_report("passed", [], ctx)
        return EXIT_SUCCESS

    def _validate_runtime(self) -> None:
        readiness = self.observer.runtime_readiness()
        expected_sha = os.environ.get("BUILD_GIT_SHA", "").strip()
        if expected_sha and readiness.get("build_git_sha") != expected_sha:
            raise LiveEvalSafetyError("build_git_sha mismatch with runtime")
        if readiness.get("env") != "test":
            raise LiveEvalSafetyError("runtime env must be test")

    def _register_run(self) -> None:
        self.observer.register_run(
            {
                "evaluation_run_id": self.evaluation_run_id,
                "tenant_id": self.tenant_id,
                "scenario_id": self.scenario_id,
                "attempt_id": self.attempt_id,
                "transport_mode": "live_gmail",
                "ai_mode": "fixture_ai",
                "expected_sender": self.expected_sender,
                "expected_recipient": self.expected_recipient,
            }
        )

    def _send_or_reconcile(self) -> SendOutcome:
        checkpoint = self._checkpoint if self.resume else None
        if checkpoint and checkpoint.send_attempt_started and not checkpoint.send_succeeded:
            return self._reconcile_only()
        self._transition("sending")
        self._send_state = "sending"
        try:
            outcome, events = send_scenario_email(
                evaluation_run_id=self.evaluation_run_id,
                scenario_id=self.scenario_id,
                attempt_id=self.attempt_id,
                expected_sender=self.expected_sender,
                expected_recipient=self.expected_recipient,
                checkpoint=checkpoint,
            )
            self.testbot_events.extend(events)
            self._reconciliation_result = "not_run"
            return outcome
        except LiveEvalSafetyError:
            raise
        except _TRANSPORT_ERRORS:
            try:
                reconciled = self._reconcile_only()
            except _TRANSPORT_ERRORS:
                self._send_state = "outcome_unknown"
                self._reconciliation_result = "transport_error"
                raise
            if reconciled is None:
                self._send_state = "outcome_unknown"
                raise LiveEvalSafetyError("send_outcome_unresolved")
            return reconciled

    def _reconcile_only(self) -> SendOutcome:
        registry = self._load_registry_run()
        expires_raw = registry.get("expires_at")
        expires_at = None
        if expires_raw:
            expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
        try:
            reconciled = reconcile_sent_message(
                evaluation_run_id=self.evaluation_run_id,
                scenario_id=self.scenario_id,
                attempt_id=self.attempt_id,
                expected_sender=self.expected_sender,
                expected_recipient=self.expected_recipient,
                send_window_start=self.send_window_start,
                expires_at=expires_at,
            )
        except LiveEvalSafetyError as exc:
            if "multiple sent matches" in str(exc):
                self._reconciliation_result = "many"
            raise
        except _TRANSPORT_ERRORS:
            self._reconciliation_result = "transport_error"
            raise
        if reconciled is None:
            self._reconciliation_result = "zero"
            raise LiveEvalSafetyError("send_outcome_unresolved")
        self._reconciliation_result = "one"
        self.testbot_events.append(
            {
                "category": TELEMETRY_TESTBOT_SEND_RECONCILE,
                "resolved": True,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        )
        return reconciled

    def _wait_for_delivery(self) -> dict[str, Any]:
        self._transition("waiting_for_delivery")

        def on_poll(payload: dict[str, Any]) -> None:
            if payload.get("duplicate_detected"):
                raise LiveEvalSafetyError("correlation_failure: duplicate delivery")

        return self.observer.poll_delivery(
            self.evaluation_run_id,
            timeout_seconds=min(300, self.config.max_runtime_minutes * 60),
            on_poll=on_poll,
        )

    def _process_delivery(self, recipient_id: str | None) -> dict[str, Any]:
        if not recipient_id:
            raise LiveEvalSafetyError("missing recipient message id for intake")
        self._transition("triggering_intake", recipient_gmail_message_id=recipient_id)
        return self.observer.process_delivery(self.evaluation_run_id, recipient_id)

    def _wait_for_pipeline(self) -> dict[str, Any]:
        self._transition("job_detected")
        return self.observer.poll_pipeline(
            self.evaluation_run_id,
            timeout_seconds=min(600, self.config.max_runtime_minutes * 60),
        )

    def _assert_all(self, observation: dict[str, Any], ctx: _RunContext) -> list[str]:
        violations: list[str] = []
        violations.extend(assert_no_unexpected_reply(ctx.unexpected_reply))
        violations.extend(assert_s01_pipeline(observation))
        events = observation.get("events") or []
        violations.extend(
            assert_telemetry_summary(
                self.testbot_events,
                events,
                observation.get("telemetry_summary") or {},
            )
        )
        send_id = ctx.send_outcome.sender_gmail_message_id if ctx.send_outcome else None
        recipient_id = (ctx.confirmed or {}).get("message_id")
        violations.extend(
            assert_safety_invariants(
                run=observation.get("run") or {},
                sender_message_id=send_id,
                recipient_message_id=recipient_id,
            )
        )
        return violations

    def _cleanup_all(self, ctx: _RunContext) -> bool:
        try:
            recipient_id = (ctx.confirmed or {}).get("message_id")
            if recipient_id:
                self.observer.cleanup_recipient(
                    self.evaluation_run_id,
                    recipient_id,
                    phase="post_claim",
                )
            return True
        except Exception:
            return False

    def _abort_run(self) -> None:
        try:
            self.observer.complete_run(self.evaluation_run_id, "aborted")
        except Exception:
            pass

    def _write_report(
        self,
        result: str,
        violations: list[str],
        ctx: _RunContext | None = None,
    ) -> None:
        from app.evaluation.live.journal import load_transitions

        report = LiveEvalReport(
            evaluation_run_id=self.evaluation_run_id,
            scenario_id=self.scenario_id,
            attempt_id=self.attempt_id,
            transport_mode="live_gmail",
            ai_mode="fixture_ai",
            result=result,  # type: ignore[arg-type]
            failure_category=self.failure_category,
            started_at=self.started_at,
            completed_at=datetime.now(timezone.utc),
            assertion_results=violations,
            sender_account_fingerprint=self._fingerprint(self.expected_sender),
            recipient_account_fingerprint=self._fingerprint(self.expected_recipient),
            external_telemetry={"testbot_events": self.testbot_events},
            state_transitions=load_transitions(self.evaluation_run_id),
            sender_gmail_message_id=(
                ctx.send_outcome.sender_gmail_message_id if ctx and ctx.send_outcome else None
            ),
            recipient_gmail_message_id=(
                (ctx.confirmed or {}).get("message_id") if ctx and ctx.confirmed else None
            ),
            redacted_diagnostics={"unexpected_reply": ctx.unexpected_reply} if ctx and ctx.unexpected_reply else {},
            failure_summary=self._last_failure_summary,
        )
        write_report_atomic(self.evaluation_run_id, report)

    def _attach_summary_to_report(self) -> None:
        if not self._last_failure_summary:
            return
        from app.evaluation.live.journal import load_report, write_report_atomic

        payload = load_report(self.evaluation_run_id)
        if not payload:
            return
        payload["failure_summary"] = self._last_failure_summary
        report = LiveEvalReport.model_validate(payload)
        write_report_atomic(self.evaluation_run_id, report)


def checkpoint_sender_id(checkpoint) -> str:
    if checkpoint.sender_gmail_message_id:
        return checkpoint.sender_gmail_message_id
    raise LiveEvalSafetyError("missing sender_gmail_message_id in checkpoint")


def cleanup_not_safe_exit_code(evaluation_run_id: str) -> int:
    """
    Exit code when cleanup is blocked (not_safe_to_execute).

    Preserve an existing primary scenario failure; otherwise fail cleanup so a
    passed scenario cannot be reported as fully successful without cleanup.
    """
    from app.evaluation.live.journal import load_report

    report = load_report(evaluation_run_id)
    if not report:
        return EXIT_SUCCESS

    summary = report.get("failure_summary") or {}
    primary = summary.get("primary_exit_code")
    if primary is None:
        result = report.get("result")
        if result == "passed":
            primary = EXIT_SUCCESS
        elif result in ("failed", "cleanup_failed"):
            return EXIT_SUCCESS
        else:
            return EXIT_SUCCESS

    if primary not in (None, EXIT_SUCCESS):
        return EXIT_SUCCESS
    return EXIT_CLEANUP


def _read_report_cleanup_state(evaluation_run_id: str) -> str | None:
    from app.evaluation.live.journal import load_report

    report = load_report(evaluation_run_id)
    if not report:
        return None
    summary = report.get("failure_summary") or {}
    return summary.get("cleanup_state")


def _scenario_passed(report: dict[str, Any]) -> bool:
    summary = report.get("failure_summary") or {}
    primary = summary.get("primary_exit_code")
    if primary is not None:
        return primary == EXIT_SUCCESS
    return report.get("result") == "passed"


def _cleanup_mutations_for_adapter_result(adapter_result: str | None) -> int:
    return 1 if adapter_result == "archived" else 0


def _emit_cleanup_stdout(payload: dict[str, Any]) -> None:
    print(json.dumps(payload))


def _persist_workflow_cleanup_outcome(
    evaluation_run_id: str,
    *,
    cleanup_state: str,
    workflow_cleanup_mutations: int,
    cleanup_adapter_called: bool,
    cleanup_adapter_result: str | None,
    cleanup_exit_code: int | None,
    cleanup_failure_reason: str | None = None,
) -> None:
    from app.evaluation.live.journal import load_report, write_report_atomic

    payload = load_report(evaluation_run_id)
    if not payload:
        return
    summary = dict(payload.get("failure_summary") or {})
    scenario_mutations = int(summary.get("scenario_cleanup_mutations") or 0)
    total_mutations = scenario_mutations + workflow_cleanup_mutations
    summary.update(
        {
            "cleanup_state": cleanup_state,
            "scenario_cleanup_mutations": scenario_mutations,
            "workflow_cleanup_mutations": workflow_cleanup_mutations,
            "total_gmail_mutations": total_mutations,
            "gmail_mutations": total_mutations,
            "cleanup_adapter_called": cleanup_adapter_called,
            "cleanup_adapter_result": cleanup_adapter_result,
            "cleanup_exit_code": cleanup_exit_code,
        }
    )
    if cleanup_failure_reason:
        summary["cleanup_failure_reason"] = cleanup_failure_reason
    payload["failure_summary"] = summary
    report = LiveEvalReport.model_validate(payload)
    write_report_atomic(evaluation_run_id, report)


def resolve_post_cleanup_run_status(
    *,
    scenario_passed: bool,
    cleanup_succeeded: bool,
    current_status: str,
) -> str | None:
    """Resolve registry terminal status after workflow cleanup without masking cleanup failure."""
    if cleanup_succeeded:
        if scenario_passed and current_status != "completed":
            return "completed"
        return None
    if current_status == "active":
        return "aborted"
    return None


def _finalize_run_after_cleanup(
    observer: LiveEvalObserver,
    evaluation_run_id: str,
    *,
    scenario_passed: bool,
    cleanup_succeeded: bool,
    current_status: str,
) -> str | None:
    next_status = resolve_post_cleanup_run_status(
        scenario_passed=scenario_passed,
        cleanup_succeeded=cleanup_succeeded,
        current_status=current_status,
    )
    if next_status:
        observer.complete_run(evaluation_run_id, next_status)
    return next_status


def _emit_idempotent_cleanup_skip(
    evaluation_run_id: str,
    *,
    cleanup_state: str,
    observer: LiveEvalObserver | None = None,
) -> int:
    adapter_result = (
        CLEANUP_STATE_ALREADY_ARCHIVED
        if cleanup_state == CLEANUP_STATE_ALREADY_ARCHIVED
        else "idempotent_skip"
    )
    _persist_workflow_cleanup_outcome(
        evaluation_run_id,
        cleanup_state=cleanup_state,
        workflow_cleanup_mutations=0,
        cleanup_adapter_called=False,
        cleanup_adapter_result=adapter_result,
        cleanup_exit_code=EXIT_SUCCESS,
    )
    if observer is not None:
        from app.evaluation.live.journal import load_report

        report = load_report(evaluation_run_id) or {}
        registry = observer.get_run(evaluation_run_id)
        _finalize_run_after_cleanup(
            observer,
            evaluation_run_id,
            scenario_passed=_scenario_passed(report),
            cleanup_succeeded=True,
            current_status=str(registry.get("status") or ""),
        )
    _emit_cleanup_stdout(
        {
            "cleanup_state": cleanup_state,
            "evaluation_run_id": evaluation_run_id,
            "cleanup_exit_code": EXIT_SUCCESS,
            "gmail_mutations": 0,
            "scenario_cleanup_mutations": 0,
            "workflow_cleanup_mutations": 0,
            "total_gmail_mutations": 0,
            "cleanup_adapter_called": False,
            "cleanup_adapter_result": adapter_result,
            "idempotent": True,
        }
    )
    return EXIT_SUCCESS


def cleanup_only(
    *,
    base_url: str,
    admin_api_key: str,
    tenant_id: str,
    evaluation_run_id: str,
    recipient_gmail_message_id: str | None = None,
    phase: str | None = None,
    force_unlock: bool = False,
) -> int:
    writer_lock = acquire_run_writer_lock(evaluation_run_id, force_unlock=force_unlock)
    try:
        checkpoint = load_checkpoint(evaluation_run_id)
        sender_id = checkpoint.sender_gmail_message_id
        message_id = recipient_gmail_message_id

        def _not_safe(reason: str) -> int:
            exit_code = cleanup_not_safe_exit_code(evaluation_run_id)
            cleanup_exit = EXIT_CLEANUP if exit_code == EXIT_CLEANUP else None
            print(
                json.dumps(
                    {
                        "cleanup_state": "not_safe_to_execute",
                        "evaluation_run_id": evaluation_run_id,
                        "reason": reason,
                        "cleanup_exit_code": cleanup_exit,
                        "gmail_mutations": 0,
                    }
                )
            )
            return exit_code

        if not message_id:
            resolution = resolve_recipient_from_journal(checkpoint)
            if not resolution.resolved:
                return _not_safe(resolution.blocked_reason or "journal_resolution_failed")
            message_id = resolution.recipient_gmail_message_id
        if not message_id:
            return _not_safe("missing exact recipient_gmail_message_id")
        if sender_id and message_id == sender_id:
            return _not_safe("recipient_gmail_message_id matches sender_gmail_message_id")

        existing_cleanup = _read_report_cleanup_state(evaluation_run_id)
        if existing_cleanup in TERMINAL_CLEANUP_STATES:
            observer = LiveEvalObserver(
                base_url=base_url,
                admin_api_key=admin_api_key,
                tenant_id=tenant_id,
            )
            return _emit_idempotent_cleanup_skip(
                evaluation_run_id,
                cleanup_state=existing_cleanup,
                observer=observer,
            )
        if existing_cleanup == CLEANUP_STATE_FAILED:
            from app.evaluation.live.journal import load_report

            report = load_report(evaluation_run_id) or {}
            summary = report.get("failure_summary") or {}
            _emit_cleanup_stdout(
                {
                    "cleanup_state": CLEANUP_STATE_FAILED,
                    "evaluation_run_id": evaluation_run_id,
                    "cleanup_exit_code": EXIT_CLEANUP,
                    "gmail_mutations": 0,
                    "cleanup_adapter_called": False,
                    "cleanup_adapter_result": "failed",
                    "idempotent": True,
                    "reason": summary.get("cleanup_failure_reason"),
                }
            )
            return EXIT_CLEANUP

        observer = LiveEvalObserver(
            base_url=base_url,
            admin_api_key=admin_api_key,
            tenant_id=tenant_id,
        )
        registry = observer.get_run(evaluation_run_id)
        root_job_bound = bool(registry.get("root_job_id"))
        root_gmail_message_id = registry.get("root_gmail_message_id")
        resolved_phase = phase
        if resolved_phase in (None, "", "auto"):
            phase_resolution = resolve_cleanup_phase(
                checkpoint,
                root_job_bound=root_job_bound,
                root_gmail_message_id=root_gmail_message_id,
            )
            if not phase_resolution.resolved:
                return _not_safe(phase_resolution.blocked_reason or "cleanup_phase_unresolved")
            resolved_phase = phase_resolution.phase

        _persist_workflow_cleanup_outcome(
            evaluation_run_id,
            cleanup_state=CLEANUP_STATE_IN_PROGRESS,
            workflow_cleanup_mutations=0,
            cleanup_adapter_called=False,
            cleanup_adapter_result=None,
            cleanup_exit_code=None,
        )
        result = observer.cleanup_recipient(evaluation_run_id, message_id, phase=resolved_phase)
        adapter_result = str(result.get("result") or "archived")
        cleanup_state = (
            CLEANUP_STATE_ALREADY_ARCHIVED
            if adapter_result == "already_archived"
            else CLEANUP_STATE_SUCCESS
        )
        workflow_mutations = _cleanup_mutations_for_adapter_result(adapter_result)
        _persist_workflow_cleanup_outcome(
            evaluation_run_id,
            cleanup_state=cleanup_state,
            workflow_cleanup_mutations=workflow_mutations,
            cleanup_adapter_called=True,
            cleanup_adapter_result=adapter_result,
            cleanup_exit_code=EXIT_SUCCESS,
        )

        from app.evaluation.live.journal import load_report

        report = load_report(evaluation_run_id) or {}
        scenario_passed = _scenario_passed(report)
        _finalize_run_after_cleanup(
            observer,
            evaluation_run_id,
            scenario_passed=scenario_passed,
            cleanup_succeeded=True,
            current_status=str(registry.get("status") or ""),
        )

        _emit_cleanup_stdout(
            {
                "cleanup_state": cleanup_state,
                "evaluation_run_id": evaluation_run_id,
                "cleanup_exit_code": EXIT_SUCCESS,
                "gmail_mutations": workflow_mutations,
                "scenario_cleanup_mutations": 0,
                "workflow_cleanup_mutations": workflow_mutations,
                "total_gmail_mutations": workflow_mutations,
                "cleanup_adapter_called": True,
                "cleanup_adapter_result": adapter_result,
                "phase": resolved_phase,
                "recipient_gmail_message_id": message_id,
            }
        )
        return EXIT_SUCCESS
    except LiveEvalSafetyError as exc:
        reason = str(exc)
        _handle_cleanup_failure(
            evaluation_run_id,
            base_url=base_url,
            admin_api_key=admin_api_key,
            tenant_id=tenant_id,
            reason=reason,
            reason_type="safety_error",
        )
        return EXIT_CLEANUP
    except Exception as exc:
        _handle_cleanup_failure(
            evaluation_run_id,
            base_url=base_url,
            admin_api_key=admin_api_key,
            tenant_id=tenant_id,
            reason=type(exc).__name__,
            reason_type="exception",
        )
        return EXIT_CLEANUP
    finally:
        release_run_writer_lock(writer_lock)


def _handle_cleanup_failure(
    evaluation_run_id: str,
    *,
    base_url: str,
    admin_api_key: str,
    tenant_id: str,
    reason: str,
    reason_type: str,
) -> None:
    from app.evaluation.live.journal import load_report

    _persist_workflow_cleanup_outcome(
        evaluation_run_id,
        cleanup_state=CLEANUP_STATE_FAILED,
        workflow_cleanup_mutations=0,
        cleanup_adapter_called=False,
        cleanup_adapter_result="failed",
        cleanup_exit_code=EXIT_CLEANUP,
        cleanup_failure_reason=reason,
    )
    report = load_report(evaluation_run_id) or {}
    observer = LiveEvalObserver(
        base_url=base_url,
        admin_api_key=admin_api_key,
        tenant_id=tenant_id,
    )
    registry = observer.get_run(evaluation_run_id)
    _finalize_run_after_cleanup(
        observer,
        evaluation_run_id,
        scenario_passed=_scenario_passed(report),
        cleanup_succeeded=False,
        current_status=str(registry.get("status") or ""),
    )
    _emit_cleanup_stdout(
        {
            "cleanup_state": "failed",
            "evaluation_run_id": evaluation_run_id,
            "reason": reason,
            "reason_type": reason_type,
            "cleanup_exit_code": EXIT_CLEANUP,
            "gmail_mutations": 0,
            "cleanup_adapter_called": False,
            "cleanup_adapter_result": "failed",
        }
    )
