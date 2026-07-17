"""Tests for write_build_metadata.py (Kapitel 8)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "write_build_metadata.py"


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


class TestWriteBuildMetadata:
    def test_valid_metadata_written(self, tmp_path: Path):
        output = tmp_path / "build-metadata.json"
        result = _run(
            "--commit-sha",
            "abc1234567890abcdef",
            "--build-time",
            "2026-07-17T10:00:00Z",
            "--release-id",
            "ci-abc1234",
            "--output",
            str(output),
        )
        assert result.returncode == 0
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 1
        assert payload["commit_sha"] == "abc1234567890abcdef"
        assert payload["build_time"] == "2026-07-17T10:00:00Z"
        assert payload["release_id"] == "ci-abc1234"
        assert set(payload.keys()) == {
            "schema_version",
            "commit_sha",
            "build_time",
            "release_id",
            "source",
        }

    def test_rejects_invalid_sha(self, tmp_path: Path):
        output = tmp_path / "build-metadata.json"
        result = _run(
            "--commit-sha",
            "not-a-sha!",
            "--build-time",
            "2026-07-17T10:00:00Z",
            "--release-id",
            "ci-test",
            "--output",
            str(output),
        )
        assert result.returncode == 1
        assert not output.exists()

    def test_rejects_non_utc_build_time(self, tmp_path: Path):
        output = tmp_path / "build-metadata.json"
        result = _run(
            "--commit-sha",
            "abc1234",
            "--build-time",
            "2026-07-17T10:00:00+02:00",
            "--release-id",
            "ci-test",
            "--output",
            str(output),
        )
        assert result.returncode == 1

    def test_rejects_oversized_release_id(self, tmp_path: Path):
        output = tmp_path / "build-metadata.json"
        result = _run(
            "--commit-sha",
            "abc1234",
            "--build-time",
            "2026-07-17T10:00:00Z",
            "--release-id",
            "x" * 129,
            "--output",
            str(output),
        )
        assert result.returncode == 1

    def test_unknown_values_allowed(self, tmp_path: Path):
        output = tmp_path / "build-metadata.json"
        result = _run(
            "--commit-sha",
            "unknown",
            "--build-time",
            "unknown",
            "--release-id",
            "local-dev",
            "--output",
            str(output),
        )
        assert result.returncode == 0
