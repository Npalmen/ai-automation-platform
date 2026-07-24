"""Hermetic drift tests for packaged S01 scenario resource vs 2E canonical source."""

from __future__ import annotations

from pathlib import Path

from app.evaluation.dataset_manifest import (
    HASH_ALGORITHM,
    compute_scenario_content_hash,
    load_manifest,
)
from app.evaluation.live.constants import S01_LOCKED_SCENARIO_HASH
from app.evaluation.live.scenario_input import (
    DEFAULT_MANIFEST_PATH,
    LLM_EVAL_RESOURCES_ROOT,
    load_locked_scenario_input,
)
from app.evaluation.loader import load_scenario

CANONICAL_S01_PATH = (
    Path(__file__).resolve().parents[1] / "scenarios" / "S01_lead_laddbox_quality.yaml"
)
PACKAGED_S01_PATH = (
    LLM_EVAL_RESOURCES_ROOT / "scenarios" / "S01_lead_laddbox_quality.yaml"
)


def test_packaged_s01_matches_canonical_2e_source():
    canonical = load_scenario(CANONICAL_S01_PATH)
    packaged = load_scenario(PACKAGED_S01_PATH)

    canonical_hash = compute_scenario_content_hash(canonical)
    packaged_hash = compute_scenario_content_hash(packaged)

    assert canonical.scenario_id == packaged.scenario_id == "S01_lead_laddbox_quality"
    assert canonical.scenario_version == packaged.scenario_version == 1
    assert canonical.dataset_version == packaged.dataset_version == "k2e-v1"
    assert canonical_hash == packaged_hash
    assert canonical_hash == S01_LOCKED_SCENARIO_HASH
    assert HASH_ALGORITHM == "semantic-json-v2"


def test_packaged_manifest_matches_runtime_resource():
    manifest = load_manifest(DEFAULT_MANIFEST_PATH)
    assert manifest.dataset_version == "k2e-v1"
    assert "S01_lead_laddbox_quality" in manifest.scenarios

    runtime_scenario = load_locked_scenario_input("S01_lead_laddbox_quality")
    assert runtime_scenario.scenario_id == "S01_lead_laddbox_quality"
    assert runtime_scenario.scenario_version == 1
    assert runtime_scenario.dataset_version == "k2e-v1"
    assert compute_scenario_content_hash(runtime_scenario) == S01_LOCKED_SCENARIO_HASH
