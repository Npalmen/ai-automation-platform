"""Tests for canonical runtime commit resolution."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.admin.system_status_sources import MetadataReadOutcome, MetadataReadResult
from app.core.canonical_commit import normalize_commit_sha, resolve_canonical_commit


class TestNormalizeCommitSha:
    def test_accepts_full_sha(self):
        assert normalize_commit_sha("A72547176D8C2E738331856A347F83465831733D") == (
            "a72547176d8c2e738331856a347f83465831733d"
        )

    def test_rejects_unknown(self):
        assert normalize_commit_sha("unknown") is None

    def test_rejects_invalid(self):
        assert normalize_commit_sha("not-a-sha") is None


class TestResolveCanonicalCommit:
    def test_explicit_override_wins(self, monkeypatch):
        monkeypatch.setenv("BUILD_COMMIT_SHA", "b" * 40)
        assert resolve_canonical_commit(explicit="a" * 40) == "a" * 40

    def test_invalid_explicit_falls_through_to_env(self, monkeypatch):
        monkeypatch.setenv("BUILD_COMMIT_SHA", "c" * 40)
        assert resolve_canonical_commit(explicit="bad-value") == "c" * 40

    def test_env_used_when_explicit_missing(self, monkeypatch):
        monkeypatch.delenv("GIT_COMMIT", raising=False)
        monkeypatch.delenv("COMMIT_SHA", raising=False)
        monkeypatch.setenv("BUILD_COMMIT_SHA", "d" * 40)
        assert resolve_canonical_commit() == "d" * 40

    def test_build_metadata_used_when_env_missing(self, monkeypatch, tmp_path: Path):
        for key in ("BUILD_COMMIT_SHA", "GIT_COMMIT", "COMMIT_SHA"):
            monkeypatch.delenv(key, raising=False)
        metadata_path = tmp_path / "build-metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "commit_sha": "e" * 40,
                    "build_time": "2026-07-21T23:35:26Z",
                    "release_id": "rc-test",
                    "source": "docker_build",
                }
            ),
            encoding="utf-8",
        )
        settings = SimpleNamespace(BUILD_METADATA_PATH=str(metadata_path))
        with patch("app.core.canonical_commit.get_settings", return_value=settings):
            assert resolve_canonical_commit() == "e" * 40

    def test_invalid_build_metadata_falls_through(self, monkeypatch, tmp_path: Path):
        for key in ("BUILD_COMMIT_SHA", "GIT_COMMIT", "COMMIT_SHA"):
            monkeypatch.delenv(key, raising=False)
        metadata_path = tmp_path / "build-metadata.json"
        metadata_path.write_text('{"schema_version":1,"commit_sha":"unknown"}', encoding="utf-8")
        settings = SimpleNamespace(BUILD_METADATA_PATH=str(metadata_path))
        monkeypatch.setenv("ENV", "production")
        with patch("app.core.canonical_commit.get_settings", return_value=settings):
            assert resolve_canonical_commit() is None

    def test_git_fallback_only_in_dev_test(self, monkeypatch, tmp_path: Path):
        for key in ("BUILD_COMMIT_SHA", "GIT_COMMIT", "COMMIT_SHA"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("ENV", "test")
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        with patch("app.core.canonical_commit.get_settings") as mock_settings:
            mock_settings.return_value = SimpleNamespace(
                BUILD_METADATA_PATH=str(tmp_path / "missing.json")
            )
            with patch("app.core.canonical_commit.subprocess.run") as mock_run:
                mock_run.return_value = type(
                    "Proc",
                    (),
                    {"returncode": 0, "stdout": "f" * 40},
                )()
                assert resolve_canonical_commit() == "f" * 40

    def test_git_fallback_skipped_in_production(self, monkeypatch, tmp_path: Path):
        for key in ("BUILD_COMMIT_SHA", "GIT_COMMIT", "COMMIT_SHA"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("ENV", "production")
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        with patch("app.core.canonical_commit.get_settings") as mock_settings:
            mock_settings.return_value = SimpleNamespace(
                BUILD_METADATA_PATH=str(tmp_path / "missing.json")
            )
            with patch("app.core.canonical_commit.subprocess.run") as mock_run:
                assert resolve_canonical_commit() is None
                mock_run.assert_not_called()

    def test_returns_none_when_no_trusted_source(self, monkeypatch, tmp_path: Path):
        for key in ("BUILD_COMMIT_SHA", "GIT_COMMIT", "COMMIT_SHA"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("ENV", "production")
        with patch("app.core.canonical_commit.get_settings") as mock_settings:
            mock_settings.return_value = SimpleNamespace(
                BUILD_METADATA_PATH=str(tmp_path / "missing.json")
            )
            assert resolve_canonical_commit() is None

    def test_missing_metadata_outcome(self, monkeypatch):
        for key in ("BUILD_COMMIT_SHA", "GIT_COMMIT", "COMMIT_SHA"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("ENV", "production")
        with patch("app.core.canonical_commit.read_build_metadata") as mock_read:
            mock_read.return_value = MetadataReadResult(outcome=MetadataReadOutcome.MISSING)
            assert resolve_canonical_commit() is None
