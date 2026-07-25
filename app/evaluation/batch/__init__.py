"""Batch evaluation for Kapitel 2G."""

from app.evaluation.batch.gates import evaluate_gates
from app.evaluation.batch.reports import build_batch_report, build_coverage_report, build_failure_corpus
from app.evaluation.batch.runner import run_batch
from app.evaluation.batch.sampler import build_main_batch_for_eval, build_pr_batch_records

__all__ = [
    "build_batch_report",
    "build_coverage_report",
    "build_failure_corpus",
    "build_main_batch_for_eval",
    "build_pr_batch_records",
    "evaluate_gates",
    "run_batch",
]
