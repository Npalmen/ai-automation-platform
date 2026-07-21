"""Persistent run journal for testbot process."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.redaction import redact_sensitive
from app.evaluation.live.schemas import LiveEvalReport


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
