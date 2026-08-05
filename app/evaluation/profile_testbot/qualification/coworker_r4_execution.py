"""R4 reviewed-live campaign runner — dry-run default; execute fail-closed until manual gate."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

from app.evaluation.profile_testbot.qualification.coworker_r4_approval_artifact import (
    compute_file_sha256,
    load_r4_approval_artifact,
    validate_r4_approval_artifact,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_candidates import (
    generate_r4_candidates,
    write_r4_candidate_package,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_human_review import (
    build_r4_human_review_package,
    validate_r4_human_review_bindings,
    write_r4_human_review_package,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_live_backend import (
    describe_r4_live_backend_wiring,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_live_jit import (
    run_r4_full_live_jit,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_mailbox_baseline import (
    build_r4_mailbox_baseline,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_manifest import (
    build_r4_campaign_manifest,
    validate_r4_manifest,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_readiness import (
    evaluate_coworker_r4_readiness,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_EXECUTE_AI_MODE,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
    R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    R4_LOCKED_REVIEW_ARTIFACT_SHA256,
    R4_NO_SEND_SCENARIO_IDS,
    R4_PROFILE_ID,
    R4_SCENARIO_IDS,
    R4_SEND_SCENARIO_IDS,
    R4_SUBJECT_PREFIX,
    R4_TENANT_ID,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_reviewed_snapshot import (
    R4ReviewedBodySnapshot,
    validate_r4_snapshot_for_reply,
)
from app.workflows.reply_quality.provenance import LLM_RENDERER

Mode = Literal["dry_run", "execute", "full_jit", "mailbox_baseline"]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _body_hash_map(candidates: dict[str, Any]) -> dict[str, str]:
    return {
        str(c["scenario_id"]): str(c["body_hash"])
        for c in (candidates.get("send_candidates") or [])
        if c.get("scenario_id") and c.get("body_hash")
    }


def validate_locked_candidate_bindings(
    *,
    candidate_runtime_sha: str,
    candidates: dict[str, Any],
    human_review: dict[str, Any],
    human_review_path: Path,
    manifest: dict[str, Any],
) -> list[str]:
    blockers: list[str] = []
    if candidate_runtime_sha != R4_LOCKED_CANDIDATE_RUNTIME_SHA:
        blockers.append("candidate_runtime_sha_must_be_locked_b7fd95e")
    if candidates.get("runtime_sha") != candidate_runtime_sha:
        blockers.append("candidates_runtime_sha_mismatch")
    if human_review.get("runtime_sha") != candidate_runtime_sha:
        blockers.append("review_runtime_sha_mismatch")
    if manifest.get("manifest_semantic_hash") != R4_LOCKED_MANIFEST_SEMANTIC_HASH:
        blockers.append("manifest_semantic_hash_mismatch")
    if candidates.get("candidate_package_semantic_hash") != R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH:
        blockers.append("candidate_package_semantic_hash_mismatch")
    if human_review.get("candidate_package_semantic_hash") != R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH:
        blockers.append("review_candidate_package_hash_mismatch")
    review_sha = compute_file_sha256(human_review_path)
    if review_sha != R4_LOCKED_REVIEW_ARTIFACT_SHA256:
        blockers.append("human_review_sha256_mismatch")
    bindings = validate_r4_human_review_bindings(candidates, human_review)
    if not bindings.get("human_review_complete"):
        blockers.extend(bindings.get("blockers") or [])
    if len(candidates.get("send_candidates") or []) != 20:
        blockers.append("send_candidates!=20")
    if len(candidates.get("no_send_candidates") or []) != 16:
        blockers.append("no_send_candidates!=16")
    for c in candidates.get("send_candidates") or []:
        if c.get("renderer_type") != LLM_RENDERER:
            blockers.append(f"renderer_not_constrained:{c.get('scenario_id')}")
    return blockers


def build_r4_campaign_registration_payload(
    *,
    campaign_id: str,
    candidate_runtime_sha: str,
    executor_runtime_sha: str,
    manifest_semantic_hash: str,
    candidate_package_semantic_hash: str,
    human_review_sha256: str,
    profile_id: str,
    profile_hash: str,
    body_hashes: dict[str, str],
) -> dict[str, Any]:
    return {
        "campaign_id": campaign_id,
        "tenant_id": R4_TENANT_ID,
        "campaign_type": R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        "execution_mode": R4_EXECUTION_MODE,
        "ai_mode": R4_EXECUTE_AI_MODE,
        "scenario_count": 36,
        "planned_sends": 20,
        "planned_no_send": 16,
        "send_budget": 20,
        "no_automatic_retry": True,
        "drafts": "forbidden",
        "candidate_runtime_sha": candidate_runtime_sha,
        "executor_runtime_sha": executor_runtime_sha,
        "manifest_semantic_hash": manifest_semantic_hash,
        "candidate_package_semantic_hash": candidate_package_semantic_hash,
        "human_review_sha256": human_review_sha256,
        "profile_id": profile_id,
        "profile_hash": profile_hash,
        "scenario_ids": list(R4_SCENARIO_IDS),
        "send_scenario_ids": list(R4_SEND_SCENARIO_IDS),
        "no_send_scenario_ids": list(R4_NO_SEND_SCENARIO_IDS),
        "body_hashes": body_hashes,
        "automatic_gmail": False,
        "production_activation": False,
    }


def _scenario_subject(campaign_id: str, evaluation_run_id: str, scenario_id: str) -> str:
    return f"{R4_SUBJECT_PREFIX}/{campaign_id}/{evaluation_run_id}/{scenario_id}"


def _execute_send_scenario_stub(
    *,
    scenario_id: str,
    candidate: dict[str, Any],
    review_row: dict[str, Any],
    campaign_id: str,
    candidate_runtime_sha: str,
    executor_runtime_sha: str,
    manifest_semantic_hash: str,
    candidate_package_semantic_hash: str,
    human_review_sha256: str,
    recipient: str,
    live_executor: Callable[..., dict[str, Any]] | None,
) -> dict[str, Any]:
    """Execute one send scenario. Without live_executor, returns blocked (no Gmail)."""
    evaluation_run_id = str(uuid.uuid4())
    approval_operation_id = str(uuid.uuid4())
    reply_operation_id = str(uuid.uuid4())
    snapshot = R4ReviewedBodySnapshot(
        campaign_type=R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        execution_mode=R4_EXECUTION_MODE,
        scenario_id=scenario_id,
        candidate_runtime_sha=candidate_runtime_sha,
        executor_runtime_sha=executor_runtime_sha,
        manifest_semantic_hash=manifest_semantic_hash,
        candidate_package_semantic_hash=candidate_package_semantic_hash,
        human_review_artifact_hash=human_review_sha256,
        plan_hash=str(candidate.get("plan_hash") or ""),
        reviewed_body=str(candidate.get("rendered_body") or ""),
        reviewed_body_hash=str(candidate.get("body_hash") or ""),
        review_status=str(review_row.get("review_status") or ""),
        renderer_type=str(candidate.get("renderer_type") or ""),
        model_id=candidate.get("model_id") or candidate.get("returned_model_id"),
        prompt_version=candidate.get("prompt_version"),
        recipient=recipient,
        campaign_id=campaign_id,
        evaluation_run_id=evaluation_run_id,
    )
    snap_blockers = validate_r4_snapshot_for_reply(
        snapshot,
        expected_body_hash=str(candidate.get("body_hash") or ""),
        send_scenario_ids=set(R4_SEND_SCENARIO_IDS),
        recipient=recipient,
        blocking_notes=list(review_row.get("blocking_notes") or []),
    )
    if snap_blockers:
        return {
            "scenario_id": scenario_id,
            "planned_gmail_send": True,
            "status": "blocked",
            "evaluation_run_id": evaluation_run_id,
            "failure_stage": "snapshot_validation",
            "failure_reason": ",".join(snap_blockers),
            "gmail_sends": 0,
            "gmail_drafts": 0,
        }

    if live_executor is None:
        return {
            "scenario_id": scenario_id,
            "planned_gmail_send": True,
            "status": "blocked",
            "evaluation_run_id": evaluation_run_id,
            "approval_operation_id": approval_operation_id,
            "reply_operation_id": reply_operation_id,
            "subject": _scenario_subject(campaign_id, evaluation_run_id, scenario_id),
            "snapshot": snapshot.to_dict(),
            "failure_stage": "live_executor_not_invoked",
            "failure_reason": "execute_requires_wired_live_backend_and_approval",
            "gmail_sends": 0,
            "gmail_drafts": 0,
            "llm_calls": 0,
            "candidates_regenerated": False,
        }

    result = live_executor(
        scenario_id=scenario_id,
        snapshot=snapshot,
        candidate=candidate,
        review_row=review_row,
        evaluation_run_id=evaluation_run_id,
        approval_operation_id=approval_operation_id,
        reply_operation_id=reply_operation_id,
    )
    result.setdefault("llm_calls", 0)
    result.setdefault("candidates_regenerated", False)
    return result


def _execute_no_send_scenario_stub(
    *,
    scenario_id: str,
    campaign_id: str,
    live_executor: Callable[..., dict[str, Any]] | None,
) -> dict[str, Any]:
    evaluation_run_id = str(uuid.uuid4())
    if live_executor is None:
        return {
            "scenario_id": scenario_id,
            "planned_gmail_send": False,
            "status": "blocked",
            "evaluation_run_id": evaluation_run_id,
            "failure_stage": "live_executor_not_invoked",
            "failure_reason": "execute_requires_wired_live_backend_and_approval",
            "gmail_sends": 0,
            "gmail_drafts": 0,
            "r4_reviewed_body_applied": False,
        }
    result = live_executor(
        scenario_id=scenario_id,
        evaluation_run_id=evaluation_run_id,
        planned_gmail_send=False,
        campaign_id=campaign_id,
    )
    result["r4_reviewed_body_applied"] = False
    return result


def run_r4_live_campaign(
    *,
    mode: Mode,
    candidate_runtime_sha: str,
    expected_executor_sha: str,
    profile_id: str = R4_PROFILE_ID,
    seed: int = 42,
    status_dir: Path | None = None,
    approval_path: Path | None = None,
    human_review_path: Path | None = None,
    candidates_path: Path | None = None,
    manifest_path: Path | None = None,
    campaign_id: str | None = None,
    recipient: str | None = None,
    live_executor: Callable[..., dict[str, Any]] | None = None,
    live_executor_factory: Callable[..., Callable[..., dict[str, Any]]] | None = None,
    # Optional live probe results for full JIT
    tenant_intake_ready: bool | None = None,
    sender_gmail_ready: bool | None = None,
    recipient_gmail_ready: bool | None = None,
    reply_provider_ready: bool | None = None,
    delivery_observation_ready: bool | None = None,
    exact_message_ready: bool | None = None,
    registration_contract_ready: bool | None = None,
    mutation_contract_ready: bool | None = None,
) -> dict[str, Any]:
    status_dir = status_dir or Path("storage/status")
    generated_at = _utc_now()
    campaign_id = campaign_id or str(uuid.uuid4())
    if not recipient:
        from app.evaluation.live.config import get_live_eval_config

        recipients = sorted(get_live_eval_config().recipient_emails)
        recipient = recipients[0] if recipients else "niklas.palm@sol-f.se"
    recipient = recipient.strip().lower()

    # Manifest: prefer locked file / rebuild bound to candidate SHA (never executor SHA as candidate).
    if manifest_path and Path(manifest_path).is_file():
        manifest = _load_json(Path(manifest_path))
        # Locked on-disk packages may omit semantic_payload; rehydrate when hash matches.
        if not isinstance(manifest.get("semantic_payload"), dict):
            rebuilt = build_r4_campaign_manifest(
                runtime_sha=candidate_runtime_sha, profile_id=profile_id, seed=seed
            )
            if rebuilt.get("manifest_semantic_hash") == manifest.get("manifest_semantic_hash"):
                manifest = {**manifest, "semantic_payload": rebuilt["semantic_payload"]}
    else:
        manifest = build_r4_campaign_manifest(
            runtime_sha=candidate_runtime_sha, profile_id=profile_id, seed=seed
        )

    if candidates_path is None or not Path(candidates_path).is_file():
        if mode == "execute":
            return {
                "mode": mode,
                "overall_status": "STOPPED",
                "stop_reason": "execute_requires_locked_candidates_json",
                "candidate_runtime_sha": candidate_runtime_sha,
                "executor_runtime_sha": expected_executor_sha,
                "gmail_sends": 0,
                "gmail_drafts": 0,
                "external_writes": 0,
                "new_trigger_emails": 0,
                "llm_calls": 0,
                "candidates_regenerated": False,
            }
        candidates = generate_r4_candidates(
            runtime_sha=candidate_runtime_sha, profile_id=profile_id, seed=seed
        )
        candidates_regenerated = True
    else:
        candidates = _load_json(Path(candidates_path))
        candidates_regenerated = False

    if human_review_path and Path(human_review_path).is_file():
        human_review = _load_json(Path(human_review_path))
        review_path = Path(human_review_path)
    else:
        human_review = build_r4_human_review_package(
            candidates, runtime_sha=candidate_runtime_sha
        )
        review_path = status_dir / f"digital-coworker-r4-human-review-{candidate_runtime_sha[:7]}.json"

    binding_blockers: list[str] = []
    enforce_locked = (
        mode in {"execute", "full_jit"}
        or (candidates_path is not None and human_review_path is not None)
    )
    if enforce_locked and review_path.is_file():
        binding_blockers = validate_locked_candidate_bindings(
            candidate_runtime_sha=candidate_runtime_sha,
            candidates=candidates,
            human_review=human_review,
            human_review_path=review_path,
            manifest=manifest,
        )

    result: dict[str, Any] = {
        "mode": mode,
        "generated_at": generated_at,
        "campaign_id": campaign_id,
        "candidate_runtime_sha": candidate_runtime_sha,
        "executor_runtime_sha": expected_executor_sha,
        "manifest_semantic_hash": manifest.get("manifest_semantic_hash"),
        "candidate_package_semantic_hash": candidates.get("candidate_package_semantic_hash"),
        "human_review_sha256": compute_file_sha256(review_path)
        if review_path.is_file()
        else None,
        "manifest_blockers": validate_r4_manifest(manifest),
        "binding_blockers": binding_blockers,
        "candidates_overall_status": candidates.get("overall_status"),
        "candidates_source": str(candidates_path) if candidates_path else "generated",
        "human_review_source": str(human_review_path) if human_review_path else "built",
        "candidates_regenerated": candidates_regenerated,
        "llm_calls": 0,
        "gmail_sends": 0,
        "gmail_drafts": 0,
        "external_writes": 0,
        "new_trigger_emails": 0,
        "automatic_gmail": False,
        "production_activation": False,
        "r3_hold_override_generalized": False,
        "ai_mode_registration": R4_EXECUTE_AI_MODE,
        **describe_r4_live_backend_wiring(),
        "campaign_registration": build_r4_campaign_registration_payload(
            campaign_id=campaign_id,
            candidate_runtime_sha=candidate_runtime_sha,
            executor_runtime_sha=expected_executor_sha,
            manifest_semantic_hash=str(manifest.get("manifest_semantic_hash") or ""),
            candidate_package_semantic_hash=str(
                candidates.get("candidate_package_semantic_hash") or ""
            ),
            human_review_sha256=str(
                compute_file_sha256(review_path) if review_path.is_file() else ""
            ),
            profile_id=profile_id,
            profile_hash=str(manifest.get("profile_hash") or ""),
            body_hashes=_body_hash_map(candidates),
        ),
    }

    # Never claim candidate SHA is the running executor code.
    if result["candidate_runtime_sha"] == result["executor_runtime_sha"]:
        result["sha_roles_note"] = (
            "candidate_runtime_sha and executor_runtime_sha happen to be equal values "
            "but remain distinct roles"
        )

    structural = evaluate_coworker_r4_readiness(
        runtime_sha=candidate_runtime_sha,
        manifest=manifest,
        candidates=candidates,
        human_review=human_review,
        skip_live_probes=True,
    )
    result["structural_readiness"] = structural

    if mode == "mailbox_baseline":
        from app.evaluation.profile_testbot.qualification.coworker_r4_live_probes import (
            probe_r4_mailbox_baseline,
        )

        baseline = build_r4_mailbox_baseline(
            campaign_id=campaign_id,
            probe_fn=lambda: probe_r4_mailbox_baseline(
                campaign_id=campaign_id, recipient_email=recipient
            ),
        )
        result["mailbox_baseline"] = baseline
        result["overall_status"] = "PASS" if baseline.get("passed") else "BLOCKED"
        result["stop_reason"] = None if baseline.get("passed") else baseline.get("blockers")
        paths = write_r4_execution_reports(
            result=result,
            manifest=manifest,
            candidates=candidates,
            human_review=human_review,
            status_dir=status_dir,
            rewrite_locked_packages=False,
            report_stem="mailbox-baseline",
        )
        result["report_paths"] = {k: str(v) for k, v in paths.items()}
        return result

    if mode == "full_jit":
        # Auto-collect read-only live probes unless explicit probe flags are supplied.
        jit = run_r4_full_live_jit(
            candidate_runtime_sha=candidate_runtime_sha,
            executor_runtime_sha=expected_executor_sha,
            manifest=manifest,
            candidates=candidates,
            human_review=human_review,
            human_review_path=review_path,
            api_build_git_sha=None
            if tenant_intake_ready is None
            else expected_executor_sha,
            worker_build_git_sha=None
            if tenant_intake_ready is None
            else expected_executor_sha,
            runner_build_git_sha=expected_executor_sha,
            tenant_intake_ready=tenant_intake_ready,
            sender_gmail_ready=sender_gmail_ready,
            recipient_gmail_ready=recipient_gmail_ready,
            reply_provider_ready=reply_provider_ready,
            delivery_observation_ready=delivery_observation_ready,
            exact_message_ready=exact_message_ready,
            registration_contract_ready=registration_contract_ready,
            mutation_contract_ready=mutation_contract_ready,
            run_live_probes=True,
            auto_collect_live_probes=True,
            recipient_email=recipient,
        )
        result["full_live_jit"] = jit
        result["overall_status"] = "PASS" if jit.get("passed") else "BLOCKED"
        result["stop_reason"] = None if jit.get("passed") else jit.get("blockers")
        result["gmail_sends"] = 0
        paths = write_r4_execution_reports(
            result=result,
            manifest=manifest,
            candidates=candidates,
            human_review=human_review,
            status_dir=status_dir,
            rewrite_locked_packages=False,
            report_stem="full-live-jit",
        )
        result["report_paths"] = {k: str(v) for k, v in paths.items()}
        return result

    if mode == "dry_run":
        result["jit_type"] = "structural_dry_run"
        result["full_live_jit"] = False
        if binding_blockers:
            result["overall_status"] = "BLOCKED"
            result["stop_reason"] = {"binding_blockers": binding_blockers}
        elif (
            structural.get("r4_campaign_ready_for_dry_run")
            and candidates.get("overall_status") == "PASS"
        ):
            result["overall_status"] = "PASS"
            result["stop_reason"] = None
            if structural.get("human_review_complete"):
                result["manual_execution_confirmation"] = (
                    "MANUAL EXECUTION CONFIRMATION REQUIRED — R4 reviewed-live executor "
                    "awaiting separate signed approval; structural dry-run PASS without "
                    "Gmail-writes (full live JIT required before --execute)"
                )
        else:
            result["overall_status"] = "BLOCKED"
            result["stop_reason"] = {
                "readiness_blockers": structural.get("blockers"),
                "binding_blockers": binding_blockers,
            }
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

    # --- execute mode ---
    if approval_path is None or not Path(approval_path).is_file():
        result["overall_status"] = "STOPPED"
        result["stop_reason"] = "missing_manual_execution_approval_artifact"
        result["failure_stage"] = "approval_gate"
        paths = write_r4_execution_reports(
            result=result,
            manifest=manifest,
            candidates=candidates,
            human_review=human_review,
            status_dir=status_dir,
            rewrite_locked_packages=False,
            report_stem="execute-stopped",
        )
        result["report_paths"] = {k: str(v) for k, v in paths.items()}
        return result

    if candidates_regenerated or candidates_path is None:
        result["overall_status"] = "STOPPED"
        result["stop_reason"] = "execute_forbids_candidate_regeneration"
        result["failure_stage"] = "candidate_lock"
        return result

    approval = load_r4_approval_artifact(Path(approval_path))
    from app.evaluation.live.config import get_live_eval_config

    live_recipients = sorted(get_live_eval_config().recipient_emails)
    approval_validation = validate_r4_approval_artifact(
        approval,
        candidate_runtime_sha=candidate_runtime_sha,
        executor_runtime_sha=expected_executor_sha,
        manifest_semantic_hash=str(manifest.get("manifest_semantic_hash") or ""),
        candidate_package_semantic_hash=str(
            candidates.get("candidate_package_semantic_hash") or ""
        ),
        human_review_sha256=compute_file_sha256(review_path),
        body_hashes=_body_hash_map(candidates),
        require_manual_approved=True,
        expected_ai_mode=R4_EXECUTE_AI_MODE,
        expected_recipient_allowlist=[recipient],
        live_eval_recipient_allowlist=live_recipients,
        expected_manifest_path=manifest_path,
        expected_candidates_path=candidates_path,
        expected_human_review_path=human_review_path,
    )
    result["approval_validation"] = approval_validation.to_dict()
    result["approval_artifact_hash"] = approval.artifact_hash
    if not approval_validation.valid:
        result["overall_status"] = "STOPPED"
        result["stop_reason"] = {
            "approval_blockers": approval_validation.blockers,
        }
        result["failure_stage"] = "approval_validation"
        result["backend_invoked"] = False
        paths = write_r4_execution_reports(
            result=result,
            manifest=manifest,
            candidates=candidates,
            human_review=human_review,
            status_dir=status_dir,
            rewrite_locked_packages=False,
            report_stem="execute-stopped",
        )
        result["report_paths"] = {k: str(v) for k, v in paths.items()}
        return result

    jit = run_r4_full_live_jit(
        candidate_runtime_sha=candidate_runtime_sha,
        executor_runtime_sha=expected_executor_sha,
        manifest=manifest,
        candidates=candidates,
        human_review=human_review,
        human_review_path=review_path,
        api_build_git_sha=None if tenant_intake_ready is None else expected_executor_sha,
        worker_build_git_sha=None if tenant_intake_ready is None else expected_executor_sha,
        runner_build_git_sha=expected_executor_sha,
        tenant_intake_ready=tenant_intake_ready,
        sender_gmail_ready=sender_gmail_ready,
        recipient_gmail_ready=recipient_gmail_ready,
        reply_provider_ready=reply_provider_ready,
        delivery_observation_ready=delivery_observation_ready,
        exact_message_ready=exact_message_ready,
        registration_contract_ready=registration_contract_ready,
        mutation_contract_ready=mutation_contract_ready,
        run_live_probes=True,
        auto_collect_live_probes=True,
        recipient_email=recipient,
    )
    result["full_live_jit"] = jit
    if not jit.get("passed") or binding_blockers:
        result["overall_status"] = "STOPPED"
        result["stop_reason"] = {
            "jit_blockers": jit.get("blockers"),
            "binding_blockers": binding_blockers,
        }
        result["failure_stage"] = "full_live_jit"
        result["backend_invoked"] = False
        paths = write_r4_execution_reports(
            result=result,
            manifest=manifest,
            candidates=candidates,
            human_review=human_review,
            status_dir=status_dir,
            rewrite_locked_packages=False,
            report_stem="execute-stopped",
        )
        result["report_paths"] = {k: str(v) for k, v in paths.items()}
        return result

    from app.evaluation.profile_testbot.qualification.coworker_r4_live_probes import (
        probe_r4_mailbox_baseline,
    )

    baseline = build_r4_mailbox_baseline(
        campaign_id=campaign_id,
        probe_fn=lambda: probe_r4_mailbox_baseline(
            campaign_id=campaign_id, recipient_email=recipient
        ),
    )
    result["mailbox_baseline"] = baseline
    result["execute_gate_binding"] = {
        "executor_runtime_sha": expected_executor_sha,
        "campaign_id": campaign_id,
        "approval_artifact_hash": approval.artifact_hash,
        "manifest_semantic_hash": manifest.get("manifest_semantic_hash"),
        "candidate_package_semantic_hash": candidates.get("candidate_package_semantic_hash"),
        "human_review_sha256": compute_file_sha256(review_path),
        "full_live_jit_passed": bool(jit.get("passed")),
        "mailbox_baseline_passed": bool(baseline.get("passed")),
    }
    if not baseline.get("passed"):
        result["overall_status"] = "STOPPED"
        result["stop_reason"] = baseline.get("blockers")
        result["failure_stage"] = "mailbox_baseline"
        result["backend_invoked"] = False
        return result

    # Wire live executor only after all gates PASS.
    if live_executor is None and live_executor_factory is not None:
        live_executor = live_executor_factory(
            candidate_runtime_sha=candidate_runtime_sha,
            executor_runtime_sha=expected_executor_sha,
            campaign_id=campaign_id,
            approval_artifact=approval,
            manifest=manifest,
            candidates=candidates,
            human_review=human_review,
            recipient=recipient,
        )
        result["live_executor_wired_after_gates"] = True
    elif live_executor is not None:
        result["live_executor_wired_after_gates"] = True
    else:
        result["live_executor_wired_after_gates"] = False
    result["backend_invoked"] = live_executor is not None

    # Sequential campaign — fail closed. Without live_executor this stops before Gmail.
    outcomes: list[dict[str, Any]] = []
    review_by_id = {r.get("scenario_id"): r for r in (human_review.get("reviews") or [])}
    cand_by_id = {c.get("scenario_id"): c for c in (candidates.get("send_candidates") or [])}

    for scenario_id in R4_SEND_SCENARIO_IDS:
        row = _execute_send_scenario_stub(
            scenario_id=scenario_id,
            candidate=cand_by_id[scenario_id],
            review_row=review_by_id[scenario_id],
            campaign_id=campaign_id,
            candidate_runtime_sha=candidate_runtime_sha,
            executor_runtime_sha=expected_executor_sha,
            manifest_semantic_hash=str(manifest.get("manifest_semantic_hash") or ""),
            candidate_package_semantic_hash=str(
                candidates.get("candidate_package_semantic_hash") or ""
            ),
            human_review_sha256=compute_file_sha256(review_path),
            recipient=recipient,
            live_executor=live_executor,
        )
        outcomes.append(row)
        if row.get("status") not in {"succeeded", "pass", "PASS", "passed"}:
            remaining = [
                {
                    "scenario_id": sid,
                    "planned_gmail_send": True,
                    "status": "not_run",
                }
                for sid in R4_SEND_SCENARIO_IDS
                if sid not in {o.get("scenario_id") for o in outcomes}
            ] + [
                {
                    "scenario_id": sid,
                    "planned_gmail_send": False,
                    "status": "not_run",
                }
                for sid in R4_NO_SEND_SCENARIO_IDS
            ]
            result["scenario_outcomes"] = outcomes + remaining
            result["overall_status"] = "partial_campaign_stopped"
            result["classification"] = "partial_campaign_stopped"
            result["stop_reason"] = {
                "failed_scenario": scenario_id,
                "failure_stage": row.get("failure_stage"),
                "failure_reason": row.get("failure_reason"),
            }
            result["resume_forbidden"] = True
            result["gmail_sends"] = sum(int(o.get("gmail_sends") or 0) for o in outcomes)
            result["gmail_drafts"] = sum(int(o.get("gmail_drafts") or 0) for o in outcomes)
            paths = write_r4_execution_reports(
                result=result,
                manifest=manifest,
                candidates=candidates,
                human_review=human_review,
                status_dir=status_dir,
                rewrite_locked_packages=False,
                report_stem="reconciliation",
            )
            result["report_paths"] = {k: str(v) for k, v in paths.items()}
            return result

    for scenario_id in R4_NO_SEND_SCENARIO_IDS:
        row = _execute_no_send_scenario_stub(
            scenario_id=scenario_id,
            campaign_id=campaign_id,
            live_executor=live_executor,
        )
        outcomes.append(row)
        if row.get("status") not in {"succeeded", "pass", "PASS", "passed", "verified_no_send"}:
            remaining = [
                {
                    "scenario_id": sid,
                    "planned_gmail_send": False,
                    "status": "not_run",
                }
                for sid in R4_NO_SEND_SCENARIO_IDS
                if sid not in {o.get("scenario_id") for o in outcomes if not o.get("planned_gmail_send")}
            ]
            result["scenario_outcomes"] = outcomes + remaining
            result["overall_status"] = "partial_campaign_stopped"
            result["classification"] = "partial_campaign_stopped"
            result["resume_forbidden"] = True
            result["stop_reason"] = {
                "failed_scenario": scenario_id,
                "failure_stage": row.get("failure_stage"),
                "failure_reason": row.get("failure_reason"),
            }
            paths = write_r4_execution_reports(
                result=result,
                manifest=manifest,
                candidates=candidates,
                human_review=human_review,
                status_dir=status_dir,
                rewrite_locked_packages=False,
                report_stem="reconciliation",
            )
            result["report_paths"] = {k: str(v) for k, v in paths.items()}
            return result

    result["scenario_outcomes"] = outcomes
    result["overall_status"] = "PASS"
    result["gmail_sends"] = sum(int(o.get("gmail_sends") or 0) for o in outcomes)
    result["gmail_drafts"] = sum(int(o.get("gmail_drafts") or 0) for o in outcomes)
    paths = write_r4_execution_reports(
        result=result,
        manifest=manifest,
        candidates=candidates,
        human_review=human_review,
        status_dir=status_dir,
        rewrite_locked_packages=False,
        report_stem="live-execution",
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
    report_stem: str = "dry-run",
) -> dict[str, Path]:
    status_dir.mkdir(parents=True, exist_ok=True)
    sha = str(result.get("executor_runtime_sha") or result.get("candidate_runtime_sha") or "unknown")[
        :7
    ]
    paths: dict[str, Path] = {}

    manifest_path = status_dir / f"digital-coworker-r4-manifest-{sha}.json"
    safe_manifest = {k: v for k, v in manifest.items() if k != "semantic_payload"}
    # Prefer candidate-sha naming for locked manifest file when present.
    cand_sha = str(result.get("candidate_runtime_sha") or "")[:7]
    if cand_sha:
        locked_manifest = status_dir / f"digital-coworker-r4-manifest-{cand_sha}.json"
        locked_manifest.write_text(
            json.dumps(safe_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        paths["manifest"] = locked_manifest
    else:
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
        if result.get("candidates_source"):
            paths["candidates_json"] = Path(str(result["candidates_source"]))
        if result.get("human_review_source"):
            paths["human_review_json"] = Path(str(result["human_review_source"]))

    report_json = status_dir / f"digital-coworker-r4-{report_stem}-{sha}.json"
    report_md = status_dir / f"digital-coworker-r4-{report_stem}-{sha}.md"
    report_json.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        f"# R4 {report_stem} report ({sha})",
        "",
        f"- mode: `{result.get('mode')}`",
        f"- overall_status: **{result.get('overall_status')}**",
        f"- candidate_runtime_sha: `{result.get('candidate_runtime_sha')}`",
        f"- executor_runtime_sha: `{result.get('executor_runtime_sha')}`",
        f"- manifest_semantic_hash: `{result.get('manifest_semantic_hash')}`",
        f"- candidate_package_semantic_hash: `{result.get('candidate_package_semantic_hash')}`",
        f"- human_review_sha256: `{result.get('human_review_sha256')}`",
        f"- gmail_sends: **{result.get('gmail_sends')}**",
        f"- gmail_drafts: **{result.get('gmail_drafts')}**",
        f"- external_writes: **{result.get('external_writes')}**",
        f"- llm_calls: **{result.get('llm_calls')}**",
        f"- candidates_regenerated: **{result.get('candidates_regenerated')}**",
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
