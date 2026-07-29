"""Repository root script resolution tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.evaluation.live.campaign.repo_paths import (
    AUTOMATIC_CANARY_REQUIRED_SCRIPT_MISSING,
    resolve_repository_root,
    resolve_required_script,
    resolve_scripts_directory,
    validate_required_scripts,
)


def test_resolve_repository_root_finds_scripts_not_app_scripts():
    root = resolve_repository_root()
    scripts = resolve_scripts_directory()
    assert scripts == root / "scripts"
    assert (scripts / "run_full_system_testbot_campaign.py").is_file()
    assert not (root / "app" / "scripts").exists()


def test_resolve_required_script_independent_of_cwd(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    path = resolve_required_script("snapshot_live_eval_tenant_config.py")
    assert path.is_file()
    assert path.parent.name == "scripts"


def test_missing_script_fail_closed():
    issues = validate_required_scripts(("definitely_missing_script.py",))
    assert len(issues) == 1
    assert AUTOMATIC_CANARY_REQUIRED_SCRIPT_MISSING in issues[0]


def test_resolve_required_script_raises_for_missing():
    with pytest.raises(FileNotFoundError, match=AUTOMATIC_CANARY_REQUIRED_SCRIPT_MISSING):
        resolve_required_script("missing_automatic_canary_script.py")
