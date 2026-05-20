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

        log.info(
            "Runtime schema safeguard complete (%d column(s), %d table/index statement(s) checked)",
            len(_REQUIRED_COLUMNS),
            len(_REQUIRED_TABLES),
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
