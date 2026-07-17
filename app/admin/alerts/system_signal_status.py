"""System signal status normalization (Kapitel 10 Slice 2)."""

from __future__ import annotations

from typing import Literal

SystemSignalStatus = Literal[
    "healthy",
    "warning",
    "failed",
    "stale",
    "missing_expected",
    "not_configured",
    "unknown",
    "source_unavailable",
]

_NO_AUTO_ALERT = frozenset(
    {"healthy", "missing_expected", "not_configured", "unknown", "source_unavailable"}
)


def allows_auto_alert(status: SystemSignalStatus) -> bool:
    return status not in _NO_AUTO_ALERT


def normalize_backup_status(
    *,
    operation_status: str | None,
    age_hours: float | None,
    max_age_hours: float,
    source_available: bool,
) -> SystemSignalStatus:
    if not source_available:
        return "source_unavailable"
    if operation_status is None:
        return "not_configured"
    op = operation_status.lower()
    if op == "failed":
        return "failed"
    if op in ("success", "ok", "healthy"):
        if age_hours is not None and age_hours > max_age_hours:
            return "stale"
        return "healthy"
    if age_hours is not None and age_hours > max_age_hours:
        return "stale"
    return "unknown"


def severity_for_system_status(status: SystemSignalStatus, *, failed_severity: str = "critical") -> str | None:
    if not allows_auto_alert(status):
        return None
    if status == "failed":
        return failed_severity
    if status == "stale":
        return "high"
    if status == "warning":
        return "warning"
    return None
