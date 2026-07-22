"""Live Gmail eval scenario runner and state machine."""

from __future__ import annotations

import hashlib
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
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.constants import TELEMETRY_TESTBOT_SEND_RECONCILE
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.gmail_transport import (
    SendOutcome,
    _TRANSPORT_ERRORS,
    observe_unexpected_sender_reply,
    reconcile_sent_message,
    run_sender_readiness,
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
from app.evaluation.live.safety import require_scenario_allowed_for_2f2
from app.evaluation.live.schemas import LiveEvalReport

EXIT_SUCCESS = 0
EXIT_ASSERTION = 1
EXIT_CONFIG = 2
EXIT_TRANSPORT = 3
EXIT_UNRESOLVED_SEND = 4
EXIT_TIMEOUT = 5
EXIT_CLEANUP = 6


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
        self._registry_run: dict[str, Any] | None = None
        self._resume_phase: str = "pre_send"
        self._checkpoint = None

    def _transition(self, state: str, **extra: Any) -> None:
        append_transition(
            self.evaluation_run_id,
            {"state": state, **extra},
        )

    def _fingerprint(self, email: str) -> str:
        return hashlib.sha256(email.encode("utf-8")).hexdigest()[:12]

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
                    return self._resume_cleanup_only()
            else:
                self._transition("created")
                self._write_run_id_file()

            self._validate_runtime()
            if not self.resume:
                self._transition("validated")

            if not self.resume:
                self._register_run()
                registry = self._load_registry_run()
                self._persist_run_config(config_hash=str(registry.get("config_hash") or ""))
                self._transition("run_registered")
            else:
                self._persist_run_config(
                    config_hash=str(self._load_registry_run().get("config_hash") or "")
                )

            ctx = _RunContext()
            if self._resume_phase in ("pre_send",):
                self._sender_ready()
                if not self.resume:
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
                    self._transition(
                        "sent",
                        sender_gmail_message_id=ctx.send_outcome.sender_gmail_message_id,
                        sender_gmail_thread_id=ctx.send_outcome.sender_gmail_thread_id,
                        rfc_message_id=ctx.send_outcome.rfc_message_id,
                    )
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

            registry = self._load_registry_run()
            if self._resume_phase in ("pre_send", "reconcile_only", "post_send", "post_delivery"):
                recipient_id = (ctx.confirmed or {}).get("message_id")
                if not registry.get("root_job_id"):
                    intake = self._process_delivery(recipient_id)
                    self._transition(
                        "intake_completed",
                        job_id=intake.get("root_job_id"),
                        pipeline_run_id=intake.get("pipeline_run_id"),
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
                self.failure_category = violations[0].split(":")[0] if violations else "assertion_failure"
                if ctx.unexpected_reply:
                    self.failure_category = "unexpected_external_write"
                self._abort_run()
                self._write_report("failed", violations, ctx)
                if ctx.unexpected_reply:
                    cleanup_unexpected_reply(message_id=ctx.unexpected_reply["message_id"])
                return EXIT_ASSERTION

            cleanup_ok = self._cleanup_all(ctx)
            self._transition("cleaning_up", cleanup_ok=cleanup_ok)
            if not cleanup_ok:
                self.failure_category = "cleanup_failure"
                self._abort_run()
                self._write_report("cleanup_failed", ["cleanup failed"], ctx)
                return EXIT_CLEANUP
            self.observer.complete_run(self.evaluation_run_id, "completed")
            self._transition("passed")
            self._write_report("passed", [], ctx)
            return EXIT_SUCCESS
        except TimeoutError as exc:
            self.failure_category = str(exc)
            self._abort_run()
            self._write_report("failed", [str(exc)])
            return EXIT_TIMEOUT
        except LiveEvalSafetyError as exc:
            msg = str(exc)
            if "send_outcome_unresolved" in msg:
                self.failure_category = "send_outcome_unresolved"
                self._abort_run()
                self._write_report("failed", [msg])
                return EXIT_UNRESOLVED_SEND
            self.failure_category = "configuration"
            self._abort_run()
            self._write_report("failed", [msg])
            return EXIT_CONFIG
        except _TRANSPORT_ERRORS as exc:
            self.failure_category = "infrastructure"
            self._abort_run()
            self._write_report("failed", [str(exc)])
            return EXIT_TRANSPORT
        finally:
            if writer_lock is not None:
                try:
                    release_run_writer_lock(writer_lock)
                except LiveEvalSafetyError:
                    pass

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

    def _sender_ready(self) -> None:
        report = run_sender_readiness(
            expected_sender=self.expected_sender,
            expected_recipient=self.expected_recipient,
        )
        if not report.ready:
            raise LiveEvalSafetyError("; ".join(report.issues))

    def _send_or_reconcile(self) -> SendOutcome:
        checkpoint = self._checkpoint if self.resume else None
        if checkpoint and checkpoint.send_attempt_started and not checkpoint.send_succeeded:
            return self._reconcile_only()
        self._transition("sending")
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
            return outcome
        except LiveEvalSafetyError:
            raise
        except _TRANSPORT_ERRORS:
            reconciled = self._reconcile_only()
            if reconciled is None:
                raise LiveEvalSafetyError("send_outcome_unresolved")
            return reconciled

    def _reconcile_only(self) -> SendOutcome:
        registry = self._load_registry_run()
        expires_raw = registry.get("expires_at")
        expires_at = None
        if expires_raw:
            expires_at = datetime.fromisoformat(str(expires_raw).replace("Z", "+00:00"))
        reconciled = reconcile_sent_message(
            evaluation_run_id=self.evaluation_run_id,
            scenario_id=self.scenario_id,
            attempt_id=self.attempt_id,
            expected_sender=self.expected_sender,
            expected_recipient=self.expected_recipient,
            send_window_start=self.send_window_start,
            expires_at=expires_at,
        )
        if reconciled is None:
            raise LiveEvalSafetyError("send_outcome_unresolved")
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
        )
        write_report_atomic(self.evaluation_run_id, report)


def checkpoint_sender_id(checkpoint) -> str:
    if checkpoint.sender_gmail_message_id:
        return checkpoint.sender_gmail_message_id
    raise LiveEvalSafetyError("missing sender_gmail_message_id in checkpoint")


def cleanup_only(
    *,
    base_url: str,
    admin_api_key: str,
    tenant_id: str,
    evaluation_run_id: str,
    recipient_gmail_message_id: str | None = None,
    phase: str = "post_claim",
    force_unlock: bool = False,
) -> int:
    writer_lock = acquire_run_writer_lock(evaluation_run_id, force_unlock=force_unlock)
    try:
        observer = LiveEvalObserver(
            base_url=base_url,
            admin_api_key=admin_api_key,
            tenant_id=tenant_id,
        )
        run = observer.get_run(evaluation_run_id)
        message_id = recipient_gmail_message_id or run.get("root_gmail_message_id")
        if not message_id:
            return EXIT_CLEANUP
        observer.cleanup_recipient(evaluation_run_id, message_id, phase=phase)
        return EXIT_SUCCESS
    finally:
        release_run_writer_lock(writer_lock)
