"""Runtime schema safeguard for columns that create_all cannot add to existing tables.

Also provides provision_tenant_defaults() for seeding tenant-specific settings at startup.
"""
import json
import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

log = logging.getLogger(__name__)

# Each entry: (table, column, DDL_type)
# ADD COLUMN IF NOT EXISTS is idempotent — safe to run on every startup.
_REQUIRED_COLUMNS: list[tuple[str, str, str]] = [
    ("tenant_configs", "settings", "JSON"),
    ("tenant_configs", "slug", "VARCHAR"),
    ("tenant_configs", "status", "VARCHAR DEFAULT 'active'"),
    ("tenant_configs", "created_at", "TIMESTAMPTZ"),
    ("tenant_configs", "updated_at", "TIMESTAMPTZ"),
]

_REQUIRED_TABLES: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS tenant_api_keys (
        key_id      VARCHAR(36)  PRIMARY KEY,
        tenant_id   VARCHAR      NOT NULL,
        key_hash    TEXT         NOT NULL UNIQUE,
        key_hint    VARCHAR(8)   NOT NULL,
        is_active   BOOLEAN      NOT NULL DEFAULT TRUE,
        created_at  TIMESTAMPTZ  NOT NULL,
        revoked_at  TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_tenant_api_keys_tenant_id ON tenant_api_keys (tenant_id)",
    """
    CREATE TABLE IF NOT EXISTS oauth_credentials (
        tenant_id    VARCHAR      NOT NULL,
        provider     VARCHAR      NOT NULL,
        access_token TEXT         NOT NULL,
        refresh_token TEXT,
        expires_at   TIMESTAMPTZ,
        scopes       VARCHAR,
        metadata_json JSON,
        connected_at TIMESTAMPTZ  DEFAULT NOW(),
        updated_at   TIMESTAMPTZ,
        PRIMARY KEY (tenant_id, provider)
    )
    """,
]

