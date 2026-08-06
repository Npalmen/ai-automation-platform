"""PostgreSQL migration / runtime-schema tests for live-eval 026 (R4 registration context)."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urlunparse
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text

from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
)
from app.repositories.postgres.migration_runner import (
    LATEST_MIGRATION_VERSION,
    MIGRATIONS_THROUGH_025,
    ORDERED_MIGRATION_FILES,
    apply_pre_migration_baseline,
    apply_versioned_sql_migrations,
    column_exists,
    read_migration_state,
    reset_public_schema,
    verify_ci_postgres_schema_provisioned,
)
from app.repositories.postgres.schema_migrations import (
    _LIVE_EVAL_026_MIGRATION_STATEMENTS,
    ensure_runtime_schema,
)

pytestmark = pytest.mark.integration_db

_026_COLUMNS = (
    "campaign_type",
    "execution_mode",
    "manifest_hash",
    "registration_context",
)
_026_INDEX = "ix_live_eval_runs_campaign_type"
_ISOLATED_DB_NAME = "ai_platform_mig026_test"


def _rewrite_db_name(url: str, db_name: str) -> str:
    parsed = urlparse(url)
    return urlunparse(parsed._replace(path=f"/{db_name}"))


def _postgres_url() -> str:
    """Isolated throwaway DB — never reset the shared eval database."""
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url or "sqlite" in url:
        pytest.skip("DATABASE_URL postgres required for integration_db migration tests")
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": _ISOLATED_DB_NAME},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{_ISOLATED_DB_NAME}"'))
    except Exception as exc:
        pytest.skip(f"Could not provision isolated migration DB: {exc}")
    finally:
        admin.dispose()
    return _rewrite_db_name(url, _ISOLATED_DB_NAME)


def _index_names(engine, table_name: str) -> set[str]:
    return {index["name"] for index in inspect(engine).get_indexes(table_name)}


def _assert_026_artifacts(engine) -> None:
    for column_name in _026_COLUMNS:
        assert column_exists(engine, "live_eval_runs", column_name), column_name
    assert _026_INDEX in _index_names(engine, "live_eval_runs")


def _seed_live_eval_run(engine, *, evaluation_run_id: str | None = None) -> str:
    run_id = evaluation_run_id or str(uuid4())
    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO live_eval_runs (
                    evaluation_run_id, tenant_id, scenario_id, attempt_id,
                    transport_mode, ai_mode, expected_sender, expected_recipient,
                    status, created_by, expires_at, config_hash
                ) VALUES (
                    :rid, 'TENANT_LIVE_EVAL', 'PTB-DCQ-0000', 1,
                    'live_gmail', 'fixture_ai', 'sender@example.com', 'recipient@example.com',
                    'registered', 'migration_026_test', :expires, 'cfghash'
                )
                """
            ),
            {"rid": run_id, "expires": expires},
        )
    return run_id


def test_ordered_migration_files_end_with_026():
    assert ORDERED_MIGRATION_FILES[-1] == "026_live_eval_r4_registration_context.sql"
    assert LATEST_MIGRATION_VERSION == "026"
    assert MIGRATIONS_THROUGH_025[-1] == "025_production_pilot_message_reviews.sql"
    assert len(_LIVE_EVAL_026_MIGRATION_STATEMENTS) == 5


def test_migration_026_full_chain_creates_columns_and_index():
    engine = create_engine(_postgres_url())
    try:
        reset_public_schema(engine)
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, ORDERED_MIGRATION_FILES)
        _assert_026_artifacts(engine)
        state = read_migration_state(engine)
        assert state["latest_version"] == "026"
        assert state["latest_file"] == "026_live_eval_r4_registration_context.sql"
        assert "026_live_eval_r4_registration_context.sql" in state["applied_files"]
    finally:
        engine.dispose()


def test_ensure_runtime_schema_backfills_026_from_through_025():
    engine = create_engine(_postgres_url())
    try:
        reset_public_schema(engine)
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, MIGRATIONS_THROUGH_025)
        for column_name in _026_COLUMNS:
            assert not column_exists(engine, "live_eval_runs", column_name)
        assert _026_INDEX not in _index_names(engine, "live_eval_runs")

        ensure_runtime_schema(engine)
        _assert_026_artifacts(engine)
    finally:
        engine.dispose()


