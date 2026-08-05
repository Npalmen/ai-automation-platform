"""R4 human-review package for send candidates (max 20)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.workflows.reply_quality.provenance import LLM_RENDERER

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


def evaluate_r4_human_review_authorization(candidates: dict[str, Any]) -> dict[str, Any]:
    """Authorize PENDING human-review slots only for qualifying constrained-LLM packages."""
    blockers: list[str] = []
    if candidates.get("overall_status") != "PASS":
        blockers.append("overall_status_not_pass")
    if not candidates.get("provenance_audit_pass"):
        blockers.append("provenance_audit_pass_false")
    if int(candidates.get("constrained_llm_candidate_count") or 0) != 20:
        blockers.append(
            f"constrained_llm_candidate_count={candidates.get('constrained_llm_candidate_count')}"
        )
    if int(candidates.get("deterministic_renderer_count") or 0) != 0:
        blockers.append(
            f"deterministic_renderer_count={candidates.get('deterministic_renderer_count')}"
        )
    if int(candidates.get("fallback_count") or 0) != 0:
        blockers.append(f"fallback_count={candidates.get('fallback_count')}")
    if int(candidates.get("missing_model_id_count") or 0) != 0:
        blockers.append(
            f"missing_model_id_count={candidates.get('missing_model_id_count')}"
        )
    if int(candidates.get("missing_prompt_version_count") or 0) != 0:
        blockers.append(
            f"missing_prompt_version_count={candidates.get('missing_prompt_version_count')}"
        )
    if not candidates.get("candidate_package_semantic_hash"):
        blockers.append("missing_candidate_package_semantic_hash")
    return {
        "human_review_authorized": not blockers,
        "blockers": blockers,
    }


def build_r4_human_review_package(
    candidates: dict[str, Any],
    *,
    runtime_sha: str,
) -> dict[str, Any]:
    auth = evaluate_r4_human_review_authorization(candidates)
    authorized = bool(auth.get("human_review_authorized"))

    if not authorized:
        return {
            "package_type": "r4_human_review_diagnostic",
            "qualification_status": "NON_QUALIFYING",
            "human_review_authorized": False,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "runtime_sha": runtime_sha,
            "manifest_semantic_hash": candidates.get("manifest_semantic_hash"),
            "candidate_package_semantic_hash": candidates.get(
                "candidate_package_semantic_hash"
            ),
            "authorization_blockers": auth.get("blockers") or [],
            "review_dimensions": list(R4_REVIEW_DIMENSIONS),
            "allowed_statuses": sorted(R4_REVIEW_STATUSES),
            "send_review_count": 0,
            "reviews": [],
            "human_review_complete": False,
            "human_review_failures": 0,
            "unresolved_blocking_notes": 0,
            "hard_safety_override_forbidden": True,
            "notes": (
                "Diagnostic-only package. Candidate package is not authorized for "
                "human review (missing constrained-LLM provenance or package PASS). "
                "No PENDING review slots were created."
            ),
        }

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
                    "renderer_requirement": row.get("renderer_requirement"),
                    "renderer_type": row.get("renderer_type"),
                    "llm_used": row.get("llm_used"),
                    "invocation_attempted": row.get("invocation_attempted"),
                    "live_call": row.get("live_call"),
                    "provider_outcome": row.get("provider_outcome"),
                    "requested_model_id": row.get("requested_model_id"),
                    "returned_model_id": row.get("returned_model_id"),
                    "model_id": row.get("model_id") or row.get("returned_model_id"),
                    "prompt_version": row.get("prompt_version"),
                    "template_version": row.get("template_version"),
                    "renderer_policy_version": row.get("renderer_policy_version"),
                    "finish_reason": row.get("finish_reason"),
                    "prompt_tokens": row.get("prompt_tokens"),
                    "completion_tokens": row.get("completion_tokens"),
                    "total_tokens": row.get("total_tokens"),
                    "provider_attempt_count": row.get("provider_attempt_count"),
                    "post_render_validation_passed": row.get(
                        "post_render_validation_passed"
                    ),
                    "final_text_validation_passed": row.get(
                        "final_text_validation_passed"
                    ),
                    "prompt_payload_hash": row.get("prompt_payload_hash"),
                    "fallback": row.get("fallback"),
                },
                "oracle_results": row.get("oracle_results"),
                "tags": row.get("tags"),
                "review_status": "PENDING",
                "dimension_scores": {dim: None for dim in R4_REVIEW_DIMENSIONS},
                "notes": [],
                "blocking_notes": [],
                "bound_body_hash": row.get("body_hash"),
                "bound_candidate_package_semantic_hash": candidates.get(
                    "candidate_package_semantic_hash"
                ),
                "bound_manifest_semantic_hash": candidates.get("manifest_semantic_hash"),
            }
        )

    # Defense in depth: refuse PENDING slots if any row is not constrained LLM.
    if any(
        (r.get("renderer_provenance") or {}).get("renderer_type") != LLM_RENDERER
        for r in reviews
    ):
        return {
            "package_type": "r4_human_review_diagnostic",
            "qualification_status": "NON_QUALIFYING",
            "human_review_authorized": False,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "runtime_sha": runtime_sha,
            "manifest_semantic_hash": candidates.get("manifest_semantic_hash"),
            "candidate_package_semantic_hash": candidates.get(
                "candidate_package_semantic_hash"
            ),
            "authorization_blockers": ["send_candidate_renderer_not_constrained_llm"],
            "send_review_count": 0,
            "reviews": [],
            "human_review_complete": False,
            "notes": "Diagnostic-only: one or more send candidates lack constrained_llm_v1.",
        }

    return {
        "package_type": "r4_human_review",
        "qualification_status": "QUALIFYING_PENDING_REVIEW",
        "human_review_authorized": True,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runtime_sha": runtime_sha,
        "manifest_semantic_hash": candidates.get("manifest_semantic_hash"),
        "candidate_package_semantic_hash": candidates.get(
            "candidate_package_semantic_hash"
        ),
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
    if not review_artifact.get("human_review_authorized"):
        return {
            "human_review_complete": False,
            "human_review_failures": 0,
            "unresolved_blocking_notes": 0,
            "pending_reviews": 0,
            "blockers": ["human_review_not_authorized"],
        }

    send_ids = [c.get("scenario_id") for c in candidates.get("send_candidates") or []]
    reviews = review_artifact.get("reviews") or []
    by_id = {r.get("scenario_id"): r for r in reviews}

    if len(reviews) != len(send_ids):
        blockers.append(
            f"review count {len(reviews)} != send candidate count {len(send_ids)}"
        )

    if review_artifact.get("candidate_package_semantic_hash") != candidates.get(
        "candidate_package_semantic_hash"
    ):
        blockers.append("candidate_package_semantic_hash_mismatch")
    if review_artifact.get("manifest_semantic_hash") != candidates.get(
        "manifest_semantic_hash"
    ):
        blockers.append("manifest_semantic_hash_mismatch")

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
    suffix = "" if package.get("human_review_authorized") else "-NON_QUALIFYING"
    json_path = status_dir / f"digital-coworker-r4-human-review-{sha}{suffix}.json"
    md_path = status_dir / f"digital-coworker-r4-human-review-{sha}{suffix}.md"
    json_path.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        f"# R4 human review package ({sha})",
        "",
        f"- human_review_authorized: **{package.get('human_review_authorized')}**",
        f"- qualification_status: **{package.get('qualification_status')}**",
        f"- send_review_count: **{package.get('send_review_count')}**",
        f"- human_review_complete: **{package.get('human_review_complete')}**",
        f"- manifest_semantic_hash: `{package.get('manifest_semantic_hash')}`",
        f"- candidate_package_semantic_hash: `{package.get('candidate_package_semantic_hash')}`",
        "",
    ]
    if not package.get("human_review_authorized"):
        lines.extend(
            [
                "## Authorization blockers",
                "",
                f"`{package.get('authorization_blockers')}`",
                "",
                "No PENDING review slots were created.",
                "",
            ]
        )
    else:
        lines.extend(["## Candidates awaiting review", ""])
        for row in package.get("reviews") or []:
            prov = row.get("renderer_provenance") or {}
            lines.append(
                f"### {row.get('scenario_id')}\n"
                f"- status: `{row.get('review_status')}`\n"
                f"- body_hash: `{(row.get('body_hash') or '')[:16]}…`\n"
                f"- renderer: `{prov.get('renderer_type')}` model=`{prov.get('returned_model_id')}` "
                f"prompt=`{prov.get('prompt_version')}`\n"
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
