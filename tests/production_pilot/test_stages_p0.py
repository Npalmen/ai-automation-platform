"""P0 stage and write-budget contract tests."""

from __future__ import annotations

import pytest

from app.production_pilot.constants import PILOT_TENANT_ID
from app.production_pilot.gates import (
    ProductionPilotGateViolation,
    enforce_production_pilot_inbox_gates,
    is_production_pilot_tenant,
)
from app.production_pilot.kill_switches import apply_p0_baseline
from app.production_pilot.stages import stage_capabilities
from app.production_pilot.tenant_baseline import build_p0_tenant_record, validate_pilot_tenant_record


def test_pilot_tenant_id_unique():
    assert is_production_pilot_tenant(PILOT_TENANT_ID)
    assert not is_production_pilot_tenant("T_NIKLAS_DEMO_001")


def test_p0_capabilities_zero_external_writes():
    caps = stage_capabilities("P0")
    assert caps["gmail_reply_budget"] == 0
    assert caps["non_gmail_write_budget"] == 0
    assert caps["gmail_intake"] is False
    assert caps["automatic_gmail"] is False
    assert caps["shadow_intake"] is False
    assert caps["sheets_monday_visma"] is False


def test_p0_baseline_blocks_gmail_intake():
    settings = apply_p0_baseline()
    with pytest.raises(ProductionPilotGateViolation):
        enforce_production_pilot_inbox_gates(
            tenant_id=PILOT_TENANT_ID,
            dry_run=False,
            settings=settings,
        )


def test_p1_cannot_create_gmail_reply_by_budget():
    caps = stage_capabilities("P1")
    assert caps["gmail_reply_budget"] == 0


def test_pilot_tenant_record_validates_p0():
    record = build_p0_tenant_record()
    assert validate_pilot_tenant_record(record) == []


def test_riskflags_default_false_in_baseline_record():
    record = build_p0_tenant_record()
    automation = record["settings"]["automation"]
    assert automation["automatic_gmail_replies"] is False
    assert record["settings"]["scheduler"]["run_mode"] == "paused"
