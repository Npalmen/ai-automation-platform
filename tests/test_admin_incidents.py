"""
Tests for operator incident management (Kapitel 6).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.admin.incident_models import (
    IncidentRecord,
    IncidentSignalRecord,
    IncidentTenantRecord,
    IncidentTimelineEventRecord,
)
from app.admin.incident_repository import (
    IncidentConflictError,
    IncidentRepository,
)
from app.admin.incident_schemas import (
    ALLOWED_TRANSITIONS,
    IncidentCreateRequest,
    IncidentFieldUpdateRequest,
)
from app.admin.incidents import (
    IncidentClosedError,
    IncidentValidationError,
    assign_self,
    build_signal_snapshot,
    change_status,
    create_incident,
    resolve_available_incident_actions,
    resolve_signal_row,
)
from app.admin.operations_triage import _row
from app.repositories.postgres.database import Base


def _operator(role: str = "operations") -> dict:
    return {
        "id": "operator-test",
        "display_name": "Test Operator",
        "role": role,
    }


def _settings(**kwargs):
    defaults = {"ADMIN_API_KEY": "test-admin-key", "APP_NAME": "Test"}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _sample_triage_row():
    return _row(
        tenant_id="T_A",
        tenant_name="Acme",
        severity="critical",
        area="integration_reconciliation",
        title="Reconcile visma",
        detail="Needs reconcile",
        source_id="integration_event:1",
        source_type="integration_event",
        created_at="2026-01-01T00:00:00+00:00",
        retryable="no",
        external_impact="yes",
    )


class TestIncidentSchemaRegistration:
    def test_startup_import_creates_all_incident_tables(self):
        import app.admin.incident_models  # noqa: F401

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        tables = set(inspect(engine).get_table_names())
        assert "incidents" in tables
        assert "incident_tenants" in tables
        assert "incident_signals" in tables
        assert "incident_timeline_events" in tables


class TestIncidentSchemas:
    def test_create_rejects_owner_field(self):
        with pytest.raises(Exception):
            IncidentCreateRequest.model_validate(
                {
                    "title": "Test",
                    "severity": "warning",
                    "reason": "test",
                    "confirmation": True,
                    "owner_id": "x",
                }
            )

    def test_field_update_rejects_owner_field(self):
        with pytest.raises(Exception):
            IncidentFieldUpdateRequest.model_validate(
                {
                    "reason": "test",
                    "confirmation": True,
                    "expected_version": 1,
                    "owner_display_name": "x",
                }
            )


class TestSignalSnapshot:
    def test_build_snapshot_from_row(self):
        row = _sample_triage_row()
        snap = build_signal_snapshot(row)
        assert snap["signal_id"] == "integration_event:1"
        assert snap["source_type"] == "integration_event"
        assert snap["source_id"] == "1"
        assert snap["snapshot_title"] == "Reconcile visma"
        assert snap["snapshot_severity"] == "critical"

    def test_resolve_signal_exact_match_only(self):
        db = MagicMock()
        tenant_record = MagicMock()
        tenant_record.name = "Acme"
        row = _sample_triage_row()
        with patch(
            "app.admin.incidents.TenantConfigRepository.get",
            return_value=tenant_record,
        ), patch(
            "app.admin.incidents._build_tenant_triage",
            return_value=[row],
        ), patch(
            "app.admin.incidents.dedupe_and_normalize_signals",
            side_effect=lambda rows: rows,
        ):
            found = resolve_signal_row(
                db,
                tenant_id="T_A",
                signal_id="integration_event:1",
                app_settings=_settings(),
            )
            missing = resolve_signal_row(
                db,
                tenant_id="T_A",
                signal_id="integration_event:999",
                app_settings=_settings(),
            )
        assert found is not None
        assert missing is None


class TestAvailableActions:
    def test_closed_incident_blocks_writes(self):
        incident = MagicMock()
        incident.status = "closed"
        incident.owner_id = None
        actions = resolve_available_incident_actions(incident, "operations")
        assert actions
        assert all(action.allowed is False for action in actions)
        assert all(action.blocked_reason == "incident_closed" for action in actions)

    def test_open_incident_assign_self_allowed(self):
        incident = MagicMock()
        incident.status = "open"
        incident.owner_id = None
        actions = resolve_available_incident_actions(incident, "operations")
        assign = next(a for a in actions if a.action_id == "incident.assign_self")
        assert assign.allowed is True


class TestIncidentRepositorySqlite:
    @pytest.fixture
    def db(self):
        engine = create_engine("sqlite:///:memory:")
        tables = [
            IncidentRecord.__table__,
            IncidentTenantRecord.__table__,
            IncidentSignalRecord.__table__,
            IncidentTimelineEventRecord.__table__,
        ]
        Base.metadata.create_all(bind=engine, tables=tables)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    def test_atomic_update_version_conflict(self, db):
        incident = IncidentRepository.create_incident(
            db,
            title="Test",
            description=None,
            severity="warning",
            created_by="op",
            created_by_display_name="Op",
        )
        db.commit()
        with pytest.raises(IncidentConflictError):
            IncidentRepository.atomic_update_incident(
                db,
                incident.incident_id,
                99,
                values={"title": "Changed"},
            )

    def test_signal_unlink_soft_not_delete(self, db):
        incident = IncidentRepository.create_incident(
            db,
            title="Test",
            description=None,
            severity="warning",
            created_by="op",
            created_by_display_name="Op",
        )
        db.commit()
        IncidentRepository.link_signal(
            db,
            incident_id=incident.incident_id,
            signal_id="job:1",
            tenant_id="T_A",
            source_type="job",
            source_id="1",
            snapshot_title="Job",
            snapshot_summary="Detail",
            snapshot_severity="failed",
        )
        db.commit()
        IncidentRepository.unlink_signal(db, incident.incident_id, "job:1")
        db.commit()
        rows = db.query(IncidentSignalRecord).all()
        assert len(rows) == 1
        assert rows[0].unlinked_at is not None

    def test_duplicate_active_tenant_link_rejected(self, db):
        incident = IncidentRepository.create_incident(
            db,
            title="Test",
            description=None,
            severity="warning",
            created_by="op",
            created_by_display_name="Op",
        )
        db.commit()
        IncidentRepository.link_tenant(
            db,
            incident_id=incident.incident_id,
            tenant_id="T_A",
            tenant_name_snapshot="Acme",
        )
        db.commit()
        with pytest.raises(IncidentConflictError):
            IncidentRepository.link_tenant(
                db,
                incident_id=incident.incident_id,
                tenant_id="T_A",
                tenant_name_snapshot="Acme",
            )


class TestIncidentServiceWrites:
    def test_create_single_commit(self):
        db = MagicMock()
        incident = MagicMock()
        incident.incident_id = "INC_test"
        incident.version = 1
        commit_count = {"n": 0}

        def counting_commit():
            commit_count["n"] += 1

        db.commit = counting_commit

        with patch(
            "app.admin.incidents.IncidentRepository.create_incident",
            return_value=incident,
        ), patch(
            "app.admin.incidents.IncidentRepository.add_timeline_event",
        ), patch(
            "app.admin.incidents._add_audit_event_no_commit",
        ), patch(
            "app.admin.incidents.get_incident_detail",
            return_value=MagicMock(),
        ):
            create_incident(
                db,
                operator=_operator(),
                title="Outage",
                description="desc",
                severity="critical",
                tenant_ids=[],
                signal_links=[],
                reason="test",
                app_settings=_settings(),
            )
        assert commit_count["n"] == 1

    def test_closed_incident_note_blocked(self):
        db = MagicMock()
        incident = MagicMock()
        incident.status = "closed"
        incident.incident_id = "INC_closed"
        with patch(
            "app.admin.incidents.IncidentRepository.get_incident",
            return_value=incident,
        ):
            from app.admin.incidents import add_note

            with pytest.raises(IncidentClosedError):
                add_note(
                    db,
                    incident_id="INC_closed",
                    operator=_operator(),
                    message="note",
                )

    def test_status_transition_table(self):
        assert "investigating" in ALLOWED_TRANSITIONS["open"]
        assert ALLOWED_TRANSITIONS["closed"] == set()

    def test_same_status_raises_conflict(self):
        db = MagicMock()
        incident = MagicMock()
        incident.status = "open"
        incident.incident_id = "INC_1"
        with patch(
            "app.admin.incidents.IncidentRepository.get_incident",
            return_value=incident,
        ):
            with pytest.raises(IncidentConflictError):
                change_status(
                    db,
                    incident_id="INC_1",
                    operator=_operator(),
                    target_status="open",
                    reason="test",
                    resolution_summary=None,
                    expected_version=1,
                )

    def test_resolved_requires_summary(self):
        db = MagicMock()
        incident = MagicMock()
        incident.status = "investigating"
        incident.incident_id = "INC_1"
        with patch(
            "app.admin.incidents.IncidentRepository.get_incident",
            return_value=incident,
        ):
            with pytest.raises(IncidentValidationError):
                change_status(
                    db,
                    incident_id="INC_1",
                    operator=_operator(),
                    target_status="resolved",
                    reason="test",
                    resolution_summary=None,
                    expected_version=1,
                )

    def test_assign_self_sets_owner_from_operator(self):
        db = MagicMock()
        incident = MagicMock()
        incident.status = "open"
        incident.incident_id = "INC_1"
        updated = MagicMock()
        updated.version = 2
        updated.status = "acknowledged"
        with patch(
            "app.admin.incidents.IncidentRepository.get_incident",
            return_value=incident,
        ), patch(
            "app.admin.incidents.IncidentRepository.atomic_update_incident",
            return_value=updated,
        ) as atomic, patch(
            "app.admin.incidents.IncidentRepository.add_timeline_event",
        ), patch(
            "app.admin.incidents._add_audit_event_no_commit",
        ), patch(
            "app.admin.incidents._audit_tenant_id",
            return_value="_operator",
        ):
            assign_self(
                db,
                incident_id="INC_1",
                operator=_operator(),
                reason="taking ownership",
                expected_version=1,
            )
        values = atomic.call_args.kwargs["values"]
        assert values["owner_id"] == "operator-test"
        assert values["owner_display_name"] == "Test Operator"


class TestIncidentRoutes:
    def test_list_incidents_requires_auth(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        response = client.get("/admin/incidents")
        assert response.status_code == 401

    def test_create_incident_read_only_forbidden(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        with patch(
            "app.core.admin_auth.resolve_authenticated_operator",
            return_value=_operator("read_only"),
        ):
            response = client.post(
                "/admin/incidents",
                json={
                    "title": "Test",
                    "severity": "warning",
                    "reason": "test reason",
                    "confirmation": True,
                },
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
        assert response.status_code == 403
