"""Canonical gold protection tests for 2G generation."""

from __future__ import annotations

from pathlib import Path

from app.evaluation.dataset_manifest import compute_manifest_hash
from app.evaluation.generation.generator import generate_batch


EXPECTED_MANIFEST_HASH = "502be4f1f4645ba48805b4696b69d9d32216ab86b63373ddfbc0d7a3e31af824"


def test_canonical_manifest_hash_unchanged():
    digest = compute_manifest_hash()
    assert digest["manifest_hash"] == EXPECTED_MANIFEST_HASH


def test_generation_does_not_modify_canonical_files(tmp_path: Path):
    digest_before = compute_manifest_hash()
    generate_batch(templates_per_parent=2, base_seed=0)
    digest_after = compute_manifest_hash()
    assert digest_before["manifest_hash"] == digest_after["manifest_hash"]
    assert digest_before["scenario_hashes"] == digest_after["scenario_hashes"]
