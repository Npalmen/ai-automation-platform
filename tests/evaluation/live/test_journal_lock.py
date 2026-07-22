"""Writer lock contract tests."""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timedelta, timezone

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.journal import (
    acquire_run_writer_lock,
    release_run_writer_lock,
    run_directory,
)


@pytest.fixture
def storage_root(tmp_path, live_eval_env, monkeypatch):
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    yield tmp_path
    get_live_eval_config.cache_clear()


def test_writer_lock_acquire_and_release(storage_root):
    lock = acquire_run_writer_lock("run-lock-1")
    lock_path = run_directory("run-lock-1") / ".writer.lock"
    assert lock_path.exists()
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["lock_id"] == lock.lock_id
    assert payload["pid"] == os.getpid()
    release_run_writer_lock(lock)
    assert not lock_path.exists()


def test_second_writer_rejected(storage_root):
    first = acquire_run_writer_lock("run-lock-2")
    try:
        with pytest.raises(LiveEvalSafetyError, match="run_directory_locked"):
            acquire_run_writer_lock("run-lock-2")
    finally:
        release_run_writer_lock(first)


def test_release_requires_matching_lock_id(storage_root):
    lock = acquire_run_writer_lock("run-lock-3")
    lock.lock_id = "wrong-id"
    with pytest.raises(LiveEvalSafetyError, match="writer_lock_release_mismatch"):
        release_run_writer_lock(lock)


def test_force_unlock_same_host_dead_pid(storage_root, monkeypatch):
    first = acquire_run_writer_lock("run-lock-4")
    try:
        with pytest.raises(LiveEvalSafetyError, match="run_directory_locked"):
            acquire_run_writer_lock("run-lock-4", force_unlock=True)

        monkeypatch.setenv("LIVE_EVAL_FORCE_UNLOCK", "yes")
        stale = datetime.now(timezone.utc) - timedelta(hours=3)
        lock_path = run_directory("run-lock-4") / ".writer.lock"
        lock_path.write_text(
            json.dumps(
                {
                    "lock_id": first.lock_id,
                    "pid": 999999,
                    "hostname": socket.gethostname(),
                    "created_at": stale.isoformat(),
                }
            ),
            encoding="utf-8",
        )
        second = acquire_run_writer_lock("run-lock-4", force_unlock=True)
        release_run_writer_lock(second)
    finally:
        if (run_directory("run-lock-4") / ".writer.lock").exists():
            release_run_writer_lock(first)


def test_force_unlock_rejects_other_host(storage_root, monkeypatch):
    acquire_run_writer_lock("run-lock-5")
    monkeypatch.setenv("LIVE_EVAL_FORCE_UNLOCK", "yes")
    stale = datetime.now(timezone.utc) - timedelta(hours=3)
    lock_path = run_directory("run-lock-5") / ".writer.lock"
    lock_path.write_text(
        json.dumps(
            {
                "lock_id": "other-lock",
                "pid": 999999,
                "hostname": "remote-host",
                "created_at": stale.isoformat(),
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(LiveEvalSafetyError, match="cross_host_lock_not_recoverable"):
        acquire_run_writer_lock("run-lock-5", force_unlock=True)
