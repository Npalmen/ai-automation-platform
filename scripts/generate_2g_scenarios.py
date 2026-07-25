#!/usr/bin/env python3
"""Hermetic CLI for deterministic 2G scenario generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from app.evaluation.errors import EXIT_FAIL_HARNESS, EXIT_PASS, HarnessError, ScenarioValidationError
from app.evaluation.generation.generator import generate_batch
from app.evaluation.generation.manifest import build_generation_manifest


def _write_scenario(output_dir: Path, record) -> Path:
    scenarios_dir = output_dir / "scenarios"
    scenarios_dir.mkdir(parents=True, exist_ok=True)
    path = scenarios_dir / f"{record.scenario.scenario_id}.yaml"
    payload = record.scenario.model_dump(mode="json", exclude_none=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate deterministic 2G scenarios")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-git-sha", default=None)
    parser.add_argument("--templates-per-parent", type=int, default=2)
    parser.add_argument("--base-seed", type=int, default=0)
    parser.add_argument("--manifest-only", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = generate_batch(
            templates_per_parent=args.templates_per_parent,
            base_seed=args.base_seed,
        )
        manifest = build_generation_manifest(result, baseline_git_sha=args.baseline_git_sha)
        args.output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = args.output_dir / "2g_generation_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if not args.manifest_only:
            for record in result.records:
                _write_scenario(args.output_dir, record)
        print(
            json.dumps(
                {
                    "generated_scenario_count": manifest["generated_scenario_count"],
                    "generation_payload_hash": manifest["generation_payload_hash"],
                    "output_dir": str(args.output_dir),
                }
            )
        )
        return EXIT_PASS
    except (ScenarioValidationError, HarnessError) as exc:
        print(f"generation failed: {exc}", file=sys.stderr)
        return EXIT_FAIL_HARNESS


if __name__ == "__main__":
    raise SystemExit(main())
