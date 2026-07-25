"""Batch evaluation runner for Kapitel 2G."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from app.evaluation.dataset_manifest import canonical_json_bytes
from app.evaluation.db_isolation import eval_db_session
from app.evaluation.errors import EXIT_PASS
from app.evaluation.generation.provenance import GeneratedScenarioRecord
from app.evaluation.reporting import ScenarioResult, new_run_id, normalize_metrics_for_baseline
from app.evaluation.runner import EvalHarnessRunner


@dataclass
class BatchScenarioOutcome:
    record: GeneratedScenarioRecord
    result: ScenarioResult
    replay_hash: str
    deterministic: bool = True


@dataclass
class BatchRunResult:
    run_id: str
    mode: str
    outcomes: list[BatchScenarioOutcome] = field(default_factory=list)
    no_network: bool = True
    openai_calls: int = 0
    gmail_calls: int = 0
    external_action_writes: int = 0

    @property
    def passed(self) -> bool:
        return all(outcome.result.status == "pass" for outcome in self.outcomes)


def _outcome_fingerprint(result: ScenarioResult) -> str:
    payload = {
        "status": result.status,
        "exit_code": result.exit_code,
        "normalized_metrics": result.normalized_metrics,
        "real_external_calls": result.runtime.real_external_calls,
    }
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def run_batch(
    records: list[GeneratedScenarioRecord],
    *,
    mode: str,
    run_id: str | None = None,
    verify_determinism: bool = True,
) -> BatchRunResult:
    effective_run_id = run_id or new_run_id()
    runner = EvalHarnessRunner(run_id=effective_run_id)
    outcomes: list[BatchScenarioOutcome] = []
    external_writes = 0

    for record in records:
        scenario = record.scenario
        with eval_db_session() as db:
            first = runner.run_scenario(db, scenario)
        replay_hash = _outcome_fingerprint(first)
        deterministic = True
        if verify_determinism:
            with eval_db_session() as db:
                second = runner.run_scenario(db, scenario)
            deterministic = replay_hash == _outcome_fingerprint(second)
            if not deterministic:
                first = second
        external_writes += int(first.runtime.real_external_calls or 0)
        outcomes.append(
            BatchScenarioOutcome(
                record=record,
                result=first,
                replay_hash=replay_hash,
                deterministic=deterministic,
            )
        )

    return BatchRunResult(
        run_id=effective_run_id,
        mode=mode,
        outcomes=outcomes,
        external_action_writes=external_writes,
    )
