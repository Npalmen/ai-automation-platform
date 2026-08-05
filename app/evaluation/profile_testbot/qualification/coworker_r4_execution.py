"""R4 live campaign runner — dry-run default; execute fail-closed until manual gate."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.evaluation.profile_testbot.qualification.coworker_r4_candidates import (
    generate_r4_candidates,
    write_r4_candidate_package,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_human_review import (
    build_r4_human_review_package,
    write_r4_human_review_package,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_manifest import (
    build_r4_campaign_manifest,
    validate_r4_manifest,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_readiness import (
    evaluate_coworker_r4_readiness,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import R4_PROFILE_ID

Mode = Literal["dry_run", "execute"]


def run_r4_live_campaign(
    *,
    mode: Mode,
    expected_runtime_sha: str,
    profile_id: str = R4_PROFILE_ID,
    seed: int = 42,
    status_dir: Path | None = None,
    approval_path: Path | None = None,
    human_review_path: Path | None = None,
    candidates_path: Path | None = None,
) -> dict[str, Any]:
    status_dir = status_dir or Path("storage/status")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    manifest = build_r4_campaign_manifest(
        runtime_sha=expected_runtime_sha, profile_id=profile_id, seed=seed
    )
    if candidates_path is not None and Path(candidates_path).is_file():
        # Post-review path: reuse locked write-free candidates; never regenerate bodies.
        candidates = json.loads(Path(candidates_path).read_text(encoding="utf-8"))
    else:
        candidates = generate_r4_candidates(
            runtime_sha=expected_runtime_sha, profile_id=profile_id, seed=seed
        )
    human_review = None
    if human_review_path and human_review_path.is_file():
        human_review = json.loads(human_review_path.read_text(encoding="utf-8"))
    else:
        human_review = build_r4_human_review_package(
            candidates, runtime_sha=expected_runtime_sha
        )

    readiness = evaluate_coworker_r4_readiness(
        runtime_sha=expected_runtime_sha,
        manifest=manifest,
        candidates=candidates,
        human_review=human_review,
        skip_live_probes=True,
    )

    result: dict[str, Any] = {
        "mode": mode,
        "generated_at": generated_at,
        "runtime_sha": expected_runtime_sha,
        "manifest_semantic_hash": manifest.get("manifest_semantic_hash"),
        "candidate_package_semantic_hash": candidates.get("candidate_package_semantic_hash"),
        "manifest_blockers": validate_r4_manifest(manifest),
        "candidates_overall_status": candidates.get("overall_status"),
        "candidates_source": str(candidates_path) if candidates_path else "generated",
        "human_review_source": str(human_review_path) if human_review_path else "built",
        "readiness": readiness,
        "gmail_sends": 0,
        "gmail_drafts": 0,
        "external_writes": 0,
        "new_trigger_emails": 0,
        "automatic_gmail": False,
        "production_activation": False,
        "r3_hold_override_generalized": False,
    }

    review_complete = bool(readiness.get("human_review_complete"))
    if mode == "dry_run":
        if (
            readiness.get("r4_campaign_ready_for_dry_run")
            and candidates.get("overall_status") == "PASS"
        ):
            result["overall_status"] = "PASS"
            result["stop_reason"] = None
            if review_complete:
                result["manual_execution_confirmation"] = (
                    "MANUAL EXECUTION CONFIRMATION REQUIRED — R4 human review PASS med "
                    "20/20 hashbundna kandidater, 0 FAIL och 0 blocking notes; "
                    "post-review preflight och dry-run PASS utan Gmail-writes"
                )
            else:
                result["manual_execution_confirmation"] = (
                    "MANUAL EXECUTION CONFIRMATION REQUIRED — R3 PASS formaliserad; "
                    "R4 campaign med 36 scenarier, minst 15 familjer, högst 20 granskade "
                    "send-kandidater och minst 16 no-send är SHA-, manifest-, profile-, "
                    "renderer-, validator- och body-hash-bunden; postdeploy preflight och "
                    "dry-run PASS utan Gmail-writes"
                )
        else:
            result["overall_status"] = "BLOCKED"
            result["stop_reason"] = {
                "readiness_blockers": readiness.get("blockers"),
                "candidate_failures": candidates.get("blocking_failures"),
                "execute_blockers": readiness.get("execute_blockers"),
            }
    else:
        # Fail-closed: this PR slice never performs live Gmail execute.
        result["overall_status"] = "STOPPED"
        result["stop_reason"] = (
            "R4 --execute is blocked until separate manual confirmation after "
            "deployed merge SHA, human-reviewed body-hash bindings, preflight PASS, "
            "and dry-run PASS. No Gmail triggers/drafts/replies were created."
        )
        if approval_path is None or not Path(approval_path).is_file():
            result["stop_reason"] = (
                "missing_manual_execution_approval_artifact; " + str(result["stop_reason"])
            )
        if not readiness.get("r4_campaign_ready_for_manual_execution"):
            result["execute_blockers"] = readiness.get("execute_blockers")

    paths = write_r4_execution_reports(
        result=result,
        manifest=manifest,
        candidates=candidates,
        human_review=human_review,
        status_dir=status_dir,
        rewrite_locked_packages=candidates_path is None,
    )
    result["report_paths"] = {k: str(v) for k, v in paths.items()}
    return result


def write_r4_execution_reports(
    *,
    result: dict[str, Any],
    manifest: dict[str, Any],
    candidates: dict[str, Any],
    human_review: dict[str, Any],
    status_dir: Path,
    rewrite_locked_packages: bool = True,
) -> dict[str, Path]:
    status_dir.mkdir(parents=True, exist_ok=True)
    sha = str(result.get("runtime_sha") or "unknown")[:7]
    paths: dict[str, Path] = {}

    manifest_path = status_dir / f"digital-coworker-r4-manifest-{sha}.json"
    safe_manifest = {k: v for k, v in manifest.items() if k != "semantic_payload"}
    manifest_path.write_text(
        json.dumps(safe_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    paths["manifest"] = manifest_path

    if rewrite_locked_packages:
        cand_paths = write_r4_candidate_package(candidates, status_dir)
        paths.update({f"candidates_{k}": v for k, v in cand_paths.items()})
        review_paths = write_r4_human_review_package(human_review, status_dir)
        paths.update({f"human_review_{k}": v for k, v in review_paths.items()})
    else:
        # Preserve locked candidate/review body hashes; only emit dry-run reports.
        paths["candidates_json"] = status_dir / f"digital-coworker-r4-candidates-{sha}.json"
        paths["human_review_json"] = Path(
            str(result.get("human_review_source") or "")
        )

    report_json = status_dir / f"digital-coworker-r4-dry-run-{sha}.json"
    report_md = status_dir / f"digital-coworker-r4-dry-run-{sha}.md"
    report_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        f"# R4 dry-run / execution report ({sha})",
        "",
        f"- mode: `{result.get('mode')}`",
        f"- overall_status: **{result.get('overall_status')}**",
        f"- runtime_sha: `{result.get('runtime_sha')}`",
        f"- manifest_semantic_hash: `{result.get('manifest_semantic_hash')}`",
        f"- candidate_package_semantic_hash: `{result.get('candidate_package_semantic_hash')}`",
        f"- gmail_sends: **{result.get('gmail_sends')}**",
        f"- gmail_drafts: **{result.get('gmail_drafts')}**",
        f"- external_writes: **{result.get('external_writes')}**",
        f"- new_trigger_emails: **{result.get('new_trigger_emails')}**",
        "",
        f"stop_reason: `{result.get('stop_reason')}`",
        "",
    ]
    if result.get("manual_execution_confirmation"):
        lines.append(result["manual_execution_confirmation"])
        lines.append("")
    report_md.write_text("\n".join(lines), encoding="utf-8")
    paths["report_json"] = report_json
    paths["report_md"] = report_md
    return paths
