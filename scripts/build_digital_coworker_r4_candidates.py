#!/usr/bin/env python3
"""Build write-free R4 candidate package (strict constrained live LLM; no Gmail writes)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.evaluation.profile_testbot.qualification.coworker_r4_candidates import (  # noqa: E402
    generate_r4_candidates,
    write_r4_candidate_package,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (  # noqa: E402
    R4_PROFILE_ID,
)
from app.workflows.reply_quality.llm_renderer import (  # noqa: E402
    MODEL_ID,
    PROMPT_VERSION,
)


def _git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build R4 write-free candidate package (requires live constrained LLM)"
    )
    parser.add_argument("--runtime-sha", default="")
    parser.add_argument("--profile-id", default=R4_PROFILE_ID)
    parser.add_argument("--status-dir", default=str(ROOT / "storage" / "status"))
    parser.add_argument(
        "--require-live-llm",
        action="store_true",
        help="Required for qualifying R4 generation (must be set explicitly)",
    )
    parser.add_argument("--expected-model", default=MODEL_ID)
    args = parser.parse_args()

    if not args.require_live_llm:
        print(
            "ERROR: --require-live-llm is mandatory for qualifying R4 candidate generation",
            file=sys.stderr,
        )
        return 1

    runtime_sha = args.runtime_sha.strip() or _git_sha()
    print("mode=write_free_candidate_generation")
    print("require_live_llm=true")
    print("gmail_writes=disabled")
    print(f"runtime_sha={runtime_sha}")
    print(f"expected_model={args.expected_model}")
    print(f"prompt_version={PROMPT_VERSION}")
    print("scenario_count=36")
    print("max_provider_calls=20")

    result = generate_r4_candidates(
        runtime_sha=runtime_sha,
        profile_id=args.profile_id,
        require_live_llm=True,
        expected_model=args.expected_model,
    )
    paths = write_r4_candidate_package(result, Path(args.status_dir))
    for path in paths.values():
        print(f"wrote {path}")
    print(f"overall_status={result.get('overall_status')}")
    print(f"constrained_llm_candidate_count={result.get('constrained_llm_candidate_count')}")
    print(f"provenance_audit_pass={result.get('provenance_audit_pass')}")
    print(f"candidate_package_semantic_hash={result.get('candidate_package_semantic_hash')}")

    if result.get("overall_status") != "PASS":
        print(result.get("blocking_failures"), file=sys.stderr)
        return 1
    if int(result.get("constrained_llm_candidate_count") or 0) != 20:
        print("ERROR: not all send candidates are constrained LLM", file=sys.stderr)
        return 1
    if int(result.get("deterministic_renderer_count") or 0) != 0:
        print("ERROR: deterministic renderer candidates present", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
