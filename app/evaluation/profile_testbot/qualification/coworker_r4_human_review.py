"""R4 human-review package for send candidates (max 20)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

R4_REVIEW_DIMENSIONS: tuple[str, ...] = (
    "safety",
    "factual_fidelity",
    "service_specificity",
    "operational_usefulness",
    "question_relevance",
    "no_known_fact_reasking",
    "profile_fidelity",
    "thread_awareness",
    "naturalness",
    "concision",
    "next_step_clarity",
    "absence_of_unsupported_commitments",
)

R4_REVIEW_STATUSES = frozenset({"PASS", "PASS_WITH_NOTE", "FAIL", "PENDING"})


def build_r4_human_review_package(
    candidates: dict[str, Any],
    *,
    runtime_sha: str,
) -> dict[str, Any]:
    reviews: list[dict[str, Any]] = []
    for row in candidates.get("send_candidates") or []:
        reviews.append(
            {
                "scenario_id": row.get("scenario_id"),
                "family": row.get("family"),
                "body_hash": row.get("body_hash"),
                "plan_hash": row.get("plan_hash"),
                "rendered_body": row.get("rendered_body"),
                "selected_questions": row.get("selected_questions"),
                "known_facts": row.get("known_facts"),
                "next_step": row.get("next_step"),
                "playbook_id": row.get("playbook_id"),
                "renderer_provenance": {
                    "renderer_type": row.get("renderer_type"),
                    "model_id": row.get("model_id"),
                    "prompt_version": row.get("prompt_version"),
                    "fallback": row.get("fallback"),
                },
                "oracle_results": row.get("oracle_results"),
                "tags": row.get("tags"),
                "review_status": "PENDING",
                "dimension_scores": {dim: None for dim in R4_REVIEW_DIMENSIONS},
                "notes": [],
                "blocking_notes": [],
                "bound_body_hash": row.get("body_hash"),
            }
        )

    return {
        "package_type": "r4_human_review",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runtime_sha": runtime_sha,
        "manifest_semantic_hash": candidates.get("manifest_semantic_hash"),
        "review_dimensions": list(R4_REVIEW_DIMENSIONS),
        "allowed_statuses": sorted(R4_REVIEW_STATUSES),
        "send_review_count": len(reviews),
        "reviews": reviews,
        "human_review_complete": False,
        "human_review_failures": 0,
        "unresolved_blocking_notes": 0,
        "hard_safety_override_forbidden": True,
        "notes": (
            "All send candidates start as PENDING. Execution readiness requires "
            "explicit PASS/PASS_WITH_NOTE for every send candidate, FAIL=0, and "
            "body-hash bindings intact. Human review cannot override hard-safety "
            "or blocking oracle failures."
        ),
    }


def validate_r4_human_review_bindings(
    candidates: dict[str, Any],
    review_artifact: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    send_ids = [c.get("scenario_id") for c in candidates.get("send_candidates") or []]
    reviews = review_artifact.get("reviews") or []
    by_id = {r.get("scenario_id"): r for r in reviews}

    if len(reviews) != len(send_ids):
        blockers.append(
            f"review count {len(reviews)} != send candidate count {len(send_ids)}"
        )

    failures = 0
    pending = 0
    unresolved_notes = 0
    for sid in send_ids:
        review = by_id.get(sid)
        if review is None:
            blockers.append(f"missing_review:{sid}")
            continue
        cand = next(
            c for c in (candidates.get("send_candidates") or []) if c.get("scenario_id") == sid
        )
        if review.get("bound_body_hash") != cand.get("body_hash"):
            blockers.append(f"body_hash_binding_mismatch:{sid}")
        if review.get("body_hash") != cand.get("body_hash"):
            blockers.append(f"review_body_hash_mismatch:{sid}")
        status = review.get("review_status")
        if status not in R4_REVIEW_STATUSES:
            blockers.append(f"invalid_status:{sid}:{status}")
        if status == "PENDING":
            pending += 1
        if status == "FAIL":
            failures += 1
        unresolved_notes += len(review.get("blocking_notes") or [])

    if failures:
        blockers.append(f"human_review_failures={failures}")
    if pending:
        blockers.append(f"human_review_pending={pending}")
    if unresolved_notes:
        blockers.append(f"unresolved_blocking_notes={unresolved_notes}")

    complete = (
        not blockers
        and failures == 0
        and pending == 0
        and unresolved_notes == 0
        and len(reviews) == len(send_ids)
    )
    return {
        "human_review_complete": complete,
        "human_review_failures": failures,
        "unresolved_blocking_notes": unresolved_notes,
        "pending_reviews": pending,
        "blockers": blockers,
    }


def write_r4_human_review_package(package: dict[str, Any], status_dir: Path) -> dict[str, Path]:
    status_dir.mkdir(parents=True, exist_ok=True)
    sha = str(package.get("runtime_sha") or "unknown")[:7]
    json_path = status_dir / f"digital-coworker-r4-human-review-{sha}.json"
    md_path = status_dir / f"digital-coworker-r4-human-review-{sha}.md"
    json_path.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        f"# R4 human review package ({sha})",
        "",
        f"- send_review_count: **{package.get('send_review_count')}**",
        f"- human_review_complete: **{package.get('human_review_complete')}**",
        f"- manifest_semantic_hash: `{package.get('manifest_semantic_hash')}`",
        "",
        "## Candidates awaiting review",
        "",
    ]
    for row in package.get("reviews") or []:
        lines.append(
            f"### {row.get('scenario_id')}\n"
            f"- status: `{row.get('review_status')}`\n"
            f"- body_hash: `{(row.get('body_hash') or '')[:16]}…`\n"
            f"- family: `{row.get('family')}`\n"
        )
        body = (row.get("rendered_body") or "").strip()
        if body:
            lines.append("```")
            lines.append(body)
            lines.append("```")
            lines.append("")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "md": md_path}
