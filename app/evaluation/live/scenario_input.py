"""Locked scenario input loading for fixture_input live LLM eval."""

from __future__ import annotations

from pathlib import Path

from app.evaluation.dataset_manifest import (
    HASH_ALGORITHM,
    compute_scenario_content_hash,
    load_manifest,
    resolve_scenarios_root,
)
from app.evaluation.errors import ScenarioValidationError
from app.evaluation.live.constants import (
    ALLOWED_2F3_SCENARIOS,
    S01_LOCKED_SCENARIO_HASH,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.journal import append_transition
from app.evaluation.loader import load_scenario
from app.evaluation.schema.scenario import ScenarioContract

LLM_EVAL_RESOURCES_ROOT = (
    Path(__file__).resolve().parents[1] / "resources" / "llm-eval"
)
DEFAULT_MANIFEST_PATH = LLM_EVAL_RESOURCES_ROOT / "k2e-v1.yaml"
LOCKED_SCENARIO_HASHES: dict[str, str] = {
    "S01_lead_laddbox_quality": S01_LOCKED_SCENARIO_HASH,
}
EXPECTED_DATASET_VERSION = "k2e-v1"


class LiveEvalScenarioInputError(LiveEvalSafetyError):
    """Typed failure loading locked eval scenario input."""


def _manifest_path() -> Path:
    return DEFAULT_MANIFEST_PATH


def _resolve_scenario_path(scenario_id: str) -> Path:
    if scenario_id not in ALLOWED_2F3_SCENARIOS:
        raise LiveEvalScenarioInputError(
            f"scenario_id {scenario_id!r} is not allowlisted for 2F.3 fixture_input"
        )
    manifest_path = _manifest_path()
    if not manifest_path.exists():
        raise LiveEvalScenarioInputError(f"eval manifest missing: {manifest_path}")
    manifest = load_manifest(manifest_path)
    if manifest.dataset_version != EXPECTED_DATASET_VERSION:
        raise LiveEvalScenarioInputError(
            f"dataset_version mismatch: expected {EXPECTED_DATASET_VERSION!r}, "
            f"got {manifest.dataset_version!r}"
        )
    if scenario_id not in manifest.scenarios:
        raise LiveEvalScenarioInputError(
            f"scenario_id {scenario_id!r} not in eval manifest"
        )
    root = resolve_scenarios_root(manifest, manifest_path)
    scenario_path = root / f"{scenario_id}.yaml"
    if not scenario_path.exists():
        raise LiveEvalScenarioInputError(f"scenario resource missing: {scenario_path}")
    return scenario_path


def load_locked_scenario_input(
    scenario_id: str,
    *,
    evaluation_run_id: str | None = None,
) -> ScenarioContract:
    """Load allowlisted scenario from packaged resources with locked hash verification."""
    scenario_path = _resolve_scenario_path(scenario_id)
    try:
        scenario = load_scenario(scenario_path)
    except ScenarioValidationError as exc:
        raise LiveEvalScenarioInputError(str(exc)) from exc

    if scenario.scenario_id != scenario_id:
        raise LiveEvalScenarioInputError(
            f"scenario_id mismatch: {scenario.scenario_id!r} != {scenario_id!r}"
        )
    if scenario.scenario_version != 1:
        raise LiveEvalScenarioInputError(
            f"scenario_version must be 1, got {scenario.scenario_version!r}"
        )
    if scenario.dataset_version != EXPECTED_DATASET_VERSION:
        raise LiveEvalScenarioInputError(
            f"scenario dataset_version must be {EXPECTED_DATASET_VERSION!r}"
        )

    content_hash = compute_scenario_content_hash(scenario)
    expected_hash = LOCKED_SCENARIO_HASHES.get(scenario_id)
    if expected_hash is None:
        raise LiveEvalScenarioInputError(f"no locked hash for scenario {scenario_id!r}")
    if content_hash != expected_hash:
        raise LiveEvalScenarioInputError(
            f"scenario content hash mismatch for {scenario_id!r}"
        )

    if evaluation_run_id:
        append_transition(
            evaluation_run_id,
            {
                "state": "fixture_input_loaded",
                "scenario_id": scenario_id,
                "dataset_version": EXPECTED_DATASET_VERSION,
                "scenario_version": scenario.scenario_version,
                "hash_algorithm": HASH_ALGORITHM,
                "scenario_content_hash": content_hash,
            },
        )

    return scenario


def build_fixture_job_input_data(scenario: ScenarioContract) -> dict:
    """Build job input_data from locked scenario (no client-supplied text)."""
    sender = scenario.input.sender or {}
    return {
        "subject": scenario.input.subject,
        "message_text": scenario.input.message_text,
        "sender": {
            "name": (sender.get("name") or "").strip(),
            "email": (sender.get("email") or "").strip().lower(),
        },
        "source": {
            "system": "fixture_input",
            "scenario_id": scenario.scenario_id,
            "dataset_version": scenario.dataset_version,
        },
    }
