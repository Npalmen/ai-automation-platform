"""Tenant intake readiness tests for R3 live eval."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.evaluation.live.tenant_intake_readiness import (
    INTAKE_CUTOFF_MAX_AGE_SECONDS,
    run_r3_tenant_intake_readiness,
)
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


def _fresh_cutoff() -> str:
    return (
        datetime.now(timezone.utc) - timedelta(seconds=60)
    ).replace(microsecond=0).isoformat()


def _seed_tenant(
    db,
    *,
    tenant_id: str = LIVE_EVAL_TENANT_ID,
    cutoff: str | None = _fresh_cutoff(),
    enabled: bool = True,
    is_test: bool = True,
    lifecycle: str = "active",
    integrations: list[str] | None = None,
    job_types: list[str] | None = None,
) -> TenantConfigRecord:
    intake: dict = {"enabled": enabled}
    if cutoff is not None:
        intake["intake_cutoff_at"] = cutoff
    row = TenantConfigRecord(
        tenant_id=tenant_id,
        name="Live Eval",
        slug="tenant-live-eval",
        status="active",
        lifecycle_status=lifecycle,
        is_test_tenant=is_test,
        allowed_integrations=integrations or ["google_mail"],
        enabled_job_types=job_types or ["lead", "customer_inquiry", "invoice"],
        settings={"intake": intake},
    )
    db.add(row)
    db.commit()
    return row


def test_tenant_missing_fails(db, live_eval_env):
    result = run_r3_tenant_intake_readiness(db, tenant_id=LIVE_EVAL_TENANT_ID)
    assert not result.tenant_config_exists
    assert not result.tenant_intake_ready
    assert "tenant_config missing" in result.blockers


def test_active_tenant_without_cutoff_fails(db, live_eval_env):
    _seed_tenant(db, cutoff=None)
    result = run_r3_tenant_intake_readiness(db, tenant_id=LIVE_EVAL_TENANT_ID)
    assert not result.intake_cutoff_present
    assert not result.tenant_intake_ready


def test_empty_cutoff_fails(db, live_eval_env):
    _seed_tenant(db, cutoff="")
    result = run_r3_tenant_intake_readiness(db, tenant_id=LIVE_EVAL_TENANT_ID)
    assert not result.intake_cutoff_present
    assert not result.tenant_intake_ready


def test_invalid_cutoff_fails(db, live_eval_env):
    _seed_tenant(db, cutoff="not-a-timestamp")
    result = run_r3_tenant_intake_readiness(db, tenant_id=LIVE_EVAL_TENANT_ID)
    assert result.intake_cutoff_present
    assert not result.intake_cutoff_parseable
    assert not result.tenant_intake_ready


def test_cutoff_in_future_fails(db, live_eval_env):
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    _seed_tenant(db, cutoff=future)
    result = run_r3_tenant_intake_readiness(db, tenant_id=LIVE_EVAL_TENANT_ID)
    assert not result.intake_cutoff_not_future
    assert not result.tenant_intake_ready


def test_stale_cutoff_fails(db, live_eval_env):
    stale = (
        datetime.now(timezone.utc) - timedelta(seconds=INTAKE_CUTOFF_MAX_AGE_SECONDS + 60)
    ).isoformat()
    _seed_tenant(db, cutoff=stale)
    result = run_r3_tenant_intake_readiness(db, tenant_id=LIVE_EVAL_TENANT_ID)
    assert not result.intake_cutoff_fresh
    assert not result.tenant_intake_ready


def test_fresh_seeded_cutoff_passes(db, live_eval_env):
    _seed_tenant(db)
    result = run_r3_tenant_intake_readiness(db, tenant_id=LIVE_EVAL_TENANT_ID)
    assert result.tenant_intake_ready
    assert result.intake_cutoff_fresh
    assert result.required_integrations_present
    assert result.required_job_types_present


def test_intake_disabled_fails(db, live_eval_env):
    _seed_tenant(db, enabled=False)
    result = run_r3_tenant_intake_readiness(db, tenant_id=LIVE_EVAL_TENANT_ID)
    assert not result.intake_enabled
    assert not result.tenant_intake_ready


def test_non_test_tenant_fails(db, live_eval_env):
    _seed_tenant(db, is_test=False)
    result = run_r3_tenant_intake_readiness(db, tenant_id=LIVE_EVAL_TENANT_ID)
    assert not result.is_test_tenant
    assert not result.tenant_intake_ready


def test_wrong_tenant_fails(db, live_eval_env):
    result = run_r3_tenant_intake_readiness(db, tenant_id="OTHER_TENANT")
    assert not result.tenant_id_match
    assert not result.tenant_intake_ready


def test_missing_google_mail_fails(db, live_eval_env):
    _seed_tenant(db, integrations=["visma"])
    result = run_r3_tenant_intake_readiness(db, tenant_id=LIVE_EVAL_TENANT_ID)
    assert not result.required_integrations_present
    assert not result.tenant_intake_ready


def test_missing_job_type_fails(db, live_eval_env):
    _seed_tenant(db, job_types=["lead"])
    result = run_r3_tenant_intake_readiness(db, tenant_id=LIVE_EVAL_TENANT_ID)
    assert not result.required_job_types_present
    assert not result.tenant_intake_ready


def test_process_delivery_readiness_uses_tenant_gate(db, live_eval_env):
    from app.repositories.postgres.live_eval_models import LiveEvalRunRow
    from app.evaluation.profile_testbot.qualification.coworker_r3_mutation_contract import (
        validate_r3_process_delivery_readiness,
    )

    now = datetime.now(timezone.utc)
    row = LiveEvalRunRow(
        evaluation_run_id="run-tenant-gate",
        tenant_id=LIVE_EVAL_TENANT_ID,
        scenario_id="PTB-DCQ-0000",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="r3_frozen_approved_body",
        status="registered",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="cfg",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
    )
    db.add(row)
    db.commit()

    result = validate_r3_process_delivery_readiness(
        db, row=row, tenant_id=LIVE_EVAL_TENANT_ID
    )
    assert not result.process_delivery_path_ready
    assert any("tenant_config missing" in b for b in result.blockers)


def test_orphan_attempt_5_not_counted_as_approved_reply():
    from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
        ORPHANED_R3_INBOUND_TRIGGERS,
    )

    orphan5 = next(o for o in ORPHANED_R3_INBOUND_TRIGGERS if o["orphan_id"] == "orphaned_attempt_5")
    assert orphan5["evaluation_run_id"] == "b5bbe7ab-7148-4366-8fba-bd92921481f4"
    assert orphan5["exclude_from_approved_reply_count"] is True
    assert orphan5["approved_reply_sent"] is False


def test_pre_execute_blocks_without_tenant(db, live_eval_env, tmp_path):
    from pathlib import Path

    from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
        build_r3_frozen_execution_rows,
        load_approval_artifact,
        load_manifest_file,
        validate_r3_pre_execute_gates,
    )

    root = Path(__file__).resolve().parents[3]
    manifest_path = root / "storage/status/digital-coworker-r3-canary-manifest-8b9a046.json"
    approval_path = root / "storage/status/digital-coworker-r3-manual-send-approval-8b9a046.json"
    if not manifest_path.is_file() or not approval_path.is_file():
        pytest.skip("manifest/approval fixtures missing")
    manifest = load_manifest_file(manifest_path)
    approval = load_approval_artifact(approval_path)
    render_rows = build_r3_frozen_execution_rows(manifest=manifest, campaign_id="jit-test")
    gates = validate_r3_pre_execute_gates(
        runtime_sha="8b9a046090f33083411240c016c553a5fb54554c",
        repo_root=root,
        render_rows=render_rows,
        approval=approval,
        recipient_email="recipient@eval.test",
        manifest=manifest,
    )
    assert gates["ready"] is False
    assert gates["tenant_intake_ready"] is False
