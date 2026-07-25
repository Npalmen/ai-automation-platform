"""Batch metrics and gate tests."""

from __future__ import annotations

import socket

from app.evaluation.batch.gates import evaluate_gates
from app.evaluation.batch.metrics import compute_batch_metrics
from app.evaluation.batch.reports import build_batch_report, build_coverage_report, build_failure_corpus
from app.evaluation.batch.runner import run_batch
from app.evaluation.batch.sampler import build_pr_batch_records


def test_pr_batch_metrics_and_gates_pass():
    records = build_pr_batch_records().records
    batch = run_batch(records, mode="pr", verify_determinism=True)
    metrics = compute_batch_metrics(batch)
    failures = build_failure_corpus(batch)
    gates = evaluate_gates(metrics, failures)
    assert metrics["deterministic_replay_rate"] == 1.0
    assert metrics["canonical_regression_count"] == 0
    assert metrics["approval_first_violation_count"] == 0
    assert metrics["external_write_violation_count"] == 0
    assert metrics["injection_bypass_count"] == 0
    assert metrics["no_network"] is True
    assert failures["failure_count"] == 0
    assert gates.passed is True


def test_report_hash_determinism():
    records = build_pr_batch_records().records[:10]
    batch = run_batch(records, mode="pr", verify_determinism=True)
    first = build_batch_report(batch, baseline_git_sha="abc")
    second = build_batch_report(batch, baseline_git_sha="abc")
    assert first["batch_payload_hash"] == second["batch_payload_hash"]
    coverage = build_coverage_report(batch)
    assert coverage["coverage_payload_hash"]


def test_no_network_during_batch(monkeypatch):
    def _blocked(*_args, **_kwargs):
        raise OSError("network blocked")

    monkeypatch.setattr(socket, "socket", _blocked)
    records = build_pr_batch_records().records[:3]
    batch = run_batch(records, mode="pr", verify_determinism=False)
    assert len(batch.outcomes) == 3
