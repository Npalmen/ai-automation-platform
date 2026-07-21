"""Migration 016 backfill verification (Slice B) — isolated fixtures, idempotency, side effects."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.admin.integrations.selection_backfill import (
    backfill_tenant_selections,
    classify_integration_for_backfill,
)
from app.admin.integrations.selection_models import parse_selections_map
from app.admin.integrations.selection_sync import sync_allowed_integrations_from_selections
from app.repositories.postgres.database import Base
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.schema_migrations import _INTEGRATION_SELECTION_MIGRATION_STATEMENTS
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from tests.onboarding_db_tables import onboarding_sqlite_tables


def _tenant(
    tenant_id: str,
    *,
    allowed: list[str] | None = None,
    job_types: list[str] | None = None,
    settings: dict | None = None,
) -> TenantConfigRecord:
    return TenantConfigRecord(
        tenant_id=tenant_id,
        name=tenant_id,
        slug=tenant_id.lower(),
        status="active",
        allowed_integrations=allowed or [],
        enabled_job_types=job_types or [],
        settings=settings or {},
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    tables = onboarding_sqlite_tables()
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestMigration016Structure:
    def test_schema_migration_statements_define_backfill_run_table(self):
        joined = "\n".join(_INTEGRATION_SELECTION_MIGRATION_STATEMENTS)
        assert "integration_selection_backfill_runs" in joined
        assert "ix_integration_selection_backfill_runs_started" in joined


class TestBackfillFixtureMatrix:
    def test_niklas_like_tenant(self, db):
        record = _tenant(
            "T_NIKLAS_LIKE",
            allowed=["google_mail", "google_sheets", "visma"],
            job_types=["customer_inquiry", "invoice"],
        )
        db.add(record)
        db.commit()
        for provider in ("google_mail", "visma"):
            db.add(
                OAuthCredentialRecord(
                    tenant_id=record.tenant_id,
                    provider=provider,
                    access_token=f"token-{provider}",
                    refresh_token=f"refresh-{provider}",
                )
            )
        db.commit()

        report = backfill_tenant_selections(db, record.tenant_id, dry_run=True)
        decisions = {d.integration_key: d for d in report.decisions}
        assert decisions["google_mail"].selection_status == "selected_required"
        assert decisions["google_mail"].migration_review_required is False
        assert decisions["visma"].selection_status == "selected_required"
        assert decisions["fortnox"].selection_status == "not_selected"
        assert decisions["google_sheets"].selection_status == "selected_optional"
        assert decisions["google_sheets"].migration_review_required is True

    def test_allowlist_without_selections(self, db):
        record = _tenant("T_ALLOW_ONLY", allowed=["google_mail"], job_types=[])
        db.add(record)
        db.commit()
        decision = classify_integration_for_backfill(db, record, "google_mail")
        assert decision.selection_status == "selected_optional"
        assert decision.migration_review_required is True
        assert decision.reason == "allowed_uncertain"

    def test_credential_without_allowlist(self, db):
        record = _tenant("T_CRED_ONLY", allowed=[], job_types=[])
        db.add(record)
        db.add(
            OAuthCredentialRecord(
                tenant_id=record.tenant_id,
                provider="visma",
                access_token="enc-visma-access",
                refresh_token="enc-visma-refresh",
            )
        )
        db.commit()
        decision = classify_integration_for_backfill(db, record, "visma")
        assert decision.selection_status == "selected_optional"
        assert decision.migration_review_required is True
        assert decision.reason == "credential_without_allowlist"

    def test_explicit_selections_skipped_on_backfill(self, db):
        record = _tenant(
            "T_EXPLICIT",
            allowed=["google_mail"],
            settings={
                "integrations": {
                    "selections": {
                        "google_mail": {
                            "integration_key": "google_mail",
                            "selection_status": "selected_optional",
                            "migration_review_required": False,
                            "requirement_source": "manual",
                            "configured_at": "2026-07-21T00:00:00Z",
                            "configured_by": "operator:test",
                        }
                    }
                }
            },
        )
        db.add(record)
        db.commit()
        report = backfill_tenant_selections(db, record.tenant_id, dry_run=False)
        assert report.skipped is True
        assert report.updated is False

    def test_legacy_gmail_key_normalizes(self, db):
        record = _tenant("T_LEGACY_GMAIL", allowed=["gmail"], job_types=[])
        db.add(record)
        db.commit()
        decision = classify_integration_for_backfill(db, record, "google_mail")
        assert decision.selection_status == "selected_optional"
        assert decision.migration_review_required is True

    def test_no_integration_signal(self, db):
        record = _tenant("T_EMPTY", allowed=[], job_types=[])
        db.add(record)
        db.commit()
        decision = classify_integration_for_backfill(db, record, "fortnox")
        assert decision.selection_status == "not_selected"
        assert decision.reason == "no_signals"

    def test_coming_later_in_legacy_allowlist_is_cautious(self, db):
        record = _tenant("T_FORTNOX_LEGACY", allowed=["fortnox"], job_types=[])
        db.add(record)
        db.commit()
        decision = classify_integration_for_backfill(db, record, "fortnox")
        assert decision.selection_status == "selected_optional"
        assert decision.migration_review_required is True


class TestBackfillIdempotencyAndSafety:
    def test_backfill_persists_system_actor_and_is_idempotent(self, db):
        record = _tenant(
            "T_IDEM",
            allowed=["google_mail", "google_sheets", "visma"],
            job_types=["customer_inquiry", "invoice"],
        )
        db.add(record)
        for provider in ("google_mail", "visma"):
            db.add(
                OAuthCredentialRecord(
                    tenant_id=record.tenant_id,
                    provider=provider,
                    access_token=f"static-{provider}",
                    refresh_token=f"static-refresh-{provider}",
                )
            )
        db.commit()

        before_jobs = db.execute(text("SELECT COUNT(*) FROM jobs")).scalar() if _table_exists(db, "jobs") else 0

        first = backfill_tenant_selections(db, record.tenant_id, dry_run=False)
        db.commit()
        db.refresh(record)
        snapshot = dict(record.settings or {})
        cred_visma = db.get(
            OAuthCredentialRecord, {"tenant_id": record.tenant_id, "provider": "visma"}
        )
        assert cred_visma is not None
        assert cred_visma.access_token == "static-visma"

        selections = parse_selections_map(snapshot["integrations"]["selections"])
        assert selections["google_mail"].configured_by == "system:migration_016"

        second = backfill_tenant_selections(db, record.tenant_id, dry_run=False)
        db.commit()
        db.refresh(record)
        assert second.skipped is True
        assert record.settings == snapshot

        after_jobs = db.execute(text("SELECT COUNT(*) FROM jobs")).scalar() if _table_exists(db, "jobs") else 0
        assert before_jobs == after_jobs == 0

        gates = sync_allowed_integrations_from_selections(db, record, dry_run=True, fail_closed=True)
        assert gates.enabled_external_writes == []

    def test_dry_run_does_not_persist(self, db):
        record = _tenant(
            "T_DRY",
            allowed=["google_mail", "visma"],
            job_types=["invoice"],
        )
        db.add(record)
        db.commit()
        report = backfill_tenant_selections(db, record.tenant_id, dry_run=True)
        db.refresh(record)
        assert report.skipped is True
        assert not (record.settings or {}).get("integrations", {}).get("selections")


def _table_exists(db, name: str) -> bool:
    try:
        return inspect(db.bind).has_table(name)
    except Exception:
        return False


@pytest.mark.integration_db
def test_postgres_migration_016_table_when_database_available():
    import os

    database_url = os.environ.get("SLICE_B_TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url or "sqlite" in database_url:
        pytest.skip("SLICE_B_TEST_DATABASE_URL or DATABASE_URL postgres not configured")

    pytest.importorskip("psycopg2")
    from sqlalchemy import create_engine as create_pg_engine

    from app.repositories.postgres.migration_runner import verify_ci_postgres_schema_provisioned

    engine = create_pg_engine(database_url)
    verify_ci_postgres_schema_provisioned(engine)
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE tablename = 'integration_selection_backfill_runs'"
            )
        ).fetchone()
    assert result is not None
