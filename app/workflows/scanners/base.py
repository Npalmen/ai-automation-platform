"""
Base contract for workflow scanner adapters.

Each adapter handles one external system (gmail, monday, microsoft_mail, etc.)
and returns a normalised ScanResult.  The engine calls adapters and persists
the results — adapters never touch the settings layer directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScanResult:
    """
    Normalised output from a scanner adapter.

    Fields
    ------
    system      : system key, e.g. "gmail", "monday"
    status      : "completed" | "failed"
    scanned_at  : ISO-8601 datetime string (UTC)
    data        : system-specific map written to system_map.<system>
    summary     : summary dict written to workflow_scan.summary.<system>
    error       : human-readable error string (set only when status="failed")
    """

    system: str
    status: str
    scanned_at: str
    data: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    error: str | None = None


class BaseWorkflowScannerAdapter:
    """
    Interface every scanner adapter must implement.

    Adapters receive a raw SQLAlchemy DB session so they can query stored data.
    They must NOT call external APIs — read only what the platform has already
    stored.  Adapters must NOT write to tenant_configs; that is the engine's job.
    """

    #: Override in subclasses — must match the system key used in system_map
    system_key: str = ""

    def run(self, db: Any, tenant_id: str) -> ScanResult:  # pragma: no cover
        raise NotImplementedError(f"{self.__class__.__name__}.run() not implemented")