_ONBOARDING_MIGRATION_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS onboarding_sessions (
        id                      VARCHAR(36)  PRIMARY KEY,
        tenant_id               VARCHAR(32)  NOT NULL,
        status                  VARCHAR(32)  NOT NULL,
        current_step            VARCHAR(32)  NOT NULL,
        version                 INTEGER      NOT NULL DEFAULT 1,
        readiness_check_version INTEGER      NOT NULL DEFAULT 0,
        created_at              TIMESTAMPTZ  NOT NULL,
        updated_at              TIMESTAMPTZ  NOT NULL,
        completed_at            TIMESTAMPTZ,
        activated_at            TIMESTAMPTZ,
        created_by_operator_id  VARCHAR(128) NOT NULL,
        last_updated_by_operator_id VARCHAR(128) NOT NULL,
        cancel_reason           TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_onboarding_sessions_tenant_id ON onboarding_sessions (tenant_id)",
    "CREATE INDEX IF NOT EXISTS ix_onboarding_sessions_status ON onboarding_sessions (status)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_onboarding_sessions_open_per_tenant
        ON onboarding_sessions (tenant_id)
        WHERE status IN ('draft', 'in_progress', 'blocked', 'ready_for_review', 'ready_for_activation')
    """,
    """
    CREATE TABLE IF NOT EXISTS onboarding_step_states (
        session_id              VARCHAR(36)  NOT NULL,
        step_key                VARCHAR(32)  NOT NULL,
        step_status             VARCHAR(32)  NOT NULL,
        verification_level      VARCHAR(32)  NOT NULL DEFAULT 'declared',
        blocking_issues         JSON,
        warnings                JSON,
        updated_at              TIMESTAMPTZ  NOT NULL,
        verified_at             TIMESTAMPTZ,
        updated_by_operator_id  VARCHAR(128),
        PRIMARY KEY (session_id, step_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_onboarding_step_states_session_id ON onboarding_step_states (session_id)",
    """
    CREATE TABLE IF NOT EXISTS onboarding_step_drafts (
        session_id              VARCHAR(36)  NOT NULL,
        step_key                VARCHAR(32)  NOT NULL,
        payload                 JSON         NOT NULL,
        updated_at              TIMESTAMPTZ  NOT NULL,
        PRIMARY KEY (session_id, step_key)
    )
    """,
]

_SLICE2B_MIGRATION_STATEMENTS: list[str] = [
    "ALTER TABLE onboarding_sessions ADD COLUMN IF NOT EXISTS integration_state_revision INTEGER NOT NULL DEFAULT 0",
    """
    CREATE TABLE IF NOT EXISTS onboarding_oauth_states (
        state_id                VARCHAR(64)  PRIMARY KEY,
        state_hash              TEXT         NOT NULL,
        session_id              VARCHAR(36)  NOT NULL,
        tenant_id               VARCHAR(32)  NOT NULL,
        operator_id             VARCHAR(128) NOT NULL,
        provider                VARCHAR(32)  NOT NULL,
        redirect_target         TEXT         NOT NULL,
        expires_at              TIMESTAMPTZ  NOT NULL,
        consumed_at             TIMESTAMPTZ,
        created_at              TIMESTAMPTZ  NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_onboarding_oauth_states_session ON onboarding_oauth_states (session_id, provider)",
    "CREATE INDEX IF NOT EXISTS ix_onboarding_oauth_states_expires ON onboarding_oauth_states (expires_at)",
    """
    CREATE TABLE IF NOT EXISTS onboarding_integration_verifications (
        session_id                      VARCHAR(36)  NOT NULL,
        integration_key                 VARCHAR(32)  NOT NULL,
        verification_status             VARCHAR(32)  NOT NULL,
        source_class                    VARCHAR(32)  NOT NULL,
        verified_at                     TIMESTAMPTZ,
        verified_by_operator_id         VARCHAR(128),
        config_fingerprint              VARCHAR(64),
        integration_state_revision_at_verify INTEGER,
        error_code                      VARCHAR(64),
        environment_safe_metadata         JSON,
        updated_at                      TIMESTAMPTZ  NOT NULL,
        PRIMARY KEY (session_id, integration_key)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_onboarding_integration_verifications_session ON onboarding_integration_verifications (session_id)",
    """
    CREATE TABLE IF NOT EXISTS tenant_resource_bindings (
        id                      VARCHAR(36)  PRIMARY KEY,
        resource_type           VARCHAR(64)  NOT NULL,
        resource_id             VARCHAR(256) NOT NULL,
        tenant_id               VARCHAR(32)  NOT NULL,
        session_id              VARCHAR(36)  NOT NULL,
        status                  VARCHAR(16)  NOT NULL,
        bound_at                TIMESTAMPTZ  NOT NULL,
        bound_by_operator_id    VARCHAR(128) NOT NULL,
        released_at             TIMESTAMPTZ
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_tenant_resource_bindings_active
        ON tenant_resource_bindings (resource_type, resource_id)
        WHERE status = 'active'
    """,
    "CREATE INDEX IF NOT EXISTS ix_tenant_resource_bindings_tenant ON tenant_resource_bindings (tenant_id, status)",
]

_INTEGRATION_OAUTH_STATE_MIGRATION_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS integration_oauth_states (
        state_id                VARCHAR(64)  PRIMARY KEY,
        state_hash              TEXT         NOT NULL,
        tenant_id               VARCHAR(32)  NOT NULL,
        operator_id             VARCHAR(128) NOT NULL,
        provider                VARCHAR(32)  NOT NULL,
        redirect_target         TEXT         NOT NULL,
        expires_at              TIMESTAMPTZ  NOT NULL,
        consumed_at             TIMESTAMPTZ,
        created_at              TIMESTAMPTZ  NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_integration_oauth_states_tenant ON integration_oauth_states (tenant_id, provider)",
    "CREATE INDEX IF NOT EXISTS ix_integration_oauth_states_expires ON integration_oauth_states (expires_at)",
]

_OPERATOR_ALERTS_MIGRATION_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS operator_alerts (
        id                          VARCHAR(36)  PRIMARY KEY,
        alert_type                  VARCHAR(64)  NOT NULL,
        deduplication_key           VARCHAR(256) NOT NULL,
        scope_type                  VARCHAR(32)  NOT NULL,
        tenant_id                   VARCHAR(32),
        related_job_id              VARCHAR(64),
        integration_key             VARCHAR(32),
        severity                    VARCHAR(16)  NOT NULL,
        status                      VARCHAR(16)  NOT NULL,
        title                       VARCHAR(256) NOT NULL,
        summary                     TEXT         NOT NULL,
        safe_details                JSON         NOT NULL DEFAULT '{}',
        source                      VARCHAR(64)  NOT NULL DEFAULT 'evaluation_engine',
        source_class                VARCHAR(32)  NOT NULL DEFAULT 'intern_db_detected',
        source_version              VARCHAR(32)  NOT NULL DEFAULT '1',
        first_detected_at           TIMESTAMPTZ  NOT NULL,
        last_detected_at            TIMESTAMPTZ  NOT NULL,
        occurrence_count            INTEGER      NOT NULL DEFAULT 1,
        last_evaluated_at           TIMESTAMPTZ  NOT NULL,
        acknowledged_at             TIMESTAMPTZ,
        acknowledged_by             VARCHAR(128),
        snoozed_until               TIMESTAMPTZ,
        resolved_at                 TIMESTAMPTZ,
        resolution_reason           TEXT,
        current_fingerprint         VARCHAR(128) NOT NULL,
        created_at                  TIMESTAMPTZ  NOT NULL,
        updated_at                  TIMESTAMPTZ  NOT NULL,
        version                     INTEGER      NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_operator_alerts_status_severity ON operator_alerts (status, severity, last_detected_at)",
    "CREATE INDEX IF NOT EXISTS ix_operator_alerts_tenant_status ON operator_alerts (tenant_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_operator_alerts_alert_type ON operator_alerts (alert_type)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_operator_alerts_active_dedup_key
        ON operator_alerts (deduplication_key)
        WHERE status IN ('open', 'acknowledged', 'snoozed', 'suppressed')
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_evaluation_runs (
        run_id                      VARCHAR(36)  PRIMARY KEY,
        started_at                  TIMESTAMPTZ  NOT NULL,
        completed_at                TIMESTAMPTZ,
        status                      VARCHAR(32)  NOT NULL,
        scope                       VARCHAR(32)  NOT NULL DEFAULT 'platform',
        dry_run                     BOOLEAN      NOT NULL DEFAULT FALSE,
        evaluator_version           VARCHAR(32)  NOT NULL DEFAULT '1',
        created_count               INTEGER      NOT NULL DEFAULT 0,
        updated_count               INTEGER      NOT NULL DEFAULT 0,
        resolved_count              INTEGER      NOT NULL DEFAULT 0,
        error_count                 INTEGER      NOT NULL DEFAULT 0,
        evaluator_results_json      JSON         NOT NULL DEFAULT '[]',
        safe_error_summary          TEXT,
        triggered_by_operator_id    VARCHAR(128)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_alert_evaluation_runs_started_at ON alert_evaluation_runs (started_at)",
    """
    CREATE TABLE IF NOT EXISTS operator_digests (
        id                          VARCHAR(36)  PRIMARY KEY,
        digest_date                 DATE         NOT NULL,
        timezone                    VARCHAR(64)  NOT NULL DEFAULT 'Europe/Stockholm',
        generated_at                TIMESTAMPTZ  NOT NULL,
        period_start                TIMESTAMPTZ  NOT NULL,
        period_end                  TIMESTAMPTZ  NOT NULL,
        content_json                JSON         NOT NULL DEFAULT '{}',
        delivery_status             VARCHAR(32)  NOT NULL DEFAULT 'pending',
        created_at                  TIMESTAMPTZ  NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_operator_digests_digest_date ON operator_digests (digest_date)",
    """
    CREATE TABLE IF NOT EXISTS notification_deliveries (
        id                          VARCHAR(36)  PRIMARY KEY,
        alert_id                    VARCHAR(36),
        digest_id                   VARCHAR(36),
        channel                     VARCHAR(32)  NOT NULL,
        recipient_ref               VARCHAR(256) NOT NULL,
        status                      VARCHAR(32)  NOT NULL DEFAULT 'pending',
        attempt_count               INTEGER      NOT NULL DEFAULT 0,
        next_attempt_at             TIMESTAMPTZ,
        sent_at                     TIMESTAMPTZ,
        idempotency_key             VARCHAR(256) NOT NULL,
        safe_error_code             VARCHAR(64),
        created_at                  TIMESTAMPTZ  NOT NULL,
        updated_at                  TIMESTAMPTZ  NOT NULL
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_notification_deliveries_idempotency ON notification_deliveries (idempotency_key)",
    "CREATE INDEX IF NOT EXISTS ix_notification_deliveries_status ON notification_deliveries (status, next_attempt_at)",
]


# Tenant branding/settings defaults provisioned at startup.
# Each entry: (tenant_id, settings_key, default_value_dict)
# Merged no-clobber: existing keys inside settings_key are never overwritten.
_TENANT_SETTING_DEFAULTS: list[tuple[str, str, dict]] = [
    (
        "T_ELITGRUPPEN",
        "branding",
        {
            "company_display_name":        "Elit Gruppen",
            "email_signature_name":        "Elit Gruppen",
            "internal_notification_email": "info@elitgruppen.se",
        },
    ),
]


def provision_tenant_defaults(engine: Engine) -> None:
    """Seed tenant-level settings defaults on startup (no-clobber — never overwrites existing values)."""
    try:
        with engine.begin() as conn:
            for tenant_id, settings_key, defaults in _TENANT_SETTING_DEFAULTS:
                row = conn.execute(
                    text("SELECT settings FROM tenant_configs WHERE tenant_id = :tid"),
                    {"tid": tenant_id},
                ).fetchone()
                if row is None:
                    log.debug("provision_tenant_defaults: tenant %s not in DB, skipping", tenant_id)
                    continue
                raw = row[0]
                if isinstance(raw, str):
                    current_settings: dict = json.loads(raw)
                elif isinstance(raw, dict):
                    current_settings = dict(raw)
                else:
                    current_settings = {}
                existing_section = current_settings.get(settings_key) or {}
                merged = {**defaults, **existing_section}
                if merged == existing_section:
                    log.debug(
                        "provision_tenant_defaults: %s.settings.%s already complete, no update",
                        tenant_id, settings_key,
                    )
                    continue
                current_settings[settings_key] = merged
                conn.execute(
                    text(
                        "UPDATE tenant_configs SET settings = :s WHERE tenant_id = :tid"
                    ),
                    {"s": json.dumps(current_settings), "tid": tenant_id},
                )
                log.info(
                    "provision_tenant_defaults: seeded %s.settings.%s with defaults",
                    tenant_id, settings_key,
                )
    except Exception as exc:
        log.warning("provision_tenant_defaults failed (non-fatal): %s", exc)


def ensure_runtime_schema(engine: Engine) -> None:
    """Add any columns/tables that exist in ORM models but may be missing from older DB instances."""
    try:
        with engine.begin() as conn:
            for table, column, col_type in _REQUIRED_COLUMNS:
                conn.execute(
                    text(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
                    )
                )
                log.debug("Schema check OK: %s.%s (%s)", table, column, col_type)

            for ddl in _REQUIRED_TABLES:
                conn.execute(text(ddl))
                log.debug("Table/index ensure OK")

            for ddl in _ONBOARDING_MIGRATION_STATEMENTS:
                conn.execute(text(ddl))
                log.debug("Onboarding migration OK")

            for ddl in _SLICE2B_MIGRATION_STATEMENTS:
                conn.execute(text(ddl))
                log.debug("Slice 2B migration OK")

            for ddl in _INTEGRATION_OAUTH_STATE_MIGRATION_STATEMENTS:
                conn.execute(text(ddl))
                log.debug("Integration OAuth state migration OK")

            for ddl in _OPERATOR_ALERTS_MIGRATION_STATEMENTS:
                conn.execute(text(ddl))
                log.debug("Operator alerts migration OK")

        log.info(
            "Runtime schema safeguard complete (%d column(s), %d table/index statement(s), %d onboarding statement(s), %d slice2b statement(s), %d operator alerts statement(s) checked)",
            len(_REQUIRED_COLUMNS),
            len(_REQUIRED_TABLES),
            len(_ONBOARDING_MIGRATION_STATEMENTS),
            len(_SLICE2B_MIGRATION_STATEMENTS),
            len(_OPERATOR_ALERTS_MIGRATION_STATEMENTS),
        )
    except Exception as exc:
        log.error(
            "Runtime schema migration failed — server cannot start safely: %s", exc,
            exc_info=True,
        )
        raise RuntimeError(
            f"Runtime schema migration failed: {exc}. "
            "Fix the database schema before restarting."
        ) from exc
