"""PR batch sampling determinism tests."""

from __future__ import annotations

from app.evaluation.batch.sampler import PR_BATCH_SIZE, build_pr_batch_records


def test_pr_batch_size():
    result = build_pr_batch_records()
    assert len(result.records) == PR_BATCH_SIZE


def test_pr_batch_deterministic():
    first = build_pr_batch_records()
    second = build_pr_batch_records()
    assert [r.provenance.scenario_hash for r in first.records] == [
        r.provenance.scenario_hash for r in second.records
    ]


def test_pr_batch_composition():
    result = build_pr_batch_records()
    canonical = [r for r in result.records if r.scenario.category == "canonical"]
    security = [r for r in result.records if r.scenario.category in {"adversarial", "injection_attempt"}]
    assert len(canonical) == 20
    assert len(security) == 20
