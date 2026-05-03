"""Runtime schema safeguard for columns that create_all cannot add to existing tables."""
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
]


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
