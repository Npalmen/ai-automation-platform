"""
Allowlisted local metadata readers for system status (Kapitel 8).

Never raises to callers. Never serializes internal paths or raw exceptions.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MAX_METADATA_BYTES = 64 * 1024
EXPECTED_SCHEMA_VERSION = 1

ALLOWLISTED_READ_ERROR_CODES = frozenset(
    {
        "invalid_json",
        "invalid_schema_version",
        "missing_required_field",
        "invalid_field_value",
    }
)


class MetadataReadOutcome(str, Enum):
    VALID = "valid"
    MISSING = "missing"
    INVALID = "invalid"
    OVERSIZED = "oversized"
    UNREADABLE = "unreadable"


@dataclass(frozen=True)
class MetadataReadResult:
    outcome: MetadataReadOutcome
    data: dict[str, Any] | None = None
    error_code: str | None = None


class DatabaseUnreachable(Exception):
    """Mandatory database check failed; endpoint should return 503."""


def _sanitize_error_code(code: str | None) -> str | None:
    if code is None:
        return None
    if code in ALLOWLISTED_READ_ERROR_CODES:
        return code
    return "invalid_field_value"


def read_json_metadata_file(path: str) -> MetadataReadResult:
    try:
        file_path = Path(path)
        if not file_path.exists():
            return MetadataReadResult(outcome=MetadataReadOutcome.MISSING)
        if not file_path.is_file():
            return MetadataReadResult(
                outcome=MetadataReadOutcome.UNREADABLE,
                error_code="invalid_field_value",
            )
        size = file_path.stat().st_size
        if size > MAX_METADATA_BYTES:
            return MetadataReadResult(
                outcome=MetadataReadOutcome.OVERSIZED,
                error_code="invalid_field_value",
            )
        raw = file_path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return MetadataReadResult(
                outcome=MetadataReadOutcome.INVALID,
                error_code="invalid_json",
            )
        if payload.get("schema_version") != EXPECTED_SCHEMA_VERSION:
            return MetadataReadResult(
                outcome=MetadataReadOutcome.INVALID,
                error_code="invalid_schema_version",
            )
        return MetadataReadResult(outcome=MetadataReadOutcome.VALID, data=payload)
    except json.JSONDecodeError:
        return MetadataReadResult(
            outcome=MetadataReadOutcome.INVALID,
            error_code="invalid_json",
        )
    except OSError:
        logger.warning("metadata_file_unreadable", exc_info=False)
        return MetadataReadResult(
            outcome=MetadataReadOutcome.UNREADABLE,
            error_code="invalid_field_value",
        )
    except Exception:
        logger.warning("metadata_file_read_failed", exc_info=False)
        return MetadataReadResult(
            outcome=MetadataReadOutcome.UNREADABLE,
            error_code="invalid_field_value",
        )


def read_backup_status(app_settings: Any) -> MetadataReadResult:
    path = getattr(app_settings, "BACKUP_STATUS_FILE", "")
    if not path:
        return MetadataReadResult(outcome=MetadataReadOutcome.MISSING)
    return read_json_metadata_file(path)


def read_restore_status(app_settings: Any) -> MetadataReadResult:
    path = getattr(app_settings, "RESTORE_STATUS_FILE", "")
    if not path:
        return MetadataReadResult(outcome=MetadataReadOutcome.MISSING)
    return read_json_metadata_file(path)


def read_build_metadata(app_settings: Any) -> MetadataReadResult:
    path = getattr(app_settings, "BUILD_METADATA_PATH", "")
    if not path:
        return MetadataReadResult(outcome=MetadataReadOutcome.MISSING)
    return read_json_metadata_file(path)


def check_database_reachable(db: Session) -> dict[str, Any]:
    """Controlled SELECT 1 with timing. Raises DatabaseUnreachable on failure."""
    started = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        dialect_name = db.bind.dialect.name if db.bind is not None else "unknown"
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "reachable": True,
            "response_time_ms": elapsed_ms,
            "dialect": dialect_name,
            "schema_ready": True,
        }
    except Exception as exc:
        logger.error(
            "system_status_database_check_failed",
            exc_info=False,
            extra={"error_type": type(exc).__name__},
        )
        raise DatabaseUnreachable from exc
