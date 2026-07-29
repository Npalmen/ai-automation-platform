"""P0 preflight contract tests."""

from __future__ import annotations

from app.production_pilot.constants import P0_MAX_SYNTHETIC_INBOUND
from app.production_pilot.preflight import run_p0_preflight
from app.production_pilot.stages import stage_capabilities
from app.production_pilot.status import PRODUCTION_PILOT_RELEASE_READY


def test_preflight_uses_synthetic_data_only():
    report = run_p0_preflight(backup_reference="backup-test-preflight")
    assert report["synthetic_inbound_count"] <= P0_MAX_SYNTHETIC_INBOUND
    assert all(item.get("synthetic") for item in report["processed_messages"])


def test_preflight_zero_replies_and_writes():
    report = run_p0_preflight(backup_reference="backup-test-preflight")
    assert report["gmail_replies"] == 0
    assert report["non_gmail_writes"] == 0


def test_preflight_registers_release_ready_on_pass():
    report = run_p0_preflight(backup_reference="backup-test-preflight")
    assert report["status"] == "PASS"
    assert report["qualification"] == PRODUCTION_PILOT_RELEASE_READY


def test_p2_requires_approval_capability():
    caps = stage_capabilities("P2")
    assert caps["approvals"] is True


def test_p3_requires_pre_write_safety_budget():
    caps = stage_capabilities("P3")
    assert caps["automatic_gmail"] is True
    assert caps["automatic_verify"] is False
    assert caps["automatic_customer_link"] is False
    assert caps["automatic_merge"] is False
