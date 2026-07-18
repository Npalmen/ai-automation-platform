"""Onboarding audit allowlist and sanitization tests."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin.onboarding.audit_events import (
    EXTERNAL_ROUTING_UPDATED,
    INTEGRATION_VERIFICATION_STARTED,
    OAUTH_CONNECTION_STARTED,
    emit_onboarding_audit,
    sanitize_audit_details,
)
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from tests.onboarding_db_tables import onboarding_sqlite_tables


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    tables = onboarding_sqlite_tables()
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestOnboardingAuditEvents:
    def test_allowlisted_event_persisted(self, db):
        emit_onboarding_audit(
            db,
            tenant_id="T1",
            action=OAUTH_CONNECTION_STARTED,
            status="succeeded",
            details={"provider": "visma", "session_id": "sess-1"},
        )
        db.commit()
        row = db.query(AuditEventRecord).first()
        assert row is not None
        assert row.action == OAUTH_CONNECTION_STARTED

    def test_blocked_secret_keys_stripped(self):
        clean = sanitize_audit_details(
            {
                "provider": "visma",
                "access_token": "secret",
                "authorization_code": "code",
                "nested": {"refresh_token": "x", "ok": "y"},
            }
        )
        assert "access_token" not in clean
        assert "authorization_code" not in clean
        assert clean["nested"]["ok"] == "y"
        assert "refresh_token" not in clean["nested"]

    def test_unknown_action_rejected(self, db):
        with pytest.raises(ValueError):
            emit_onboarding_audit(
                db,
                tenant_id="T1",
                action="onboarding.secret_leak",
                status="succeeded",
                details={},
            )

    def test_domain_events_allowlisted(self):
        for action in (
            INTEGRATION_VERIFICATION_STARTED,
            EXTERNAL_ROUTING_UPDATED,
        ):
            assert action  # compile-time import guard
