"""
Tests for operator alerts (Kapitel 10).
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import app.admin.alerts.models  # noqa: F401
import app.admin.incident_models  # noqa: F401
from app.admin.alerts.evaluation_lock import alert_evaluation_lock
from app.admin.alerts.evaluation_service import run_alert_evaluation
from app.admin.alerts.lifecycle import (
    AlertCandidate,
    apply_candidate,
    auto_resolve_missing,
    acknowledge_alert,
)
from app.admin.alerts.registry import ALERT_REGISTRY, validate_registry
from app.admin.alerts.repository import AlertRepository
from app.admin.alerts.service import get_alert_summary, list_alerts, run_evaluation
from app.admin.alerts.models import OperatorAlertRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


def _operator(role: str = "operations") -> dict:
    return {"id": "operator-test", "display_name": "Test", "role": role}


def _settings(**kwargs):
    defaults = {"ADMIN_API_KEY": "test", "APP_NAME": "Test", "OPERATOR_ALERT_RECIPIENT": ""}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    tenant = TenantConfigRecord(
        tenant_id="T_ALERT",
        name="Alert Tenant",
        slug="alert-tenant",
        status="active",
        settings={"scheduler": {"run_mode": "manual"}},
        enabled_job_types=["lead"],
        allowed_integrations=[],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.add(tenant)
    session.commit()
    yield session
    session.close()


class TestAlertRegistry:
    def test_registry_unique_types(self):
        assert not validate_registry()

    def test_slice1_evaluators_present(self):
        assert "job.approval_stale" in ALERT_REGISTRY
        assert "job.stuck_processing" in ALERT_REGISTRY


class TestAlertLifecycle:
    def test_dedup_creates_once(self, db):
        definition = ALERT_REGISTRY["job.approval_stale"]
        candidate = AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key="tenant:T_ALERT:approval:a1:stale",
            scope_type="job",
            tenant_id="T_ALERT",
            related_job_id="job-1",
            integration_key=None,
            severity="warning",
            title="Stale",
            summary="Pending",
            safe_details={"source_type": "approval", "source_id": "approval:a1"},
            source_class="intern_db_detected",
            current_fingerprint="fp1",
        )
        action1, _ = apply_candidate(db, candidate, definition=definition, dry_run=False)
        db.commit()
        action2, _ = apply_candidate(db, candidate, definition=definition, dry_run=False)
        db.commit()
        assert action1 == "created"
        assert action2 == "updated"
        alerts, total = AlertRepository.list_alerts(db)
        assert total == 1
        assert alerts[0].occurrence_count == 2

    def test_suppressed_in_active_dedup(self, db):
        definition = ALERT_REGISTRY["job.approval_stale"]
        candidate = AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key="tenant:T_ALERT:approval:a2:stale",
            scope_type="job",
            tenant_id="T_ALERT",
            related_job_id=None,
            integration_key=None,
            severity="warning",
            title="Stale",
            summary="Pending",
            safe_details={},
            source_class="intern_db_detected",
            current_fingerprint="fp2",
        )
        apply_candidate(db, candidate, definition=definition, dry_run=False)
        db.commit()
        alert = AlertRepository.get_active_by_dedup_key(db, candidate.deduplication_key)
        alert.status = "suppressed"
        db.commit()
        action, _ = apply_candidate(db, candidate, definition=definition, dry_run=False)
        db.commit()
        assert action == "updated"

    def test_acknowledge(self, db):
        definition = ALERT_REGISTRY["job.stuck_processing"]
        candidate = AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key="tenant:T_ALERT:job:j1:stuck",
            scope_type="job",
            tenant_id="T_ALERT",
            related_job_id="j1",
            integration_key=None,
            severity="high",
            title="Stuck",
            summary="Stuck job",
            safe_details={"source_type": "job", "source_id": "job:j1"},
            source_class="intern_db_detected",
            current_fingerprint="fp3",
        )
        apply_candidate(db, candidate, definition=definition, dry_run=False)
        db.commit()
        alert = AlertRepository.get_active_by_dedup_key(db, candidate.deduplication_key)
        acknowledge_alert(db, alert, operator_id="op-1", version=alert.version)
        db.commit()
        assert alert.status == "acknowledged"


class TestAlertEvaluators:
    def _seed_stale_approval(self, db):
        db.add(
            ApprovalRequestRecord(
                approval_id=str(uuid4()),
                tenant_id="T_ALERT",
                job_id="job-1",
                state="pending",
                channel="internal",
                next_on_approve="email_send",
                created_at=datetime.now(timezone.utc) - timedelta(hours=30),
                updated_at=datetime.now(timezone.utc),
                request_payload={},
            )
        )
        db.commit()

    def _seed_stuck_job(self, db):
        db.add(
            JobRecord(
                job_id=str(uuid4()),
                tenant_id="T_ALERT",
                job_type="lead",
                status="processing",
                input_data={},
                result={},
                created_at=datetime.now(timezone.utc) - timedelta(hours=50),
                updated_at=datetime.now(timezone.utc) - timedelta(hours=50),
            )
        )
        db.commit()

    def test_evaluation_creates_alerts(self, db):
        self._seed_stale_approval(db)
        self._seed_stuck_job(db)
        result = run_alert_evaluation(
            db, settings=_settings(), dry_run=False, max_slice=1, operator_id="op"
        )
        assert result["status"] in ("completed", "partial")
        assert result["created_count"] >= 1
        summary = get_alert_summary(db)
        assert summary.total_open >= 1

    def test_evaluator_exception_isolation(self, db):
        self._seed_stale_approval(db)
        with patch(
            "app.admin.alerts.evaluators.evaluate_job_stuck_processing",
            side_effect=RuntimeError("boom"),
        ):
            result = run_alert_evaluation(db, settings=_settings(), max_slice=1)
        assert result["error_count"] >= 1
        assert result["created_count"] >= 0

    def test_auto_resolve(self, db):
        definition = ALERT_REGISTRY["job.approval_stale"]
        key = "tenant:T_ALERT:approval:gone:stale"
        candidate = AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key=key,
            scope_type="job",
            tenant_id="T_ALERT",
            related_job_id=None,
            integration_key=None,
            severity="warning",
            title="Stale",
            summary="x",
            safe_details={},
            source_class="intern_db_detected",
            current_fingerprint="fp",
        )
        apply_candidate(db, candidate, definition=definition, dry_run=False)
        db.commit()
        resolved = auto_resolve_missing(
            db, alert_type=definition.alert_type, active_keys=set(), dry_run=False
        )
        db.commit()
        assert resolved == 1


class TestEvaluationLock:
    def test_concurrent_lock_second_skips(self):
        engine = create_engine("sqlite:///:memory:")
        results: list[bool] = []

        def worker():
            with alert_evaluation_lock(engine) as acquired:
                results.append(acquired)

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        with alert_evaluation_lock(engine) as first:
            assert first is True
            t1.start()
            t2.start()
            t1.join(timeout=2)
            t2.join(timeout=2)
        assert False in results or len(results) == 0


class TestAlertSchemaRegistration:
    def test_tables_register(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        tables = set(inspect(engine).get_table_names())
        assert "operator_alerts" in tables
        assert "alert_evaluation_runs" in tables


class TestNotificationSeparation:
    def test_email_deferred_without_recipient(self, db):
        from app.admin.alerts.notification_service import enqueue_alert_notifications

        count = enqueue_alert_notifications(db, settings=_settings())
        assert count == 0


class TestNeedsHelpEnrichment:
    def test_enrich_adds_alert_fields(self, db):
        from app.admin.alerts.lifecycle import apply_candidate, AlertCandidate
        from app.admin.operations_triage import enrich_triage_rows_with_alerts

        definition = ALERT_REGISTRY["job.approval_stale"]
        candidate = AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key="tenant:T_ALERT:approval:x:stale",
            scope_type="job",
            tenant_id="T_ALERT",
            related_job_id="j",
            integration_key=None,
            severity="warning",
            title="T",
            summary="S",
            safe_details={"source_type": "approval", "source_id": "approval:x"},
            source_class="intern_db_detected",
            current_fingerprint="f",
        )
        apply_candidate(db, candidate, definition=definition, dry_run=False)
        db.commit()
        rows = [
            {
                "tenant_id": "T_ALERT",
                "source_type": "approval",
                "source_id": "approval:x",
                "title": "row",
            }
        ]
        enriched = enrich_triage_rows_with_alerts(db, rows)
        assert enriched[0]["related_alert_id"]
        assert len(enriched) == 1


class TestSlice2Evaluators:
    def test_scheduler_paused_no_alert(self, db):
        from app.admin.alerts.evaluators import evaluate_tenant_scheduler_failed
        from app.admin.alerts.registry import ALERT_REGISTRY

        tenant = db.query(TenantConfigRecord).filter_by(tenant_id="T_ALERT").one()
        tenant.settings = {
            "scheduler": {"run_mode": "paused"},
            "scheduler_state": {"last_status": "failed"},
        }
        db.commit()
        definition = ALERT_REGISTRY["tenant.scheduler_failed"]
        candidates = evaluate_tenant_scheduler_failed(db, definition)
        assert candidates == []

    def test_system_unknown_not_critical(self):
        from app.admin.alerts.system_signal_status import (
            allows_auto_alert,
            normalize_backup_status,
            severity_for_system_status,
        )

        status = normalize_backup_status(
            operation_status=None,
            age_hours=None,
            max_age_hours=25,
            source_available=True,
        )
        assert status == "not_configured"
        assert not allows_auto_alert(status)
        assert severity_for_system_status(status) is None


class TestDigest:
    def test_digest_uses_alerts_not_custom_severity(self, db):
        from app.admin.alerts.digest_service import generate_operator_digest
        from app.admin.alerts.lifecycle import apply_candidate, AlertCandidate
        from app.admin.alerts.registry import ALERT_REGISTRY

        definition = ALERT_REGISTRY["job.approval_stale"]
        candidate = AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key="tenant:T_ALERT:approval:digest:stale",
            scope_type="job",
            tenant_id="T_ALERT",
            related_job_id="j",
            integration_key=None,
            severity="warning",
            title="Digest alert",
            summary="From operator_alerts",
            safe_details={},
            source_class="intern_db_detected",
            current_fingerprint="digest-fp",
        )
        apply_candidate(db, candidate, definition=definition, dry_run=False)
        db.commit()
        digest = generate_operator_digest(db, tz_name="UTC")
        assert digest.content_json["items"]
        assert digest.content_json["items"][0]["kind"] == "open_alert"
        assert digest.content_json["items"][0]["severity"] == "warning"


class TestReopenPolicy:
    def test_reopen_existing_after_grace(self, db):
        from datetime import timedelta

        definition = ALERT_REGISTRY["job.failed_recent"]
        key = "tenant:T_ALERT:job:j-reopen:failed"
        candidate = AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key=key,
            scope_type="job",
            tenant_id="T_ALERT",
            related_job_id="j-reopen",
            integration_key=None,
            severity="warning",
            title="Failed",
            summary="x",
            safe_details={},
            source_class="intern_db_detected",
            current_fingerprint="fp-a",
        )
        apply_candidate(db, candidate, definition=definition, dry_run=False)
        db.commit()
        alert = AlertRepository.get_active_by_dedup_key(db, key)
        alert.status = "resolved"
        alert.resolved_at = datetime.now(timezone.utc) - timedelta(hours=2)
        db.commit()
        candidate.current_fingerprint = "fp-b"
        action, reopened = apply_candidate(db, candidate, definition=definition, dry_run=False)
        db.commit()
        assert action == "reopened"
        assert reopened is not None
        assert reopened.status == "open"


class TestNotificationFailureIsolation:
    def test_delivery_failure_does_not_change_alert_status(self, db):
        from unittest.mock import patch
        from uuid import uuid4

        from app.admin.alerts.lifecycle import apply_candidate, AlertCandidate
        from app.admin.alerts.models import NotificationDeliveryRecord
        from app.admin.alerts.notification_service import process_pending_deliveries

        definition = ALERT_REGISTRY["job.stuck_processing"]
        candidate = AlertCandidate(
            alert_type=definition.alert_type,
            deduplication_key="tenant:T_ALERT:job:notify:stuck",
            scope_type="job",
            tenant_id="T_ALERT",
            related_job_id="notify-job",
            integration_key=None,
            severity="high",
            title="Notify",
            summary="x",
            safe_details={},
            source_class="intern_db_detected",
            current_fingerprint="fp-n",
        )
        apply_candidate(db, candidate, definition=definition, dry_run=False)
        db.commit()
        alert = AlertRepository.get_active_by_dedup_key(db, candidate.deduplication_key)
        before_status = alert.status
        db.add(
            NotificationDeliveryRecord(
                id=str(uuid4()),
                alert_id=alert.id,
                digest_id=None,
                channel="email",
                recipient_ref="ops@example.com",
                status="pending",
                attempt_count=0,
                idempotency_key=f"{alert.id}:email:test",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        settings = _settings(OPERATOR_ALERT_RECIPIENT="ops@example.com")
        with patch(
            "app.workflows.action_executor.execute_action",
            side_effect=RuntimeError("smtp down"),
        ):
            stats = process_pending_deliveries(db, settings=settings)
        db.commit()
        db.refresh(alert)
        assert stats["failed"] >= 1
        assert alert.status == before_status
