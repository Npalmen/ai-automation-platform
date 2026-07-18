"""Tests for system status metadata readers (Kapitel 8)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.admin.system_status_sources import (
    MetadataReadOutcome,
    read_backup_status,
    read_build_metadata,
    read_json_metadata_file,
    read_restore_status,
    summarize_backup_status_for_signals,
)


def _settings(tmp_path: Path, **kwargs):
    defaults = {
        "BACKUP_STATUS_FILE": str(tmp_path / "backup_status.json"),
        "RESTORE_STATUS_FILE": str(tmp_path / "restore_status.json"),
        "BUILD_METADATA_PATH": str(tmp_path / "build-metadata.json"),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


class TestReadJsonMetadataFile:
    def test_valid_backup_metadata(self, tmp_path: Path):
        path = tmp_path / "backup_status.json"
        _write(
            path,
            {
                "schema_version": 1,
                "backup_id": "ai_platform_2026-07-08-020000",
                "started_at": "2026-07-08T02:00:00Z",
                "completed_at": "2026-07-08T02:00:12Z",
                "status": "success",
                "size_bytes": 1000,
                "retention_days": 30,
                "archive_integrity_verified": True,
                "error_code": None,
            },
        )
        result = read_json_metadata_file(str(path))
        assert result.outcome == MetadataReadOutcome.VALID
        assert result.data is not None
        assert result.data["backup_id"] == "ai_platform_2026-07-08-020000"

    def test_missing_file(self, tmp_path: Path):
        result = read_json_metadata_file(str(tmp_path / "missing.json"))
        assert result.outcome == MetadataReadOutcome.MISSING

    def test_invalid_json(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        result = read_json_metadata_file(str(path))
        assert result.outcome == MetadataReadOutcome.INVALID
        assert result.error_code == "invalid_json"

    def test_oversized_file(self, tmp_path: Path):
        path = tmp_path / "big.json"
        path.write_text(" " * (64 * 1024 + 1), encoding="utf-8")
        result = read_json_metadata_file(str(path))
        assert result.outcome == MetadataReadOutcome.OVERSIZED

    def test_wrong_schema_version(self, tmp_path: Path):
        path = tmp_path / "backup_status.json"
        _write(path, {"schema_version": 2, "status": "success"})
        result = read_json_metadata_file(str(path))
        assert result.outcome == MetadataReadOutcome.INVALID
        assert result.error_code == "invalid_schema_version"

    def test_response_never_contains_path(self, tmp_path: Path):
        path = tmp_path / "backup_status.json"
        _write(path, {"schema_version": 1, "status": "success"})
        result = read_backup_status(_settings(tmp_path))
        dumped = repr(result)
        assert str(path) not in dumped


class TestTypedReaders:
    def test_read_build_metadata(self, tmp_path: Path):
        settings = _settings(tmp_path)
        _write(
            Path(settings.BUILD_METADATA_PATH),
            {
                "schema_version": 1,
                "commit_sha": "abc1234567890",
                "build_time": "2026-07-17T10:00:00Z",
                "release_id": "ci-abc1234",
                "source": "docker_build",
            },
        )
        result = read_build_metadata(settings)
        assert result.outcome == MetadataReadOutcome.VALID

    def test_read_restore_status_missing(self, tmp_path: Path):
        result = read_restore_status(_settings(tmp_path))
        assert result.outcome == MetadataReadOutcome.MISSING

    def test_summarize_backup_status_for_signals(self, tmp_path: Path):
        path = tmp_path / "backup_status.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "backup_id": "x",
                    "started_at": "2026-07-18T02:00:00Z",
                    "completed_at": "2026-07-18T02:00:00Z",
                    "status": "success",
                    "size_bytes": 100,
                    "retention_days": 30,
                    "archive_integrity_verified": True,
                    "offsite_status": "success",
                    "offsite_verified": True,
                }
            ),
            encoding="utf-8",
        )
        summary = summarize_backup_status_for_signals(_settings(tmp_path))
        assert summary["available"] is True
        assert summary["operation_status"] == "success"
        assert summary["offsite_verified"] is True
