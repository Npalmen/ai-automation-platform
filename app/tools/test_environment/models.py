from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RowAction(str, Enum):
    DELETE = "DELETE"
    SKIP = "SKIP"
    UNLINK = "UNLINK"
    ORPHAN_INCIDENT_DELETE = "ORPHAN_INCIDENT_DELETE"


class StaleDataType(str, Enum):
    PENDING_APPROVALS = "pending_approvals"
    STUCK_JOBS = "stuck_jobs"
    DEMO_SEED_JOBS = "demo_seed_jobs"


@dataclass
class OperationLine:
    table: str
    tenant_id: str
    rows: int
    action: RowAction
    note: str = ""


@dataclass
class OperationReport:
    command: str
    dry_run: bool
    lines: list[OperationLine] = field(default_factory=list)

    @property
    def total_mutations(self) -> int:
        return sum(
            line.rows
            for line in self.lines
            if line.action
            in {RowAction.DELETE, RowAction.UNLINK, RowAction.ORPHAN_INCIDENT_DELETE}
        )