def test_ensure_runtime_schema_026_idempotent_and_preserves_rows():
    engine = create_engine(_postgres_url())
    try:
        reset_public_schema(engine)
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, MIGRATIONS_THROUGH_025)
        run_id = _seed_live_eval_run(engine)

        ensure_runtime_schema(engine)
        ensure_runtime_schema(engine)
        _assert_026_artifacts(engine)

        with engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT evaluation_run_id, campaign_type, registration_context "
                    "FROM live_eval_runs WHERE evaluation_run_id = :rid"
                ),
                {"rid": run_id},
            ).mappings().one()
        assert row["evaluation_run_id"] == run_id
        assert row["campaign_type"] is None
        assert row["registration_context"] is None
    finally:
        engine.dispose()


def test_registration_context_jsonb_after_runtime_safeguard():
    engine = create_engine(_postgres_url())
    try:
        reset_public_schema(engine)
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, MIGRATIONS_THROUGH_025)
        ensure_runtime_schema(engine)
        run_id = _seed_live_eval_run(engine)
        payload = {
            "campaign_type": R4_LIVE_QUALITY_CAMPAIGN_TYPE,
            "planned_gmail_send": True,
            "automatic_gmail": False,
            "production_activation": False,
        }
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE live_eval_runs
                    SET campaign_type = :ctype,
                        execution_mode = 'r4_reviewed_live_candidate',
                        manifest_hash = :mhash,
                        registration_context = CAST(:ctx AS jsonb)
                    WHERE evaluation_run_id = :rid
                    """
                ),
                {
                    "ctype": R4_LIVE_QUALITY_CAMPAIGN_TYPE,
                    "mhash": "b" * 64,
                    "ctx": json.dumps(payload),
                    "rid": run_id,
                },
            )
            stored = conn.execute(
                text(
                    "SELECT registration_context->>'automatic_gmail' AS ag, "
                    "registration_context->>'production_activation' AS pa "
                    "FROM live_eval_runs WHERE evaluation_run_id = :rid"
                ),
                {"rid": run_id},
            ).mappings().one()
        assert stored["ag"] == "false"
        assert stored["pa"] == "false"
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "drop_sql,needle",
    [
        ("ALTER TABLE live_eval_runs DROP COLUMN campaign_type", "campaign_type"),
        ("ALTER TABLE live_eval_runs DROP COLUMN execution_mode", "execution_mode"),
        ("ALTER TABLE live_eval_runs DROP COLUMN manifest_hash", "manifest_hash"),
        (
            "ALTER TABLE live_eval_runs DROP COLUMN registration_context",
            "registration_context",
        ),
        ("DROP INDEX IF EXISTS ix_live_eval_runs_campaign_type", "ix_live_eval_runs_campaign_type"),
    ],
)
def test_read_migration_state_blocks_when_026_artifact_missing(drop_sql: str, needle: str):
    engine = create_engine(_postgres_url())
    try:
        reset_public_schema(engine)
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, ORDERED_MIGRATION_FILES)
        with engine.begin() as conn:
            conn.execute(text(drop_sql))
        with pytest.raises(RuntimeError) as exc:
            read_migration_state(engine)
        assert "026" in str(exc.value)
        assert needle in str(exc.value)
    finally:
        engine.dispose()


def test_ci_schema_verification_requires_026():
    engine = create_engine(_postgres_url())
    try:
        reset_public_schema(engine)
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, MIGRATIONS_THROUGH_025)
        with pytest.raises(RuntimeError) as exc:
            verify_ci_postgres_schema_provisioned(engine)
        assert "026" in str(exc.value)

        ensure_runtime_schema(engine)
        state = verify_ci_postgres_schema_provisioned(engine)
        assert state["latest_version"] == "026"
    finally:
        engine.dispose()


def test_r4_automatic_gmail_and_production_activation_remain_false():
    from app.evaluation.live.constants import REVIEWED_LIVE_LLM_BODY
    from app.evaluation.profile_testbot.qualification.coworker_r4_registration_contract import (
        R4RegistrationContext,
        validate_r4_registration_contract,
    )

    assert REVIEWED_LIVE_LLM_BODY == "reviewed_live_llm_body"
    defaults = R4RegistrationContext.model_fields
    assert defaults["automatic_gmail"].default is False
    assert defaults["production_activation"].default is False
    assert callable(validate_r4_registration_contract)
