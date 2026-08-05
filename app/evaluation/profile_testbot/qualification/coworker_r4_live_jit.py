"""Full read-only R4 live JIT readiness (no Gmail writes)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from app.evaluation.profile_testbot.qualification.coworker_r4_approval_artifact import (
    compute_file_sha256,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_hold_materialization import (
    R4_0088_SCENARIO_ID,
    resolve_r4_0088_hold_materialization,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_human_review import (
    validate_r4_human_review_bindings,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_live_probes import (
    collect_r4_live_probes,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_mutation_contract import (
    validate_r4_mutation_operation,
    R4_MUTATION_PROCESS_DELIVERY,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_readiness import (
    evaluate_coworker_r4_readiness,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_0088_REVIEWED_BODY_HASH,
    R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
    R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    R4_LOCKED_REVIEW_ARTIFACT_SHA256,
    R4_NO_SEND_SCENARIO_IDS,
    R4_SEND_MAX,
    R4_SEND_SCENARIO_IDS,
)
from app.workflows.reply_quality.provenance import LLM_RENDERER


def _sha_env() -> str:
    return (os.environ.get("BUILD_GIT_SHA") or os.environ.get("GIT_COMMIT") or "").strip()


def _any_probe_kwarg_set(**kwargs: Any) -> bool:
    return any(v is not None for v in kwargs.values())


def run_r4_full_live_jit(
    *,
    candidate_runtime_sha: str,
    executor_runtime_sha: str,
    manifest: dict[str, Any],
    candidates: dict[str, Any],
    human_review: dict[str, Any],
    human_review_path: Path,
    api_build_git_sha: str | None = None,
    worker_build_git_sha: str | None = None,
    runner_build_git_sha: str | None = None,
    tenant_intake_ready: bool | None = None,
    sender_gmail_ready: bool | None = None,
    recipient_gmail_ready: bool | None = None,
    reply_provider_ready: bool | None = None,
    delivery_observation_ready: bool | None = None,
    exact_message_ready: bool | None = None,
    registration_contract_ready: bool | None = None,
    mutation_contract_ready: bool | None = None,
    orphan_isolation_ready: bool | None = True,
    run_live_probes: bool = True,
    auto_collect_live_probes: bool = True,
    recipient_email: str = "ni@sol-f.se",
) -> dict[str, Any]:
    """Full live JIT. When run_live_probes=True, collects read-only probes unless supplied."""
    blockers: list[str] = []
    review_sha = compute_file_sha256(human_review_path)
    probe_bundle: dict[str, Any] | None = None
    # Treat default True as unset so auto-collect can still run when no other probes given.
    orphan_for_collect_check = (
        None if orphan_isolation_ready is True else orphan_isolation_ready
    )

    if candidate_runtime_sha != R4_LOCKED_CANDIDATE_RUNTIME_SHA:
        blockers.append("candidate_runtime_sha_not_locked_b7fd95e")
    if candidates.get("runtime_sha") != candidate_runtime_sha:
        blockers.append("candidates_runtime_sha_mismatch")
    if human_review.get("runtime_sha") != candidate_runtime_sha:
        blockers.append("review_runtime_sha_mismatch")
    if manifest.get("manifest_semantic_hash") != R4_LOCKED_MANIFEST_SEMANTIC_HASH:
        blockers.append("manifest_semantic_hash_mismatch")
    if candidates.get("manifest_semantic_hash") != R4_LOCKED_MANIFEST_SEMANTIC_HASH:
        blockers.append("candidates_manifest_hash_mismatch")
    if candidates.get("candidate_package_semantic_hash") != R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH:
        blockers.append("candidate_package_semantic_hash_mismatch")
    if human_review.get("candidate_package_semantic_hash") != R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH:
        blockers.append("review_candidate_package_hash_mismatch")
    if review_sha != R4_LOCKED_REVIEW_ARTIFACT_SHA256:
        blockers.append("review_artifact_sha256_mismatch")

    if run_live_probes and auto_collect_live_probes and not _any_probe_kwarg_set(
        tenant_intake_ready=tenant_intake_ready,
        sender_gmail_ready=sender_gmail_ready,
        recipient_gmail_ready=recipient_gmail_ready,
        reply_provider_ready=reply_provider_ready,
        delivery_observation_ready=delivery_observation_ready,
        exact_message_ready=exact_message_ready,
        registration_contract_ready=registration_contract_ready,
        mutation_contract_ready=mutation_contract_ready,
        orphan_isolation_ready=orphan_for_collect_check,
        api_build_git_sha=api_build_git_sha,
        worker_build_git_sha=worker_build_git_sha,
    ):
        probe_bundle = collect_r4_live_probes(
            executor_runtime_sha=executor_runtime_sha,
            manifest=manifest,
            recipient_email=recipient_email,
        )
        api_build_git_sha = probe_bundle.get("api_build_git_sha")
        worker_build_git_sha = probe_bundle.get("worker_build_git_sha")
        runner_build_git_sha = probe_bundle.get("runner_build_git_sha") or executor_runtime_sha
        tenant_intake_ready = probe_bundle.get("tenant_intake_ready")
        sender_gmail_ready = probe_bundle.get("sender_gmail_ready")
        recipient_gmail_ready = probe_bundle.get("recipient_gmail_ready")
        reply_provider_ready = probe_bundle.get("reply_provider_ready")
        delivery_observation_ready = probe_bundle.get("delivery_observation_ready")
        exact_message_ready = probe_bundle.get("exact_message_ready")
        registration_contract_ready = probe_bundle.get("registration_contract_ready")
        mutation_contract_ready = probe_bundle.get("mutation_contract_ready")
        orphan_isolation_ready = probe_bundle.get("orphan_isolation_ready")
        blockers.extend(probe_bundle.get("probe_blockers") or [])

    api_sha = api_build_git_sha or _sha_env()
    worker_sha = worker_build_git_sha or api_sha
    runner_sha = runner_build_git_sha or executor_runtime_sha
    if api_sha != executor_runtime_sha:
        blockers.append("api_sha_mismatch_executor")
    if worker_sha != executor_runtime_sha:
        blockers.append("worker_sha_mismatch_executor")
    if runner_sha != executor_runtime_sha:
        blockers.append("runner_sha_mismatch_executor")

    # Body + review bindings
    bindings = validate_r4_human_review_bindings(candidates, human_review)
    if not bindings.get("human_review_complete"):
        blockers.extend(f"review:{b}" for b in (bindings.get("blockers") or []))

    sends = candidates.get("send_candidates") or []
    body_ok = 0
    for c in sends:
        rev = next(
            (r for r in (human_review.get("reviews") or []) if r.get("scenario_id") == c.get("scenario_id")),
            None,
        )
        if (
            rev
            and rev.get("body_hash") == c.get("body_hash")
            and rev.get("bound_body_hash") == c.get("body_hash")
            and rev.get("review_status") in {"PASS", "PASS_WITH_NOTE"}
            and not (rev.get("blocking_notes") or [])
        ):
            body_ok += 1
        else:
            blockers.append(f"body_or_review_binding:{c.get('scenario_id')}")
    if body_ok != R4_SEND_MAX:
        blockers.append(f"body_hash_bindings {body_ok}!=20")

    prov_ok = sum(1 for c in sends if c.get("renderer_type") == LLM_RENDERER)
    if prov_ok != R4_SEND_MAX:
        blockers.append(f"constrained_llm_provenance {prov_ok}!=20")

    no_send = int(candidates.get("no_send_candidate_count") or 0)
    if no_send != len(R4_NO_SEND_SCENARIO_IDS):
        blockers.append(f"no_send {no_send}!=16")

    # Structural readiness (no regen)
    structural = evaluate_coworker_r4_readiness(
        runtime_sha=candidate_runtime_sha,
        manifest=manifest,
        candidates=candidates,
        human_review=human_review,
        tenant_intake_ready=tenant_intake_ready,
        sender_gmail_ready=sender_gmail_ready,
        recipient_gmail_ready=recipient_gmail_ready,
        reply_provider_ready=reply_provider_ready,
        skip_live_probes=not run_live_probes,
    )
    if run_live_probes:
        if tenant_intake_ready is not True:
            blockers.append("tenant_intake_ready!=true")
        if sender_gmail_ready is not True:
            blockers.append("sender_gmail_ready!=true")
        if recipient_gmail_ready is not True:
            blockers.append("recipient_gmail_ready!=true")
        if reply_provider_ready is not True:
            blockers.append("reply_provider_ready!=true")
        if delivery_observation_ready is not True:
            blockers.append("delivery_observation_ready!=true")
        if exact_message_ready is not True:
            blockers.append("exact_message_ready!=true")
        if registration_contract_ready is not True:
            blockers.append("registration_contract_ready!=true")
        if mutation_contract_ready is not True:
            mut = validate_r4_mutation_operation(
                operation=R4_MUTATION_PROCESS_DELIVERY,
                tenant_id=manifest.get("tenant_id"),
                campaign_type=manifest.get("campaign_type"),
                execution_mode=manifest.get("execution_mode"),
                ai_mode="reviewed_live_llm_body",
            )
            if not mut.allowed:
                blockers.append("mutation_contract_ready!=true")
                blockers.extend(mut.blockers)
            else:
                blockers.append("mutation_contract_ready!=true")
        if orphan_isolation_ready is not True:
            blockers.append("orphan_isolation_ready!=true")

    # 0088 R4 contract readiness
    c088 = next((c for c in sends if c.get("scenario_id") == R4_0088_SCENARIO_ID), None)
    if not c088 or c088.get("body_hash") != R4_0088_REVIEWED_BODY_HASH:
        blockers.append("r4_0088_contract_body_hash_not_ready")
    else:
        res = resolve_r4_0088_hold_materialization(
            scenario_id=R4_0088_SCENARIO_ID,
            base_authorization="hold_for_review",
            reviewed_body_hash=c088.get("body_hash"),
            candidate_package_semantic_hash=candidates.get("candidate_package_semantic_hash"),
            human_review_artifact_hash=review_sha,
            campaign_type=manifest.get("campaign_type"),
            execution_mode=manifest.get("execution_mode"),
            ai_mode="reviewed_live_llm_body",
            tenant_id=manifest.get("tenant_id"),
        )
        if not res.eligible:
            blockers.append("r4_0088_contract_not_ready")
            blockers.extend(res.blockers)

    if candidates.get("gmail_sends") not in (0, None):
        blockers.append("gmail_sends_nonzero")
    if candidates.get("gmail_drafts") not in (0, None):
        blockers.append("gmail_drafts_nonzero")
    if candidates.get("automatic_gmail") is True:
        blockers.append("automatic_gmail_true")
    if candidates.get("production_activation") is True:
        blockers.append("production_activation_true")
    if int(candidates.get("send_candidate_count") or 0) != R4_SEND_MAX:
        blockers.append("send_budget!=20")

    blockers = list(dict.fromkeys(blockers))
    passed = not blockers and structural.get("human_review_complete") is True
    return {
        "jit_type": "full_live_jit" if run_live_probes else "structural_only",
        "full_live_jit": bool(run_live_probes),
        "passed": passed,
        "blockers": blockers,
        "candidate_runtime_sha": candidate_runtime_sha,
        "executor_runtime_sha": executor_runtime_sha,
        "api_build_git_sha": api_sha,
        "worker_build_git_sha": worker_sha,
        "runner_build_git_sha": runner_sha,
        "live_probes_collected": probe_bundle is not None,
        "live_probe_bundle": probe_bundle,
        "manifest_semantic_hash": manifest.get("manifest_semantic_hash"),
        "candidate_package_semantic_hash": candidates.get("candidate_package_semantic_hash"),
        "human_review_sha256": review_sha,
        "body_hash_bindings": f"{body_ok}/20",
        "constrained_llm_provenance": f"{prov_ok}/20",
        "no_send_ready": f"{no_send}/16",
        "human_review_complete": bindings.get("human_review_complete"),
        "structural_readiness": structural,
        "gmail_sends": 0,
        "gmail_drafts": 0,
        "gmail_triggers": 0,
        "external_writes": 0,
        "automatic_gmail": False,
        "production_activation": False,
        "send_scenario_ids": list(R4_SEND_SCENARIO_IDS),
        "no_send_scenario_ids": list(R4_NO_SEND_SCENARIO_IDS),
    }


def hash_json_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
