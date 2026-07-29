"""Tests for production pilot P1 observability."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.production_pilot.constants import PILOT_TENANT_ID
from app.production_pilot.observability.constants import (
    GO_FOR_P2_APPROVAL_GMAIL,
    NO_GO_FOR_P2_APPROVAL_GMAIL,
)
from app.production_pilot.observability.daily_report import build_p1_daily_report
from app.production_pilot.observability.message_filters import is_real_pilot_inbound_message
from app.production_pilot.observability.operational_evaluation import evaluate_p1_operational_evidence
from app.production_pilot.observability.redaction import provider_message_ref_hash
from app.production_pilot.observability.repository import ProductionPilotReviewRepository
from app.production_pilot.observability.review_service import submit_message_review, validate_review_payload
from app.production_pilot.observability.runtime_readiness import build_p1_runtime_readiness
from app.production_pilot.p1_activation import build_p1_tenant_record
from app.repositories.postgres.database import Base
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.end_customer_shadow_models import (
    EndCustomerShadowMatchProposalRecord,
    EndCustomerShadowObservationRecord,
)
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.production_pilot.observability.models import ProductionPilotMessageReviewRecord


def _observability_tables():
    return [
        JobRecord.__table__,
        TenantConfigRecord.__table__,
        OAuthCredentialRecord.__table__,
        ProductionPilotMessageReviewRecord.__table__,
        DecisionRecordRow.__table__,
        ApprovalRequestRecord.__table__,
        EndCustomerShadowObservationRecord.__table__,
        EndCustomerShadowMatchProposalRecord.__table__,
    ]


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=_observability_tables())
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _seed_tenant(db):
    record = build_p1_tenant_record()
    db.add(
        TenantConfigRecord(
            tenant_id=PILOT_TENANT_ID,
            name="Production Pilot 01",
            slug="production-pilot-01",
            status="pilot",
            lifecycle_status="active",
            config_version=1,
            enabled_job_types=record["enabled_job_types"],
            allowed_integrations=record["allowed_integrations"],
            auto_actions=record["auto_actions"],
            settings=record["settings"],
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.add(
        OAuthCredentialRecord(
            tenant_id=PILOT_TENANT_ID,
            provider="google_mail",
            access_token="token",
            refresh_token="refresh",
        )
    )
    db.commit()


def _make_job(*, message_id: str, created_at: datetime, synthetic: bool = False) -> JobRecord:
    input_data = {
        "subject": "Pilot inquiry",
        "source": {
            "system": "gmail",
            "message_id": message_id,
            "thread_id": "thread-1",
            "synthetic": synthetic,
        },
    }
    if synthetic:
        input_data["production_pilot_preflight"] = True
    return JobRecord(
        job_id=str(uuid4()),
        tenant_id=PILOT_TENANT_ID,
        job_type="lead",
        status="completed",
        input_data=input_data,
        result={"classification": "lead", "confidence": 0.9},
        created_at=created_at,
        updated_at=created_at,
    )


def test_message_filter_excludes_synthetic_and_live_eval():
    assert is_real_pilot_inbound_message({"source": {"system": "gmail", "message_id": "abc123"}})
    assert not is_real_pilot_inbound_message({"source": {"system": "gmail", "message_id": "synthetic-1"}})
    assert not is_real_pilot_inbound_message({"live_eval": True, "source": {"system": "gmail", "message_id": "x"}})


def test_daily_report_uses_live_records_not_p0(db):
    _seed_tenant(db)
    day = date(2026, 7, 27)
    created = datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc)
    db.add(_make_job(message_id="msg-real-1", created_at=created))
    db.add(_make_job(message_id="synthetic-abc", created_at=created, synthetic=True))
    db.commit()
    report = build_p1_daily_report(db, tenant_id=PILOT_TENANT_ID, day=day, runtime_sha="abc1234")
    assert report["activation_stage"] == "P1"
    assert report["intake"]["provider_inbound_count"] == 1
    assert report["intake"]["correlation_gaps"] == 0


def test_daily_report_is_tenant_isolated(db):
    _seed_tenant(db)
    other = _make_job(message_id="other-tenant", created_at=datetime.now(timezone.utc))
    other.tenant_id = "T_OTHER"
    db.add(other)
    db.commit()
    report = build_p1_daily_report(db, tenant_id=PILOT_TENANT_ID, day=date.today())
    assert report["tenant_id"] == PILOT_TENANT_ID
    assert report["intake"]["provider_inbound_count"] == 0


def test_review_requires_operator_identity():
    failures = validate_review_payload(
        {
            "tenant_id": PILOT_TENANT_ID,
            "provider_message_ref_hash": "a" * 64,
            "job_id": "job-1",
            "classification_verdict": "correct",
            "extraction_verdict": "acceptable",
            "routing_verdict": "correct",
            "manual_review_verdict": "not_required",
            "shadow_observation_verdict": "acceptable",
            "match_proposal_verdict": "not_applicable",
        }
    )
    assert any("reviewed_by" in item for item in failures)


def test_review_is_tenant_isolated_and_idempotent(db):
    _seed_tenant(db)
    job = _make_job(message_id="msg-review-1", created_at=datetime.now(timezone.utc))
    db.add(job)
    db.commit()
    ref_hash = provider_message_ref_hash(PILOT_TENANT_ID, "msg-review-1")
    payload = {
        "tenant_id": PILOT_TENANT_ID,
        "provider_message_ref_hash": ref_hash,
        "job_id": job.job_id,
        "reviewed_by": "operator-a",
        "classification_verdict": "correct",
        "extraction_verdict": "acceptable",
        "routing_verdict": "correct",
        "manual_review_verdict": "not_required",
        "shadow_observation_verdict": "acceptable",
        "match_proposal_verdict": "not_applicable",
    }
    first = submit_message_review(db, payload)
    payload["classification_verdict"] = "ambiguous"
    second = submit_message_review(db, payload)
    assert first["id"] == second["id"]
    assert second["classification_verdict"] == "ambiguous"
    stored = ProductionPilotReviewRepository.get_by_ref(
        db, tenant_id=PILOT_TENANT_ID, provider_message_ref_hash=ref_hash
    )
    assert stored is not None
    assert "message_text" not in ProductionPilotReviewRepository.to_dict(stored)


def test_operational_evaluator_requires_thresholds(db):
    _seed_tenant(db)
    report = evaluate_p1_operational_evidence(
        db,
        tenant_id=PILOT_TENANT_ID,
        start_date=date(2026, 7, 27),
        end_date=date(2026, 7, 29),
        runtime_sha="abc1234567890",
        expected_runtime_sha="abc1234567890",
    )
    assert report["p2_readiness"] == NO_GO_FOR_P2_APPROVAL_GMAIL
    assert report["operational_pass"] is False


def test_operational_evaluator_passes_with_full_window(db):
    _seed_tenant(db)
    start = date(2026, 7, 25)
    message_jobs: dict[str, str] = {}
    for day_offset in range(3):
        day = start + timedelta(days=day_offset)
        created = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
        count = 9 if day_offset < 2 else 7
        for idx in range(count):
            message_id = f"msg-{day_offset}-{idx}"
            job = _make_job(message_id=message_id, created_at=created)
            db.add(job)
            message_jobs[message_id] = job.job_id
    db.commit()
    for message_id, job_id in message_jobs.items():
        submit_message_review(
            db,
            {
                "tenant_id": PILOT_TENANT_ID,
                "provider_message_ref_hash": provider_message_ref_hash(PILOT_TENANT_ID, message_id),
                "job_id": job_id,
                "reviewed_by": "operator-a",
                "classification_verdict": "correct",
                "extraction_verdict": "acceptable",
                "routing_verdict": "correct",
                "manual_review_verdict": "not_required",
                "shadow_observation_verdict": "acceptable",
                "match_proposal_verdict": "not_applicable",
            },
        )
    report = evaluate_p1_operational_evidence(
        db,
        tenant_id=PILOT_TENANT_ID,
        start_date=start,
        end_date=start + timedelta(days=2),
        runtime_sha="abc1234567890",
        expected_runtime_sha="abc1234567890",
    )
    assert report["real_message_count"] == 25
    assert report["p2_readiness"] == GO_FOR_P2_APPROVAL_GMAIL


def test_runtime_readiness_does_not_expose_oauth_token(db):
    _seed_tenant(db)
    report = build_p1_runtime_readiness(
        db,
        tenant_id=PILOT_TENANT_ID,
        expected_runtime_sha="abc1234567890",
        backup_reference="backup-test",
    )
    assert report["oauth_token_exposed"] is False
    assert "token" not in str(report).lower() or "oauth_token_exposed" in str(report)


def test_daily_report_fixed_from_p1_record(db):
    _seed_tenant(db)
    report = build_p1_daily_report(db, tenant_id=PILOT_TENANT_ID, day=date.today())
    assert report["activation_stage"] == "P1"
