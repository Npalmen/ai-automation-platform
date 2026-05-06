from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


_REPO = "app.repositories.postgres.tenant_config_repository.TenantConfigRepository"


def _demo_ctrl(enabled: bool = True) -> dict:
    return {"automation": {"demo_mode": enabled}}


def test_manual_inbox_sync_is_blocked_in_demo_mode():
    from app.main import trigger_inbox_sync

    db = MagicMock()
    with (
        patch(f"{_REPO}.get_settings", return_value=_demo_ctrl(True)),
        patch("app.main._run_gmail_inbox_sync") as mock_sync,
        patch("app.main.get_settings") as mock_settings,
    ):
        result = trigger_inbox_sync(db=db, tenant_id="T_DEMO")

    assert result["status"] == "demo_mode"
    assert result["created_jobs"] == 0
    mock_sync.assert_not_called()
    mock_settings.assert_not_called()


def test_scheduler_skips_inbox_and_digest_in_demo_mode():
    from app.main import _run_scheduler_pass

    db = MagicMock()
    ctrl = {
        "automation": {"demo_mode": True},
        "scheduler": {"run_mode": "scheduled"},
        "notifications": {
            "enabled": True,
            "recipient_email": "ops@example.com",
            "frequency": "daily",
            "send_hour": 8,
        },
    }
    now = datetime(2026, 5, 6, 10, 0, 0, tzinfo=timezone.utc)

    with (
        patch(f"{_REPO}.get_settings", return_value=ctrl),
        patch(f"{_REPO}.update_settings") as mock_save,
        patch("app.main._run_gmail_inbox_sync") as mock_sync,
        patch("app.main.dispatch_action") as mock_dispatch,
        patch("app.main.get_settings"),
    ):
        result = _run_scheduler_pass("T_DEMO", db, now)

    assert result["inbox_sync"] == {"skipped": True, "reason": "demo_mode"}
    assert result["digest"] == {"skipped": True, "reason": "demo_mode"}
    assert result["error"] is None
    mock_sync.assert_not_called()
    mock_dispatch.assert_not_called()
    mock_save.assert_called_once()


def test_demo_seed_requires_demo_mode():
    from app.main import demo_seed

    with patch(f"{_REPO}.get_settings", return_value=_demo_ctrl(False)):
        with pytest.raises(HTTPException) as exc_info:
            demo_seed(request=None, db=MagicMock(), tenant_id="T_LIVE")

    assert exc_info.value.status_code == 400
    assert "demo_mode" in exc_info.value.detail


def test_demo_seed_creates_synthetic_jobs_for_enabled_types():
    from app.main import _DemoSeedRequest, demo_seed

    db = MagicMock()
    processed_jobs = []

    def _create_job(_db, job):
        job.job_id = f"job-{len(processed_jobs) + 1}"
        job.status = MagicMock(value="created")
        return job

    def _run(job, job_type_value, _db):
        job.status = MagicMock(value="completed")
        processed_jobs.append((job_type_value, job.input_data))
        return job

    with (
        patch(f"{_REPO}.get_settings", return_value=_demo_ctrl(True)),
        patch("app.main.get_tenant_config", return_value={"enabled_job_types": ["lead", "invoice"]}),
        patch("app.main.JobRepository.create_job", side_effect=_create_job),
        patch("app.main._run_verification_pipeline", side_effect=_run),
        patch("app.main.create_audit_event") as mock_audit,
        patch("app.main.set_current_tenant"),
    ):
        result = demo_seed(
            request=_DemoSeedRequest(include_types=["lead", "invoice"]),
            db=db,
            tenant_id="T_DEMO",
        )

    assert result["demo_mode"] is True
    assert len(result["created_jobs"]) == 2
    assert [j["job_type"] for j in result["created_jobs"]] == ["lead", "invoice"]
    assert all(input_data["demo_seed"] is True for _, input_data in processed_jobs)
    assert all(input_data["source"]["system"] == "demo_seed" for _, input_data in processed_jobs)
    mock_audit.assert_called_once()
