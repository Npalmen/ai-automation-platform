"""Tests for package-build worktree verification."""

from __future__ import annotations

from app.evaluation.profile_testbot.qualification.package_build_worktree import classify_porcelain_lines


class TestPackageBuildWorktree:
    def test_clean_checkout_allowed(self):
        is_clean, blocked = classify_porcelain_lines([])
        assert is_clean is True
        assert blocked == []

    def test_storage_status_only_allowed(self):
        lines = [
            "?? storage/status/digital-coworker-human-review-40-abc.md",
            " M storage/status/report.json",
        ]
        is_clean, blocked = classify_porcelain_lines(lines)
        assert is_clean is True
        assert blocked == []

    def test_modified_tracked_file_blocked(self):
        is_clean, blocked = classify_porcelain_lines([" M app/main.py"])
        assert is_clean is False
        assert blocked == [" M app/main.py"]

    def test_untracked_docs_blocked(self):
        is_clean, blocked = classify_porcelain_lines(["?? docs/plans/foo.md"])
        assert is_clean is False
        assert "docs/plans/foo.md" in blocked[0]

    def test_untracked_scripts_blocked(self):
        is_clean, blocked = classify_porcelain_lines(["?? scripts/local_helper.py"])
        assert is_clean is False

    def test_untracked_app_or_tests_blocked(self):
        for path in ("?? app/workflows/foo.py", "?? tests/test_foo.py"):
            is_clean, blocked = classify_porcelain_lines([path])
            assert is_clean is False, path
