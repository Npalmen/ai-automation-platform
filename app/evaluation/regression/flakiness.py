"""Flakiness and quarantine policy for continuous regression."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.evaluation.regression.constants import SECURITY_CRITICAL_SUITE_TAGS


class FlakinessPolicyError(RuntimeError):
    pass


@dataclass
class FailureArtifact:
    suite_id: str
    exit_code: int
    output: str
    classification: str = "unknown"


@dataclass
class QuarantineEntry:
    test_id: str
    owner: str
    expires_on: date
    issue_ref: str
    suite_tags: list[str] = field(default_factory=list)


@dataclass
class FlakinessState:
    first_failure: FailureArtifact | None = None
    diagnostic_runs: int = 0
    quarantines: dict[str, QuarantineEntry] = field(default_factory=dict)

    def record_failure(self, artifact: FailureArtifact) -> None:
        if self.first_failure is None:
            self.first_failure = artifact

    def allow_diagnostic_reproduction(self) -> bool:
        return self.diagnostic_runs < 1

    def record_diagnostic_run(self) -> None:
        self.diagnostic_runs += 1

    def blind_rerun_forbidden(self) -> bool:
        return True

    def register_quarantine(self, entry: QuarantineEntry) -> None:
        blocked = set(entry.suite_tags) & SECURITY_CRITICAL_SUITE_TAGS
        if blocked:
            raise FlakinessPolicyError(
                f"Cannot quarantine security-critical tags: {sorted(blocked)}"
            )
        if not entry.owner or not entry.issue_ref:
            raise FlakinessPolicyError("Quarantine requires owner and issue reference")
        if entry.expires_on < date.today():
            raise FlakinessPolicyError("Quarantine expiry must be in the future")
        self.quarantines[entry.test_id] = entry

    def quarantine_status(self, test_id: str, *, today: date | None = None) -> str:
        entry = self.quarantines.get(test_id)
        if entry is None:
            return "active"
        current = today or date.today()
        if entry.expires_on < current:
            return "expired"
        return "quarantined"


def classify_failure(output: str) -> str:
    lowered = output.lower()
    if "assertionerror" in lowered or "failed" in lowered:
        return "deterministic_product_regression"
    if "connection refused" in lowered or "timeout" in lowered:
        return "infrastructure_failure"
    if "flaky" in lowered or "suspected flaky" in lowered:
        return "suspected_flaky"
    return "deterministic_test_regression"


def failure_report_payload(state: FlakinessState) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "blind_rerun_forbidden": state.blind_rerun_forbidden(),
        "diagnostic_runs": state.diagnostic_runs,
        "quarantined_tests": list(state.quarantines.keys()),
    }
    if state.first_failure is not None:
        payload["first_failure"] = {
            "suite_id": state.first_failure.suite_id,
            "exit_code": state.first_failure.exit_code,
            "classification": state.first_failure.classification,
        }
    return payload
