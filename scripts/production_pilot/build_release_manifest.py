#!/usr/bin/env python3
"""Build production pilot release manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.production_pilot.release_manifest import build_release_manifest, validate_release_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build production pilot release manifest")
    parser.add_argument("--activation-stage", default="P0")
    parser.add_argument("--backup-reference", default=None)
    parser.add_argument("--docker-image-digest", default=None)
    parser.add_argument("--operator-approval-id", default=None)
    parser.add_argument(
        "--output",
        default="storage/status/production-pilot/release-manifest.json",
    )
    args = parser.parse_args(argv)
    manifest = build_release_manifest(
        activation_stage=args.activation_stage,
        backup_reference=args.backup_reference,
        docker_image_digest=args.docker_image_digest,
        operator_approval_id=args.operator_approval_id,
    )
    failures = validate_release_manifest(manifest)
    if failures:
        print("FAIL", failures)
        return 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(manifest["release_version"], manifest["manifest_hash"][:16])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
