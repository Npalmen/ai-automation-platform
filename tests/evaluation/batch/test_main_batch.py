"""Main batch determinism tests."""

from __future__ import annotations

from app.evaluation.batch.sampler import build_main_batch_for_eval
from app.evaluation.mutations.batch import MAIN_BATCH_SIZE


def test_main_batch_size():
    records = build_main_batch_for_eval()
    assert len(records) == MAIN_BATCH_SIZE


def test_main_batch_deterministic():
    first = [r.provenance.scenario_hash for r in build_main_batch_for_eval()]
    second = [r.provenance.scenario_hash for r in build_main_batch_for_eval()]
    assert first == second
