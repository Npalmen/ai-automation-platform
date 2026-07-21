"""Tests for write_operation_status.py (Kapitel 8)."""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "write_operation_status.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestWriteOperationStatus:
    def test_backup_success_atomic_write(self, tmp_path: Path):
        output = tmp_path / "status" / "backup_status.json"
        result = _run(
            "backup",
            "--output",
            str(output),
            "--backup-id",
            "ai_platform_2026-07-08-020000",
            "--started-at",
            "2026-07-08T02:00:00Z",
            "--completed-at",
            "2026-07-08T02:00:12Z",
            "--status",
            "success",
            "--size-bytes",
            "1234",
            "--retention-days",
            "30",
            "--archive-integrity-verified",
            "true",
        )
        assert result.returncode == 0
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["archive_integrity_verified"] is True
        assert "password" not in json.dumps(payload).lower()
        if os.name != "nt":
            mode = stat.S_IMODE(output.stat().st_mode)
            # Policy: 0640 (owner rw, group r, others none) per docs/runbooks/backup-and-restore.md
            assert mode == 0o640

    def test_restore_success_with_verification_enums(self, tmp_path: Path):
        output = tmp_path / "restore_status.json"
        result = _run(
            "restore",
            "--output",
            str(output),
            "--test-id",
            "restore_2026-07-08-030000",
            "--backup-id",
            "ai_platform_2026-07-08-020000",
            "--started-at",
            "2026-07-08T03:00:00Z",
            "--completed-at",
            "2026-07-08T03:05:00Z",
            "--status",
            "success",
            "--schema-verification",
            "success",
            "--application-smoke-verification",
            "not_performed",
        )
        assert result.returncode == 0
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["schema_verification"] == "success"
        assert payload["application_smoke_verification"] == "not_performed"

    def test_backup_failed_status(self, tmp_path: Path):
        output = tmp_path / "backup_status.json"
        result = _run(
            "backup",
            "--output",
            str(output),
            "--backup-id",
            "ai_platform_failed",
            "--started-at",
            "2026-07-08T02:00:00Z",
            "--completed-at",
            "2026-07-08T02:00:01Z",
            "--status",
            "failed",
            "--size-bytes",
            "0",
            "--retention-days",
            "30",
            "--archive-integrity-verified",
            "false",
            "--error-code",
            "gzip_invalid",
        )
        assert result.returncode == 0
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["status"] == "failed"
        assert payload["error_code"] == "gzip_invalid"

    def test_rejects_invalid_error_code(self, tmp_path: Path):
        output = tmp_path / "backup_status.json"
        result = _run(
            "backup",
            "--output",
            str(output),
            "--backup-id",
            "x",
            "--started-at",
            "2026-07-08T02:00:00Z",
            "--completed-at",
            "2026-07-08T02:00:01Z",
            "--status",
            "failed",
            "--size-bytes",
            "0",
            "--retention-days",
            "30",
            "--archive-integrity-verified",
            "false",
            "--error-code",
            "DATABASE_URL",
        )
        assert result.returncode == 1
        assert not output.exists()
