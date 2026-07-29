"""P1 evaluation contract tests."""

from __future__ import annotations

from app.production_pilot.status import PRODUCTION_PILOT_ACTIVE, PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED
from app.production_pilot.p1_evaluation import evaluate_p1_acceptance, run_p1_evaluation
from app.production_pilot.p1_preflight import run_p1_preflight


def test_p1_evaluation_passes_with_threshold_metrics():
    preflight = run_p1_preflight(backup_reference="backup-test-p1")
    report = run_p1_evaluation(backup_reference="backup-test-p1", preflight=preflight)
    assert report["status"] == "PASS"
    assert PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED in report["qualifications"]
    assert PRODUCTION_PILOT_ACTIVE in report["qualifications"]


def test_p1_evaluation_fails_on_external_write():
    result = evaluate_p1_acceptance(
        {
            "inbound_messages": 25,
            "operation_days": 3,
            "gmail_replies": 0,
            "external_writes": 1,
            "duplicate_jobs": 0,
            "unauthorized_adapter_invocations": 0,
            "cross_tenant_findings": 0,
            "automatic_verified_facts": 0,
            "automatic_customer_links": 0,
            "automatic_merges": 0,
            "message_loss": 0,
            "manual_review_working": True,
            "shadow_provenance_complete": True,
            "kill_switches_working": True,
        }
    )
    assert result["status"] == "FAIL"
