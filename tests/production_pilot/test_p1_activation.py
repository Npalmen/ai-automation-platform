"""P1 activation contract tests."""

from __future__ import annotations

import pytest

from app.production_pilot.constants import PILOT_TENANT_ID
from app.production_pilot.gates import (
    ProductionPilotGateViolation,
    enforce_production_pilot_inbox_gates,
    validate_approvals_allowed,
)
from app.production_pilot.kill_switches import apply_p1_activation
from app.production_pilot.p1_activation import build_p1_tenant_record, validate_p1_tenant_record
from app.production_pilot.stages import validate_stage_transition


def test_p0_to_p1_transition_allowed():
    validate_stage_transition("P0", "P1")


def test_p1_to_p3_transition_blocked():
    with pytest.raises(Exception):
        validate_stage_transition("P1", "P3")


def test_p1_tenant_record_validates():
    record = build_p1_tenant_record()
    assert validate_p1_tenant_record(record) == []
    assert record["tenant_id"] == PILOT_TENANT_ID


def test_p1_allows_gmail_intake():
    settings = apply_p1_activation()
    enforce_production_pilot_inbox_gates(
        tenant_id=PILOT_TENANT_ID,
        dry_run=False,
        settings=settings,
    )


def test_p1_blocks_approvals():
    settings = apply_p1_activation()
    with pytest.raises(ProductionPilotGateViolation):
        validate_approvals_allowed(settings)
