"""Kapitel 12 Slice 2 — incident drill tests (safe, in-process)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.admin.alerts.evaluators import (
    evaluate_system_backup_last_failed,
    evaluate_system_backup_stale,
)
from app.admin.alerts.registry import ALERT_REGISTRY
from app.admin.system_status_sources import summarize_backup_status_for_signals


def _settings(tmp_path, **kwargs):
    defaults = {
        "BACKUP_STATUS_FILE": str(tmp_path / "backup_status.json"),
        "BACKUP_MAX_AGE_HOURS": 25,
        "ADMIN_API_KEY": "test",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _write_backup(path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestBackupIncidentDrills:
    def test_stale_backup_creates_alert(self, tmp_path):
        path = tmp_path / "backup_status.json"
        old = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat().replace("+00:00", "Z")
        _write_backup(
            path,
            {
                "schema_version": 1,
                "backup_id": "old",
                "started_at": old,
                "completed_at": old,
                "status": "success",
                "size_bytes": 5000,
                "retention_days": 30,
                "archive_integrity_verified": True,
                "offsite_status": "success",
                "offsite_verified": True,
            },
        )
        settings = _settings(tmp_path)
        definition = ALERT_REGISTRY["system.backup_stale"]
        candidates = evaluate_system_backup_stale(None, definition, settings)
        assert len(candidates) == 1
        assert candidates[0].deduplication_key == "system:backup:stale"

    def test_failed_backup_creates_alert(self, tmp_path):
        path = tmp_path / "backup_status.json"
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _write_backup(
            path,
            {
                "schema_version": 1,
                "backup_id": "failed",
                "started_at": now,
                "completed_at": now,
                "status": "failed",
                "size_bytes": 0,
                "retention_days": 30,
                "archive_integrity_verified": False,
                "error_code": "offsite_failed",
                "offsite_status": "failed",
                "offsite_verified": False,
            },
        )
        settings = _settings(tmp_path)
        definition = ALERT_REGISTRY["system.backup_last_failed"]
        candidates = evaluate_system_backup_last_failed(None, definition, settings)
        assert len(candidates) == 1

    def test_fresh_backup_no_stale_alert(self, tmp_path):
        path = tmp_path / "backup_status.json"
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _write_backup(
            path,
            {
                "schema_version": 1,
                "backup_id": "fresh",
                "started_at": now,
                "completed_at": now,
                "status": "success",
                "size_bytes": 5000,
                "retention_days": 30,
                "archive_integrity_verified": True,
                "offsite_status": "success",
                "offsite_verified": True,
            },
        )
        settings = _settings(tmp_path)
        definition = ALERT_REGISTRY["system.backup_stale"]
        candidates = evaluate_system_backup_stale(None, definition, settings)
        assert candidates == []

    def test_summarize_backup_signal(self, tmp_path):
        path = tmp_path / "backup_status.json"
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        _write_backup(
            path,
            {
                "schema_version": 1,
                "backup_id": "x",
                "started_at": now,
                "completed_at": now,
                "status": "success",
                "size_bytes": 1,
                "retention_days": 30,
                "archive_integrity_verified": True,
                "offsite_status": "not_configured",
            },
        )
        summary = summarize_backup_status_for_signals(_settings(tmp_path))
        assert summary["available"] is True
        assert "Offsite ej konfigurerad" in (summary.get("message") or "")


class TestEvaluatorFailureIsolation:
    def test_registry_has_backup_evaluators(self):
        assert "system.backup_stale" in ALERT_REGISTRY
        assert "system.backup_last_failed" in ALERT_REGISTRY

    def test_evaluation_service_importable(self):
        from app.admin.alerts.evaluation_service import run_alert_evaluation

        assert callable(run_alert_evaluation)
