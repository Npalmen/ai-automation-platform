"""Failure fingerprint tests."""

from __future__ import annotations

from app.evaluation.batch.failures import build_failure_corpus
from app.evaluation.batch.runner import BatchRunResult


def test_failure_corpus_empty_when_all_pass():
    batch = BatchRunResult(run_id="test", mode="pr", outcomes=[])
    corpus = build_failure_corpus(batch)
    assert corpus["failure_count"] == 0
    assert corpus["failures_payload_hash"]
