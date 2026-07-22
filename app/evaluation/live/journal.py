"""Persistent run journal, checkpoint, and single-writer lock for testbot."""

from __future__ import annotations

import json
import os
import platform
import socket
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.redaction import redact_sensitive
from app.evaluation.live.schemas import LiveEvalReport

LOCK_FILENAME = ".writer.lock"
RUN_CONFIG_FILENAME = "run_config.json"
DEFAULT_LOCK_STALE_MINUTES = 120


def run_directory(evaluation_run_id: str) -> Path:
    config = get_live_eval_config()
    return Path(config.storage_root) / "runs" / evaluation_run_id


def ensure_run_directory(evaluation_run_id: str) -> Path:
    path = run_directory(evaluation_run_id)
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o750)
    return path


def append_transition(evaluation_run_id: str, transition: dict[str, Any]) -> None:
    directory = ensure_run_directory(evaluation_run_id)
    transitions_path = directory / "transitions.jsonl"
    payload = redact_sensitive(
        {
            **transition,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    line = json.dumps(payload, ensure_ascii=False) + "\n"
    with open(transitions_path, "a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(transitions_path, 0o640)


def write_report_atomic(evaluation_run_id: str, report: LiveEvalReport) -> Path:
    directory = ensure_run_directory(evaluation_run_id)
    target = directory / "report.json"
    payload = redact_sensitive(report.model_dump(mode="json"))
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".report.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
        os.chmod(target, 0o640)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return target


def load_transitions(evaluation_run_id: str) -> list[dict[str, Any]]:
    path = run_directory(evaluation_run_id) / "transitions.jsonl"
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_run_config(evaluation_run_id: str, payload: dict[str, Any]) -> Path:
    directory = ensure_run_directory(evaluation_run_id)
    target = directory / RUN_CONFIG_FILENAME
    body = redact_sensitive(payload)
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".run_config.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(body, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
        os.chmod(target, 0o640)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return target


def load_run_config(evaluation_run_id: str) -> dict[str, Any]:
    path = run_directory(evaluation_run_id) / RUN_CONFIG_FILENAME
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_report(evaluation_run_id: str) -> dict[str, Any]:
    path = run_directory(evaluation_run_id) / "report.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class RunCheckpoint:
    evaluation_run_id: str
    scenario_id: str
    attempt_id: int
    tenant_id: str
    transport_mode: str
    ai_mode: str
    config_hash: str
    send_window_start: datetime
    sender_account_fingerprint: str
    recipient_account_fingerprint: str
    last_state: str
    send_attempt_started: bool = False
    send_succeeded: bool = False
    sender_gmail_message_id: str | None = None
    sender_gmail_thread_id: str | None = None
    rfc_message_id: str | None = None
    recipient_gmail_message_id: str | None = None
    recipient_gmail_thread_id: str | None = None
    job_id: str | None = None
    pipeline_run_id: str | None = None
    report_result: str | None = None
    failure_category: str | None = None
    transitions: list[dict[str, Any]] = field(default_factory=list)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _field_from_transitions(transitions: list[dict[str, Any]], state: str, key: str) -> str | None:
    for row in reversed(transitions):
        if row.get("state") == state and row.get(key):
            return str(row[key])
    return None


def load_checkpoint(evaluation_run_id: str) -> RunCheckpoint:
    run_config = load_run_config(evaluation_run_id)
    transitions = load_transitions(evaluation_run_id)
    report = load_report(evaluation_run_id)
    if not run_config and not transitions:
        raise LiveEvalSafetyError(f"checkpoint missing for run {evaluation_run_id!r}")

    send_window_start = _parse_iso_datetime(run_config.get("send_window_start"))
    if send_window_start is None and transitions:
        send_window_start = _parse_iso_datetime(transitions[0].get("recorded_at"))
    if send_window_start is None:
        send_window_start = datetime.now(timezone.utc)

    last_state = transitions[-1].get("state", "created") if transitions else "created"
    sender_id = _field_from_transitions(transitions, "sent", "sender_gmail_message_id")
    recipient_id = _field_from_transitions(transitions, "delivery_confirmed", "recipient_gmail_message_id")
    job_id = _field_from_transitions(transitions, "intake_completed", "job_id")
    pipeline_run_id = _field_from_transitions(transitions, "intake_completed", "pipeline_run_id")

    send_attempt_started = any(t.get("state") == "sending" for t in transitions)
    send_succeeded = sender_id is not None or any(
        t.get("state") == "sent" and t.get("sender_gmail_message_id") for t in transitions
    )

    return RunCheckpoint(
        evaluation_run_id=str(run_config.get("evaluation_run_id") or evaluation_run_id),
        scenario_id=str(run_config.get("scenario_id") or ""),
        attempt_id=int(run_config.get("attempt_id") or 1),
        tenant_id=str(run_config.get("tenant_id") or ""),
        transport_mode=str(run_config.get("transport_mode") or "live_gmail"),
        ai_mode=str(run_config.get("ai_mode") or "fixture_ai"),
        config_hash=str(run_config.get("config_hash") or ""),
        send_window_start=send_window_start,
        sender_account_fingerprint=str(run_config.get("sender_account_fingerprint") or ""),
        recipient_account_fingerprint=str(run_config.get("recipient_account_fingerprint") or ""),
        last_state=str(last_state),
        send_attempt_started=send_attempt_started,
        send_succeeded=send_succeeded,
        sender_gmail_message_id=sender_id,
        sender_gmail_thread_id=_field_from_transitions(transitions, "sent", "sender_gmail_thread_id"),
        rfc_message_id=_field_from_transitions(transitions, "sent", "rfc_message_id"),
        recipient_gmail_message_id=recipient_id,
        recipient_gmail_thread_id=_field_from_transitions(
            transitions, "delivery_confirmed", "recipient_gmail_thread_id"
        ),
        job_id=job_id,
        pipeline_run_id=pipeline_run_id,
        report_result=report.get("result"),
        failure_category=report.get("failure_category"),
        transitions=transitions,
    )


@dataclass(frozen=True)
class ResumeState:
    phase: str
    checkpoint: RunCheckpoint


TERMINAL_REPORT_RESULTS = frozenset({
    "passed",
    "failed",
    "cleanup_failed",
    "dry_run",
})
NON_RESUMABLE_FAILURE_CATEGORIES = frozenset({
    "send_outcome_unresolved",
})


def derive_resume_state(checkpoint: RunCheckpoint) -> ResumeState:
    report_result = checkpoint.report_result
    last = checkpoint.last_state

    if report_result == "cleanup_failed":
        return ResumeState(phase="cleanup_only", checkpoint=checkpoint)
    if report_result == "passed" or last == "passed":
        raise LiveEvalSafetyError("terminal_run_not_resumable: passed")
    if checkpoint.failure_category in NON_RESUMABLE_FAILURE_CATEGORIES:
        raise LiveEvalSafetyError(
            f"terminal_run_not_resumable: {checkpoint.failure_category}"
        )
    if report_result == "failed" and last not in ("asserting", "cleaning_up", "pipeline_completed"):
        raise LiveEvalSafetyError("terminal_run_not_resumable: failed")

    if checkpoint.job_id or last in (
        "intake_completed",
        "job_detected",
        "pipeline_completed",
        "asserting",
        "cleaning_up",
    ):
        return ResumeState(phase="post_intake", checkpoint=checkpoint)
    if checkpoint.recipient_gmail_message_id or last in (
        "delivery_confirmed",
        "triggering_intake",
    ):
        return ResumeState(phase="post_delivery", checkpoint=checkpoint)
    if checkpoint.send_succeeded or last in ("sent", "waiting_for_delivery"):
        return ResumeState(phase="post_send", checkpoint=checkpoint)
    if checkpoint.send_attempt_started and not checkpoint.send_succeeded:
        return ResumeState(phase="reconcile_only", checkpoint=checkpoint)
    return ResumeState(phase="pre_send", checkpoint=checkpoint)


def assert_journal_send_budget(checkpoint: RunCheckpoint) -> None:
    if checkpoint.send_attempt_started:
        raise LiveEvalSafetyError("send_in_progress_use_reconcile")
    if checkpoint.send_succeeded or checkpoint.sender_gmail_message_id:
        raise LiveEvalSafetyError("send_budget_exhausted")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if platform.system() == "Windows":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


@dataclass
class RunWriterLock:
    evaluation_run_id: str
    lock_id: str
    path: Path


def _lock_stale_minutes() -> int:
    raw = os.environ.get("LIVE_EVAL_LOCK_STALE_MINUTES", str(DEFAULT_LOCK_STALE_MINUTES))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_LOCK_STALE_MINUTES


def _read_lock_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _is_lock_stale(lock_data: dict[str, Any]) -> bool:
    created_at = _parse_iso_datetime(str(lock_data.get("created_at") or ""))
    if created_at is None:
        return True
    age = datetime.now(timezone.utc) - created_at
    return age > timedelta(minutes=_lock_stale_minutes())


def _can_force_unlock(lock_data: dict[str, Any]) -> bool:
    if os.environ.get("LIVE_EVAL_FORCE_UNLOCK", "").strip().lower() not in ("yes", "true", "1"):
        return False
    if not _is_lock_stale(lock_data):
        return False
    hostname = str(lock_data.get("hostname") or "")
    if hostname != socket.gethostname():
        return False
    pid = int(lock_data.get("pid") or 0)
    if _pid_alive(pid):
        return False
    return True


def acquire_run_writer_lock(
    evaluation_run_id: str,
    *,
    force_unlock: bool = False,
) -> RunWriterLock:
    directory = ensure_run_directory(evaluation_run_id)
    path = directory / LOCK_FILENAME
    lock_id = str(uuid.uuid4())
    payload = {
        "lock_id": lock_id,
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags)
        try:
            os.write(fd, json.dumps(payload).encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(path, 0o640)
        return RunWriterLock(evaluation_run_id=evaluation_run_id, lock_id=lock_id, path=path)
    except FileExistsError:
        existing = _read_lock_file(path)
        if force_unlock:
            hostname = str(existing.get("hostname") or "")
            if hostname and hostname != socket.gethostname():
                raise LiveEvalSafetyError("cross_host_lock_not_recoverable")
            if _can_force_unlock(existing):
                append_transition(
                    evaluation_run_id,
                    {
                        "state": "lock_forced",
                        "previous_lock_id": existing.get("lock_id"),
                        "previous_pid": existing.get("pid"),
                    },
                )
                try:
                    os.unlink(path)
                except OSError as exc:
                    raise LiveEvalSafetyError(f"failed to remove stale lock: {exc}") from exc
                return acquire_run_writer_lock(evaluation_run_id, force_unlock=False)
        raise LiveEvalSafetyError("run_directory_locked") from None


def release_run_writer_lock(lock: RunWriterLock) -> None:
    if not lock.path.exists():
        return
    existing = _read_lock_file(lock.path)
    if str(existing.get("lock_id") or "") != lock.lock_id:
        raise LiveEvalSafetyError("writer_lock_release_mismatch")
    os.unlink(lock.path)


def write_run_id_file(path: str | Path, evaluation_run_id: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".run_id.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(evaluation_run_id)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
