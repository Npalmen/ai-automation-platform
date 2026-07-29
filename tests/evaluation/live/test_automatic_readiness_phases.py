"""Phase-separated automatic Gmail canary readiness tests."""

from __future__ import annotations

import json

import pytest

from app.evaluation.live.campaign.automatic_action_contract import CANARY_AUTO_ACTIONS
from app.evaluation.live.campaign.automatic_readiness import (
    AUTOMATION_PHASE_ACTIVE_CANARY,
    AUTOMATION_PHASE_PRE_SEED,
    AUTOMATION_PHASE_RESTORED,
    PHASE_MISMATCH_ERROR,
    validate_automatic_automation_readiness,
)
from app.evaluation.live.campaign.readiness import build_full_system_testbot_readiness
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache
from app.evaluation.live.campaign.tenant_automation_lifecycle import hash_auto_actions
from app.evaluation.live.config import get_live_eval_config


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_REPLIES", "1")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_SENDS", "1")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    clear_campaign_registry_cache()
    yield
    clear_campaign_registry_cache()
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def _mock_tenant(monkeypatch, *, auto_actions, settings=None, allowed_integrations=None):
    class _Row:
        def __init__(self):
            self.auto_actions = auto_actions
            self.settings = settings or {}
            self.allowed_integrations = allowed_integrations or ["google_mail"]

    row = _Row()

    monkeypatch.setattr(
        "app.evaluation.live.campaign.tenant_automation_lifecycle._read_auto_actions",
        lambda tenant_id: dict(auto_actions),
    )
    monkeypatch.setattr(
        "app.evaluation.live.campaign.automatic_readiness._read_tenant_record",
        lambda tenant_id: row,
    )
    return row


def test_pre_seed_blocks_broad_automation(monkeypatch):
    _mock_tenant(monkeypatch, auto_actions={"lead": "auto"})
    issues, matrix = validate_automatic_automation_readiness(
        automation_phase=AUTOMATION_PHASE_PRE_SEED,
    )
    assert issues
    assert matrix["automation_phase"] == AUTOMATION_PHASE_PRE_SEED


def test_pre_seed_accepts_manual_baseline(monkeypatch):
    _mock_tenant(monkeypatch, auto_actions={"lead": "manual", "unknown": "manual"})
    issues, _matrix = validate_automatic_automation_readiness(
        automation_phase=AUTOMATION_PHASE_PRE_SEED,
    )
    assert [issue for issue in issues if "already enabled" in issue] == []


def test_active_canary_accepts_authorized_lead_auto(monkeypatch, tmp_path):
    baseline_actions = {"lead": "manual", "unknown": "manual"}
    _mock_tenant(monkeypatch, auto_actions=dict(CANARY_AUTO_ACTIONS))
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "tenant_id": "TENANT_LIVE_EVAL",
                "auto_actions": baseline_actions,
                "config_hash": hash_auto_actions(baseline_actions),
            }
        ),
        encoding="utf-8",
    )
    issues, matrix = validate_automatic_automation_readiness(
        automation_phase=AUTOMATION_PHASE_ACTIVE_CANARY,
        baseline_snapshot_path=snapshot,
    )
    assert [i for i in issues if "mismatch" in i and "phase" in i] == []
    assert matrix["pre_run_config_hash"] != matrix["runtime_config_hash"]


def test_active_canary_blocks_monday_integration(monkeypatch, tmp_path):
    baseline_actions = {"lead": "manual"}
    _mock_tenant(
        monkeypatch,
        auto_actions=dict(CANARY_AUTO_ACTIONS),
        allowed_integrations=["google_mail", "monday"],
    )
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "tenant_id": "TENANT_LIVE_EVAL",
                "auto_actions": baseline_actions,
                "config_hash": hash_auto_actions(baseline_actions),
            }
        ),
        encoding="utf-8",
    )
    issues, _matrix = validate_automatic_automation_readiness(
        automation_phase=AUTOMATION_PHASE_ACTIVE_CANARY,
        baseline_snapshot_path=snapshot,
    )
    assert any("monday" in issue for issue in issues)


def test_restored_requires_hash_match(monkeypatch, tmp_path):
    actions = {"lead": "manual", "unknown": "manual"}
    _mock_tenant(monkeypatch, auto_actions=actions)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(
        json.dumps(
            {
                "tenant_id": "TENANT_LIVE_EVAL",
                "auto_actions": actions,
                "config_hash": hash_auto_actions(actions),
            }
        ),
        encoding="utf-8",
    )
    issues, matrix = validate_automatic_automation_readiness(
        automation_phase=AUTOMATION_PHASE_RESTORED,
        baseline_snapshot_path=snapshot,
    )
    assert issues == []
    assert matrix["post_run_config_hash"] == matrix["pre_run_config_hash"]


def test_missing_automation_phase_fails_readiness(monkeypatch):
    _mock_tenant(monkeypatch, auto_actions={"lead": "manual"})
    report = build_full_system_testbot_readiness(
        campaign_type="automatic-gmail-canary",
        selected_scenario_ids=("TBA01_safe_lead_auto_reply", "TBA02_unknown_auto_hold"),
        automation_phase=None,
    )
    assert not report.ready
    assert any(PHASE_MISMATCH_ERROR in issue for issue in report.issues)


def test_cleanup_restores_hash_after_readiness_failure(monkeypatch, tmp_path):
    from app.evaluation.live.campaign.tenant_automation_lifecycle import (
        run_lifecycle_cleanup,
        write_snapshot_file,
        snapshot_tenant_config,
        TenantAutomationSnapshot,
    )

    baseline = {"lead": "manual", "unknown": "manual"}
    snapshot = TenantAutomationSnapshot(
        tenant_id="TENANT_LIVE_EVAL",
        auto_actions=baseline,
        config_hash=hash_auto_actions(baseline),
    )
    path = write_snapshot_file(snapshot, tmp_path / "snap.json")

    states = [dict(CANARY_AUTO_ACTIONS), dict(baseline)]

    def _fake_read(tenant_id):
        return states[-1]

    def _fake_write(tenant_id, auto_actions):
        states.append(dict(auto_actions))

    monkeypatch.setattr(
        "app.evaluation.live.campaign.tenant_automation_lifecycle._read_auto_actions",
        _fake_read,
    )
    monkeypatch.setattr(
        "app.evaluation.live.campaign.tenant_automation_lifecycle._write_auto_actions",
        _fake_write,
    )

    report = run_lifecycle_cleanup(path)
    assert report.restoration_status == "restored"
    assert report.post_run_config_hash == report.pre_run_config_hash


def test_readiness_cli_accepts_active_core_automation_phase():
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/full_system_testbot_readiness.py",
            "--campaign-type",
            "automatic-gmail-core",
            "--automation-phase",
            "active_core",
        ],
        capture_output=True,
        text=True,
        cwd=repo_root,
    )
    assert "invalid choice: 'active_core'" not in (proc.stderr or "")
