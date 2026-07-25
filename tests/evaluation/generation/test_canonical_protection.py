"""Canonical gold protection tests for 2G generation."""

from __future__ import annotations

from pathlib import Path

from app.evaluation.dataset_manifest import compute_manifest_hash
from app.evaluation.generation.generator import generate_batch


EXPECTED_MANIFEST_HASH = "600e7fd601227d0e327951df8f2a91f48eb6af713410f2a76f819d4db5a793d8"


def test_canonical_manifest_hash_unchanged():
    digest = compute_manifest_hash()
    assert digest["manifest_hash"] == EXPECTED_MANIFEST_HASH


def test_generation_does_not_modify_canonical_files(tmp_path: Path):
    digest_before = compute_manifest_hash()
    generate_batch(templates_per_parent=2, base_seed=0)
    digest_after = compute_manifest_hash()
    assert digest_before["manifest_hash"] == digest_after["manifest_hash"]
    assert digest_before["scenario_hashes"] == digest_after["scenario_hashes"]
