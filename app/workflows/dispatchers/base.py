"""
Generic controlled dispatch engine — base contract.

Each adapter handles one (system, job_type) pair.  The engine resolves the
correct adapter from the registry, validates the routing hint, optionally
runs dry_run, and returns a normalized DispatchResult.

No external writes happen in dry_run mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class DispatchResult:
    status:      str            # "success" | "failed" | "skipped" | "dry_run"
    system:      str
    job_type:    str
    target:      dict = field(default_factory=dict)
    external_id: str | None = None
    external_url: str | None = None
    message:     str = ""
    details:     dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "status":       self.status,
            "system":       self.system,
            "job_type":     self.job_type,
            "target":       self.target,
            "external_id":  self.external_id,
            "external_url": self.external_url,
            "message":      self.message,
            "details":      self.details,
        }


# ---------------------------------------------------------------------------
# Adapter contract
# ---------------------------------------------------------------------------

class BaseDispatchAdapter:
    """
    Override system_key and job_type_key to register the adapter.
    Implement dispatch() for live writes and describe() for dry-run output.
    """

    system_key:   str = ""
    job_type_key: str = ""

    def dispatch(
        self,
        job: Any,
        routing_hint: dict,
        settings: Any,
        dry_run: bool = False,
    ) -> DispatchResult:
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement dispatch()"
        )
