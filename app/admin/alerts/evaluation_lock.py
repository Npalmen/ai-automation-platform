"""Pool-safe advisory lock for alert evaluation runs."""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

_LOCK_KEY = 0x4B314030  # "K10"-ish
_sqlite_lock = threading.Lock()


@contextmanager
def alert_evaluation_lock(engine: Engine) -> Iterator[bool]:
    """Yield True if lock acquired, False if another run is active."""
    dialect = engine.dialect.name
    if dialect == "sqlite":
        acquired = _sqlite_lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                _sqlite_lock.release()
        return

    conn = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    acquired = False
    try:
        acquired = bool(
            conn.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": _LOCK_KEY},
            ).scalar()
        )
        yield acquired
    finally:
        if acquired:
            try:
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _LOCK_KEY})
            except Exception:
                logger.exception("Failed to release alert evaluation advisory lock")
        conn.close()
