"""Schema and CLI smoke tests for 2G generation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.evaluation.generation.manifest import MANIFEST_SCHEMA_VERSION, build_generation_manifest
from app.evaluation.generation.generator import generate_batch

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "2g"


def test_generation_manifest_schema():
    result = generate_batch(templates_per_parent=2, base_seed=0)
    manifest = build_generation_manifest(result, baseline_git_sha="abc123")
    assert manifest["manifest_schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["canonical_parent_count"] == 20
    assert manifest["generated_scenario_count"] == 40
    assert manifest["baseline_git_sha"] == "abc123"
    assert manifest["generation_payload_hash"]
    assert len(manifest["generation_payload_hash"]) == 64
    for entry in manifest["scenarios"]:
        assert entry["scenario_id"].startswith("2g_")
        assert entry["parent_scenario_id"]
        assert entry["template_id"]
        assert entry["seed"] is not None


def test_generation_manifest_matches_golden_fixture():
    expected = json.loads((FIXTURES_DIR / "expected_generation_manifest_v1.json").read_text(encoding="utf-8"))
    result = generate_batch(templates_per_parent=expected["templates_per_parent"], base_seed=expected["base_seed"])
    manifest = build_generation_manifest(result)
    assert manifest["generated_scenario_count"] == expected["generated_scenario_count"]
    assert manifest["generation_payload_hash"] == expected["generation_payload_hash"]


def test_cli_smoke_creates_expected_outputs(tmp_path: Path):
    import os

    output_dir = tmp_path / "generated"
    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/generate_2g_scenarios.py",
            "--output-dir",
            str(output_dir),
            "--baseline-git-sha",
            "deadbeef",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    manifest_path = output_dir / "2g_generation_manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["generated_scenario_count"] == 40
    scenario_files = list((output_dir / "scenarios").glob("*.yaml"))
    assert len(scenario_files) == 40
