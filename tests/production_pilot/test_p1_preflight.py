"""P1 preflight contract tests."""

from __future__ import annotations

from app.production_pilot.constants import P1_MAX_SYNTHETIC_INBOUND
from app.production_pilot.p1_preflight import run_p1_preflight
from app.production_pilot.p1_readiness import build_p1_readiness
from app.production_pilot.status import PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED


def test_p1_readiness_ready():
    readiness = build_p1_readiness(backup_reference="backup-test-p1")
    assert readiness["overall_status"] == "ready_for_p1_activation"


def test_p1_preflight_passes():
    report = run_p1_preflight(backup_reference="backup-test-p1")
    assert report["status"] == "PASS"
    assert report["gmail_replies"] == 0
    assert report["non_gmail_writes"] == 0
    assert report["synthetic_inbound_count"] <= P1_MAX_SYNTHETIC_INBOUND
    assert report["preflight_qualification"] == PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED


def test_p1_preflight_creates_shadow_observations():
    report = run_p1_preflight(backup_reference="backup-test-p1")
    assert len(report["shadow_observations"]) >= 1
