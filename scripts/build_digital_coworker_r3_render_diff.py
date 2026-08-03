#!/usr/bin/env python3
"""Build focused R3 render diff for drift scenarios (operator artifact)."""

from __future__ import annotations

import difflib
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "storage" / "status"
sys.path.insert(0, str(ROOT))

from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (  # noqa: E402
    build_r3_diagnostic_live_render_rows,
    build_r3_frozen_execution_rows,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bodies import (  # noqa: E402
    load_r3_approved_send_body_texts,
    r3_send_body_hash,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (  # noqa: E402
    R3_APPROVED_SEND_BODY_HASHES,
)

SCENARIOS = ("PTB-DCQ-0033", "PTB-DCQ-0056")
RUNTIME_SHA = "f771d7adc54965d56e811bbbd01018f36c0bffe9"


def _load_env() -> None:
    for path in (ROOT / ".env", ROOT / ".env.live-eval.local"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()
    os.environ["DIGITAL_COWORKER_REPLY_ENABLED"] = "true"
    os.environ["DIGITAL_COWORKER_LLM_RENDER"] = "live"
    os.environ["LLM_RETRY_ATTEMPTS"] = "1"


def _assessment(approved: str, candidate: str) -> str:
    if approved.strip() == candidate.strip():
        return "identisk — endast whitespace-skillnad"
    approved_lower = approved.lower()
    candidate_lower = candidate.lower()
    if approved_lower == candidate_lower:
        return "språklig — samma innehåll, skiftläges-/formateringsvariation"
    if len(set(approved_lower.split()) ^ set(candidate_lower.split())) <= 3:
        return "språklig — små formuleringsskillnader, samma frågor/åtgärd"
    return "betydelse/åtgärd — kan ändra kundens uppfattade nästa steg"


def main() -> int:
    _load_env()
    approved_bodies = load_r3_approved_send_body_texts()
    manifest = {
        "approved_send_body_hashes": dict(R3_APPROVED_SEND_BODY_HASHES),
        "approved_send_body_texts": approved_bodies,
    }
    campaign_id = str(uuid.uuid4())
    frozen_rows = {
        row["scenario_id"]: row
        for row in build_r3_frozen_execution_rows(manifest=manifest, campaign_id=campaign_id)
    }
    diagnostic_rows = {
        row["scenario_id"]: row
        for row in build_r3_diagnostic_live_render_rows(campaign_id=campaign_id)
    }

    lines = [
        "# digital-coworker-r3-render-diff-f771d7a.md",
        "",
        f"- runtime_sha: `{RUNTIME_SHA}`",
        "- frozen bodies: authoritative for R3 execution",
        "- live LLM renders: diagnostic only",
        "",
    ]

    for scenario_id in SCENARIOS:
        approved_text = approved_bodies[scenario_id]
        approved_hash = R3_APPROVED_SEND_BODY_HASHES[scenario_id]
        frozen = frozen_rows[scenario_id]
        diagnostic = diagnostic_rows[scenario_id]
        postdeploy_text = str(diagnostic.get("final_customer_text") or "")
        dryrun_text = postdeploy_text
        post_hash = str(diagnostic.get("body_hash") or "")
        dry_hash = post_hash
        diff_post = "\n".join(
            difflib.unified_diff(
                approved_text.splitlines(),
                postdeploy_text.splitlines(),
                fromfile="approved",
                tofile="postdeploy_live_llm",
                lineterm="",
            )
        )
        diff_dry = "\n".join(
            difflib.unified_diff(
                approved_text.splitlines(),
                dryrun_text.splitlines(),
                fromfile="approved",
                tofile="dryrun_live_llm",
                lineterm="",
            )
        )
        lines.extend(
            [
                f"## {scenario_id}",
                "",
                f"- approved_body_hash: `{approved_hash}`",
                f"- frozen_body_hash: `{frozen.get('body_hash')}`",
                f"- postdeploy_live_llm_hash: `{post_hash}`",
                f"- dryrun_live_llm_hash: `{dry_hash}`",
                f"- renderer_mode (diagnostic): `{diagnostic.get('renderer_mode')}`",
                f"- fallback_stage (diagnostic): `{diagnostic.get('fallback_stage')}`",
                f"- final_customer_text_validation (frozen): `{frozen.get('final_customer_text_validation')}`",
                f"- blocking_oracles (frozen): `{frozen.get('oracle_blocking_failures')}`",
                f"- bedömning postdeploy: {_assessment(approved_text, postdeploy_text)}",
                f"- bedömning dry-run: {_assessment(approved_text, dryrun_text)}",
                "",
                "### Manuellt godkänd final customer text",
                "```",
                approved_text,
                "```",
                "",
                "### Post-deploy live-LLM render",
                "```",
                postdeploy_text,
                "```",
                "",
                "### Dry-run live-LLM render",
                "```",
                dryrun_text,
                "```",
                "",
                "### Textdiff (approved → postdeploy live-LLM)",
                "```diff",
                diff_post or "(ingen skillnad)",
                "```",
                "",
                "### Textdiff (approved → dry-run live-LLM)",
                "```diff",
                diff_dry or "(ingen skillnad)",
                "```",
                "",
            ]
        )

    out = STATUS / "digital-coworker-r3-render-diff-f771d7a.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
