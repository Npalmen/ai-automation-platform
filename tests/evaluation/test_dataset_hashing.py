"""Semantic dataset hashing tests for Kapitel 2E.1."""

from __future__ import annotations

from pathlib import Path
import yaml

from app.evaluation.dataset_manifest import (
    HASH_ALGORITHM,
    compute_manifest_hash,
    compute_scenario_content_hash,
    compute_scenario_file_hash,
)
from app.evaluation.schema.scenario import ScenarioContract


def _minimal_scenario(**overrides) -> ScenarioContract:
    payload = {
        "schema_version": "2e.1",
        "scenario_id": "S99_hash_probe",
        "category": "probe",
        "input": {"subject": "Probe", "message_text": "Probe body"},
    }
    payload.update(overrides)
    return ScenarioContract.model_validate(payload)


def test_hash_algorithm_constant():
    assert HASH_ALGORITHM == "semantic-json-v1"


def test_crlf_and_lf_yaml_produce_same_scenario_hash(tmp_path: Path):
    semantic = {
        "schema_version": "2e.1",
        "scenario_id": "S99_hash_probe",
        "category": "probe",
        "input": {"subject": "Probe", "message_text": "Probe body"},
    }
    lf_path = tmp_path / "lf.yaml"
    crlf_path = tmp_path / "crlf.yaml"
    lf_path.write_text(yaml.safe_dump(semantic, sort_keys=False), encoding="utf-8", newline="\n")
    crlf_path.write_text(
        yaml.safe_dump(semantic, sort_keys=False).replace("\n", "\r\n"),
        encoding="utf-8",
        newline="\n",
    )
    assert compute_scenario_file_hash(lf_path) == compute_scenario_file_hash(crlf_path)


def test_equivalent_yaml_indentation_produces_same_hash(tmp_path: Path):
    semantic = {
        "schema_version": "2e.1",
        "scenario_id": "S99_hash_probe",
        "category": "probe",
        "input": {"subject": "Probe", "message_text": "Probe body"},
        "tenant": {"auto_actions": {}, "followups_enabled": True},
    }
    compact = tmp_path / "compact.yaml"
    expanded = tmp_path / "expanded.yaml"
    compact.write_text(yaml.safe_dump(semantic, default_flow_style=True), encoding="utf-8")
    expanded.write_text(yaml.safe_dump(semantic, default_flow_style=False, sort_keys=False), encoding="utf-8")
    assert compute_scenario_file_hash(compact) == compute_scenario_file_hash(expanded)


def test_semantic_change_produces_different_hash():
    base = _minimal_scenario()
    changed = _minimal_scenario(input={"subject": "Changed", "message_text": "Probe body"})
    assert compute_scenario_content_hash(base) != compute_scenario_content_hash(changed)


def test_runtime_generation_provenance_excluded_from_hash():
    base = _minimal_scenario()
    with_generation = _minimal_scenario(
        generation={
            "template_id": "tpl-1",
            "seed": 42,
            "variation_id": "v1",
            "generator_model": "gpt-test",
            "generator_prompt_version": "p1",
            "parent_scenario_id": "S01_lead_laddbox_quality",
            "mutation_types": ["paraphrase"],
        }
    )
    assert compute_scenario_content_hash(base) == compute_scenario_content_hash(with_generation)


def test_manifest_hash_includes_algorithm_and_ordered_lists():
    info = compute_manifest_hash()
    canonical = info["canonical"]
    assert canonical["hash_algorithm"] == HASH_ALGORITHM
    assert canonical["scenarios"]
    assert canonical["smoke"]
    assert info["hash_algorithm"] == HASH_ALGORITHM
    assert len(info["manifest_hash"]) == 64


def test_manifest_hash_stable_across_line_endings(tmp_path: Path, monkeypatch):
    manifest_src = Path("tests/evaluation/datasets/k2e-v1.yaml").read_text(encoding="utf-8")
    manifest_lf = tmp_path / "manifest-lf.yaml"
    manifest_crlf = tmp_path / "manifest-crlf.yaml"
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    manifest_lf.write_text(manifest_src, encoding="utf-8", newline="\n")
    manifest_crlf.write_text(manifest_src.replace("\n", "\r\n"), encoding="utf-8", newline="\n")

    src_root = Path("tests/evaluation/scenarios")
    for name in src_root.glob("S*.yaml"):
        text = name.read_text(encoding="utf-8")
        (scenarios_dir / name.name).write_text(text, encoding="utf-8", newline="\n")
        (scenarios_dir / f"crlf_{name.name}").write_text(text.replace("\n", "\r\n"), encoding="utf-8", newline="\n")

    # Point manifest scenarios_dir at copied LF scenarios only.
    raw = yaml.safe_load(manifest_lf.read_text(encoding="utf-8"))
    raw["scenarios_dir"] = "scenarios"
    manifest_lf.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    manifest_crlf.write_text(yaml.safe_dump(raw, sort_keys=False).replace("\n", "\r\n"), encoding="utf-8")

    lf_hash = compute_manifest_hash(manifest_lf)["manifest_hash"]
    crlf_hash = compute_manifest_hash(manifest_crlf)["manifest_hash"]
    assert lf_hash == crlf_hash
