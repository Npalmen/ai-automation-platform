"""Explicit quality oracle status model (Todo I)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ORACLE_VERSION = "quality_oracle_v1"

ORACLE_STATUSES = frozenset(
    {
        "pass",
        "fail",
        "advisory",
        "not_applicable",
        "unresolved",
    }
)

ORACLE_CATEGORIES = frozenset(
    {
        "transport_safety",
        "decision_quality",
        "reply_quality",
        "thread_idempotency",
    }
)


@dataclass(frozen=True)
class QualityOracleResult:
    name: str
    status: str
    category: str
    detail: str
    blocker: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "category": self.category,
            "detail": self.detail,
            "blocker": self.blocker,
        }


@dataclass
class QualityOracleEvaluation:
    results: list[QualityOracleResult] = field(default_factory=list)

    @property
    def blockers(self) -> list[str]:
        return [
            r.name
            for r in self.results
            if r.blocker and r.status in {"fail", "unresolved"}
        ]

    @property
    def passed(self) -> bool:
        return not self.blockers

    def by_category(self, category: str) -> list[QualityOracleResult]:
        return [r for r in self.results if r.category == category]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "blockers": self.blockers,
            "results": [r.to_dict() for r in self.results],
        }


def _result(
    name: str,
    *,
    status: str,
    category: str,
    detail: str,
    blocker: bool = False,
) -> QualityOracleResult:
    if status not in ORACLE_STATUSES:
        status = "unresolved"
    return QualityOracleResult(
        name=name,
        status=status,
        category=category,
        detail=detail,
        blocker=blocker,
    )


def aggregate_quality_score(results: list[QualityOracleResult]) -> dict[str, Any]:
    """Deterministic aggregation — not_applicable excluded from pass/fail scoring."""
    scored = [r for r in results if r.status not in {"not_applicable"}]
    passes = sum(1 for r in scored if r.status == "pass")
    fails = sum(1 for r in scored if r.status == "fail" and r.blocker)
    advisories = sum(1 for r in scored if r.status == "advisory")
    unresolved = sum(1 for r in scored if r.status == "unresolved")
    applicable = len(scored)
    return {
        "applicable_count": applicable,
        "pass_count": passes,
        "fail_count": fails,
        "advisory_count": advisories,
        "unresolved_count": unresolved,
        "overall_pass": fails == 0 and unresolved == 0,
        "transport_pass": all(
            r.status in {"pass", "not_applicable"}
            for r in results
            if r.category == "transport_safety" and r.blocker
        ),
        "decision_pass": all(
            r.status in {"pass", "not_applicable"}
            for r in results
            if r.category == "decision_quality" and r.blocker
        ),
    }
