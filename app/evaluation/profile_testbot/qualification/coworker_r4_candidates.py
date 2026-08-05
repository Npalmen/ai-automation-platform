"""Write-free R4 candidate generation (strict constrained live LLM; no Gmail writes)."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.evaluation.profile_testbot.coworker_quality_oracles import (
    evaluate_coworker_reply_oracles,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.constants import (
    NO_SEND_BEHAVIORS,
    SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_llm_readiness import (
    run_r4_constrained_llm_readiness,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_manifest import (
    R4_PLAYBOOK_CONTRACT_VERSION,
    build_r4_campaign_manifest,
    validate_r4_manifest,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_EXCLUDED_R3_HOLD_OVERRIDE_SCENARIOS,
    R4_PROFILE_ID,
    coverage_summary,
    is_multi_turn,
    is_no_name_phone,
    is_service_prequalification,
    resolve_r4_scenarios,
    scenario_tags,
    validate_r4_scenario_coverage,
)
from app.evaluation.profile_testbot.qualification.qualification_scenario_plan import (
    build_qualification_scenario_reply_plan,
)
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario
from app.workflows.reply_quality.llm_renderer import (
    MODEL_ID,
    PROMPT_VERSION,
    RENDERER_POLICY_VERSION as LLM_RENDERER_POLICY_VERSION,
    TEMPLATE_VERSION as LLM_TEMPLATE_VERSION,
)
from app.workflows.reply_quality.post_render_validator import (
    POLICY_VERSION as VALIDATOR_VERSION,
)
from app.workflows.reply_quality.provenance import LLM_RENDERER, hash_body, hash_plan
from app.workflows.reply_quality.renderer import render_coworker_reply_with_validation
from app.workflows.reply_quality.renderer_requirement import RendererRequirement

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\b(?:\+46|0)\d[\d\s\-]{7,}\d\b")
GMAIL_ID_RE = re.compile(r"\b19[a-f0-9]{14,16}\b", re.I)

FORBIDDEN_SEND_RENDERERS = frozenset(
    {
        "deterministic_structured_v1",
        "hermetic_constrained",
        "blocked_constrained_llm_required",
    }
)


def _redact(value: str) -> str:
    out = EMAIL_RE.sub("[REDACTED_EMAIL]", value or "")
    out = PHONE_RE.sub("[REDACTED_PHONE]", out)
    out = GMAIL_ID_RE.sub(lambda m: f"gm_{m.group(0)[:6]}…", out)
    return out


def _redact_obj(value: Any) -> Any:
    if isinstance(value, str):
        return _redact(value)
    if isinstance(value, dict):
        return {k: _redact_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_obj(v) for v in value]
    return value


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_candidate_package_semantic_hash(semantic_payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(semantic_payload).encode("utf-8")).hexdigest()


def build_candidate_package_semantic_payload(
    *,
    runtime_sha: str,
    manifest_semantic_hash: str,
    profile_id: str,
    profile_hash: str,
    send_candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = []
    for row in sorted(send_candidates, key=lambda r: str(r.get("scenario_id") or "")):
        rows.append(
            {
                "scenario_id": row.get("scenario_id"),
                "plan_hash": row.get("plan_hash"),
                "body_hash": row.get("body_hash"),
                "renderer_type": row.get("renderer_type"),
                "requested_model_id": row.get("requested_model_id"),
                "returned_model_id": row.get("returned_model_id"),
                "prompt_version": row.get("prompt_version"),
                "renderer_policy_version": row.get("renderer_policy_version"),
                "validator_version": row.get("validator_version"),
                "playbook_version": row.get("playbook_version"),
                "provider_outcome": row.get("provider_outcome"),
                "fallback_used": bool((row.get("fallback") or {}).get("used")),
            }
        )
    return {
        "runtime_sha": runtime_sha,
        "manifest_semantic_hash": manifest_semantic_hash,
        "profile_id": profile_id,
        "profile_hash": profile_hash,
        "scenario_rows": rows,
    }


def _no_send_reason(scenario: ProfileScenario) -> str:
    return str(scenario.expected_send_behavior or "no_send")


def _empty_provenance_block(*, reason: str) -> dict[str, Any]:
    return {
        "renderer_requirement": RendererRequirement.CONSTRAINED_LLM_REQUIRED.value,
        "renderer_type": "blocked_constrained_llm_required",
        "llm_used": False,
        "invocation_attempted": False,
        "live_call": False,
        "provider_outcome": reason,
        "requested_model_id": MODEL_ID,
        "returned_model_id": None,
        "model_id": None,
        "prompt_version": None,
        "template_version": LLM_TEMPLATE_VERSION,
        "renderer_policy_version": LLM_RENDERER_POLICY_VERSION,
        "finish_reason": None,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "provider_attempt_count": 0,
        "post_render_validation_passed": False,
        "final_text_validation_passed": False,
        "fallback_used": False,
        "fallback_tier": "none",
        "fallback_reason": reason,
        "plan_hash": None,
        "prompt_payload_hash": None,
        "body_hash": None,
    }


def _generate_send_candidate(
    scenario: ProfileScenario,
    *,
    require_live_llm: bool,
    expected_model: str,
) -> dict[str, Any]:
    blockers: list[str] = []
    base = {
        "scenario_id": scenario.scenario_id,
        "family": scenario.family,
        "language": scenario.input.language if scenario.input else "sv",
        "planned_gmail_send": True,
        "tags": scenario_tags(scenario),
        "multi_turn": is_multi_turn(scenario),
        "no_name_phone": is_no_name_phone(scenario),
        "service_specific_prequalification": is_service_prequalification(scenario),
        "approval_eligibility": True,
        "r3_hold_override_applied": False,
        "external_actions": [],
        "gmail_mutations": 0,
        "validator_version": VALIDATOR_VERSION,
        "playbook_version": R4_PLAYBOOK_CONTRACT_VERSION,
    }

    if not require_live_llm:
        blockers.append("require_live_llm_false")
        return _redact_obj(
            {
                **base,
                "status": "BLOCKED",
                "blockers": blockers,
                "rendered_body": "",
                "fallback": {"used": False, "reason": "require_live_llm_false", "tier": "none"},
                **_empty_provenance_block(reason="require_live_llm_false"),
            }
        )

    plan = build_qualification_scenario_reply_plan(scenario, signature_name="Niklas")
    if plan is None:
        blockers.append("plan_build_failed")
        return _redact_obj(
            {
                **base,
                "status": "BLOCKED",
                "blockers": blockers,
                "rendered_body": "",
                "fallback": {"used": False, "reason": "plan_build_failed", "tier": "none"},
                **_empty_provenance_block(reason="plan_build_failed"),
            }
        )

    prev = os.environ.get("DIGITAL_COWORKER_REPLY_ENABLED")
    os.environ["DIGITAL_COWORKER_REPLY_ENABLED"] = "true"
    try:
        render_result = render_coworker_reply_with_validation(
            plan,
            requirement=RendererRequirement.CONSTRAINED_LLM_REQUIRED,
        )
    finally:
        if prev is None:
            os.environ.pop("DIGITAL_COWORKER_REPLY_ENABLED", None)
        else:
            os.environ["DIGITAL_COWORKER_REPLY_ENABLED"] = prev

    body = render_result.body or ""
    prov = render_result.provenance
    validation = render_result.validation or {}
    llm_meta = dict(validation.get("llm_meta") or {})
    final_validation = validation.get("final_customer_text_validation") or {}
    validation_blockers = list(validation.get("blockers") or [])
    blockers.extend(validation_blockers)

    renderer_type = prov.renderer_type
    llm_used = bool(prov.llm_used)
    invocation_attempted = bool(llm_meta.get("invocation_attempted"))
    live_call = bool(llm_meta.get("live_call"))
    provider_outcome = str(llm_meta.get("provider_outcome") or "unknown")
    requested_model_id = str(llm_meta.get("requested_model_id") or MODEL_ID)
    returned_model_id = llm_meta.get("returned_model_id") or llm_meta.get("returned_model")
    prompt_version = llm_meta.get("prompt_version") or prov.prompt_version
    template_version = llm_meta.get("template_version") or LLM_TEMPLATE_VERSION
    renderer_policy_version = (
        llm_meta.get("renderer_policy_version") or LLM_RENDERER_POLICY_VERSION
    )
    plan_hash = prov.plan_hash or hash_plan(plan.to_dict())
    prompt_payload_hash = llm_meta.get("prompt_payload_hash") or llm_meta.get("payload_hash")
    body_hash = hash_body(body) if body else ""
    post_render_ok = bool(validation.get("passed")) and not validation_blockers
    final_text_ok = bool(final_validation.get("passed"))
    fallback_used = bool(prov.use_fallback) or bool(llm_meta.get("fallback_used"))
    fallback_tier = str(llm_meta.get("fallback_tier") or ("none" if not fallback_used else "unknown"))
    fallback_reason = prov.fallback_reason or llm_meta.get("fallback_reason")

    if renderer_type != LLM_RENDERER:
        blockers.append(f"renderer_type:{renderer_type}")
    if renderer_type in FORBIDDEN_SEND_RENDERERS:
        blockers.append(f"forbidden_renderer:{renderer_type}")
    if not llm_used:
        blockers.append("llm_used_false")
    if not invocation_attempted:
        blockers.append("invocation_not_attempted")
    if not live_call:
        blockers.append("live_call_false")
    if provider_outcome != "success":
        blockers.append(f"provider_outcome:{provider_outcome}")
    if requested_model_id != expected_model:
        blockers.append(f"requested_model_mismatch:{requested_model_id}")
    if not returned_model_id:
        blockers.append("missing_returned_model")
    if prompt_version != PROMPT_VERSION:
        blockers.append(f"prompt_version_mismatch:{prompt_version}")
    if not prompt_version:
        blockers.append("missing_prompt_version")
    if not post_render_ok:
        blockers.append("post_render_validation_failed")
    if not final_text_ok:
        blockers.append("final_text_validation_failed")
    if fallback_used or fallback_tier not in {"none", ""}:
        blockers.append(f"fallback_not_allowed:{fallback_tier}")
    if not plan_hash:
        blockers.append("missing_plan_hash")
    if not body or not body_hash:
        blockers.append("missing_body_hash")
    if body and body_hash != hash_body(body):
        blockers.append("body_hash_mismatch")

    oracle_rows: list[dict[str, Any]] = []
    if body and not blockers:
        try:
            oracle_results = evaluate_coworker_reply_oracles(
                scenario=scenario,
                reply_body=body,
                plan_v2=plan,
                provenance=prov,
            )
            for item in oracle_results:
                row = (
                    item.to_dict()
                    if hasattr(item, "to_dict")
                    else {
                        "name": getattr(item, "name", None),
                        "status": getattr(item, "status", None),
                        "blocker": getattr(item, "blocker", False),
                        "detail": getattr(item, "detail", None),
                    }
                )
                oracle_rows.append(row)
                if getattr(item, "blocker", False) and getattr(item, "status", "") == "fail":
                    blockers.append(f"oracle:{getattr(item, 'name', 'unknown')}")
        except Exception as exc:  # noqa: BLE001
            blockers.append(f"oracle_error:{type(exc).__name__}")

    ok = not blockers
    return _redact_obj(
        {
            **base,
            "status": "PASS" if ok else "BLOCKED",
            "blockers": blockers,
            "renderer_requirement": RendererRequirement.CONSTRAINED_LLM_REQUIRED.value,
            "renderer_type": renderer_type if ok else (renderer_type or "blocked_constrained_llm_required"),
            "llm_used": llm_used and ok,
            "invocation_attempted": invocation_attempted,
            "live_call": live_call,
            "provider_outcome": provider_outcome,
            "requested_model_id": requested_model_id,
            "returned_model_id": returned_model_id,
            "model_id": returned_model_id if ok else None,
            "prompt_version": prompt_version if (ok or prompt_version) else None,
            "template_version": template_version,
            "renderer_policy_version": renderer_policy_version,
            "finish_reason": llm_meta.get("finish_reason"),
            "prompt_tokens": int(llm_meta.get("prompt_tokens") or 0),
            "completion_tokens": int(llm_meta.get("completion_tokens") or 0),
            "total_tokens": int(llm_meta.get("total_tokens") or 0),
            "provider_attempt_count": int(llm_meta.get("provider_attempt_count") or 0),
            "post_render_validation_passed": post_render_ok,
            "final_text_validation_passed": final_text_ok,
            "fallback": {
                "used": fallback_used,
                "tier": fallback_tier,
                "reason": fallback_reason,
            },
            "fallback_used": fallback_used,
            "fallback_tier": fallback_tier,
            "fallback_reason": fallback_reason,
            "plan_hash": plan_hash,
            "prompt_payload_hash": prompt_payload_hash,
            "body_hash": body_hash if ok else None,
            "rendered_body": body if ok else "",
            "selected_questions": list(plan.selected_questions or []),
            "known_facts": list(plan.verified_facts or []),
            "next_step": plan.next_step_statement,
            "playbook_id": plan.playbook_id,
            "oracle_results": oracle_rows,
        }
    )


def _generate_no_send_candidate(scenario: ProfileScenario) -> dict[str, Any]:
    return _redact_obj(
        {
            "scenario_id": scenario.scenario_id,
            "family": scenario.family,
            "language": scenario.input.language if scenario.input else "sv",
            "planned_gmail_send": False,
            "status": "PASS",
            "blockers": [],
            "tags": scenario_tags(scenario),
            "no_send_reason": _no_send_reason(scenario),
            "policy_authorization_expected": scenario.expected_authorization
            or scenario.expected_send_behavior,
            "threat_or_risk_family": scenario.family in {"spam", "invoice"}
            or scenario.risk_class in {"critical", "high"},
            "external_actions": [],
            "gmail_mutations": 0,
            "llm_calls": 0,
            "r3_hold_override_applied": False,
            "r3_hold_override_excluded": scenario.scenario_id
            in R4_EXCLUDED_R3_HOLD_OVERRIDE_SCENARIOS,
        }
    )


def generate_r4_candidates(
    *,
    runtime_sha: str,
    profile_id: str = R4_PROFILE_ID,
    seed: int = 42,
    require_live_llm: bool = True,
    expected_model: str = MODEL_ID,
) -> dict[str, Any]:
    """Generate R4 candidates. require_live_llm defaults True and must stay True for PASS."""
    blocking_failures: list[str] = []
    if not require_live_llm:
        blocking_failures.append("require_live_llm_must_be_true")

    readiness = run_r4_constrained_llm_readiness(
        expected_model=expected_model,
        gmail_mutation_enabled=False,
        production_activation=False,
        automatic_gmail=False,
    )
    if require_live_llm and not readiness.get("constrained_llm_ready"):
        blocking_failures.extend(
            f"llm_readiness:{b}" for b in (readiness.get("blockers") or [])
        )

    manifest = build_r4_campaign_manifest(
        runtime_sha=runtime_sha, profile_id=profile_id, seed=seed
    )
    manifest_blockers = validate_r4_manifest(manifest)
    profile = load_customer_profile(profile_id)
    scenarios = resolve_r4_scenarios(profile, seed=seed)
    coverage_blockers = validate_r4_scenario_coverage(scenarios)
    blocking_failures.extend(manifest_blockers)
    blocking_failures.extend(coverage_blockers)

    send_candidates: list[dict[str, Any]] = []
    no_send_candidates: list[dict[str, Any]] = []
    provider_call_count = 0

    for scenario in scenarios:
        if scenario.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND:
            row = _generate_send_candidate(
                scenario,
                require_live_llm=require_live_llm,
                expected_model=expected_model,
            )
            send_candidates.append(row)
            if row.get("invocation_attempted") and row.get("live_call"):
                provider_call_count += 1
            blocking_failures.extend(
                f"{scenario.scenario_id}:{b}" for b in (row.get("blockers") or [])
            )
        elif scenario.expected_send_behavior in NO_SEND_BEHAVIORS:
            row = _generate_no_send_candidate(scenario)
            no_send_candidates.append(row)
        else:
            blocking_failures.append(
                f"{scenario.scenario_id}:unexpected_send_behavior:{scenario.expected_send_behavior}"
            )

    constrained_ok = [
        c
        for c in send_candidates
        if c.get("status") == "PASS"
        and c.get("renderer_type") == LLM_RENDERER
        and c.get("llm_used") is True
    ]
    deterministic_count = sum(
        1
        for c in send_candidates
        if c.get("renderer_type") == "deterministic_structured_v1"
    )
    fallback_count = sum(1 for c in send_candidates if c.get("fallback_used"))
    missing_model = sum(1 for c in send_candidates if not c.get("returned_model_id"))
    missing_prompt = sum(1 for c in send_candidates if not c.get("prompt_version"))
    provider_failures = sum(
        1
        for c in send_candidates
        if c.get("provider_outcome")
        in {"failed", "parse_failed", "blocked_llm_render_disabled", "skipped", "pending"}
    )
    parse_failures = sum(
        1 for c in send_candidates if c.get("provider_outcome") == "parse_failed"
    )
    post_render_failures = sum(
        1 for c in send_candidates if not c.get("post_render_validation_passed")
    )
    final_text_failures = sum(
        1 for c in send_candidates if not c.get("final_text_validation_passed")
    )
    oracle_blocking = sum(
        1
        for c in send_candidates
        for b in (c.get("blockers") or [])
        if str(b).startswith("oracle:")
    )
    body_hash_ok = sum(1 for c in send_candidates if c.get("body_hash"))
    plan_hash_ok = sum(1 for c in send_candidates if c.get("plan_hash"))

    if len(send_candidates) != 20:
        blocking_failures.append(f"send_candidates {len(send_candidates)} != 20")
    if len(no_send_candidates) != 16:
        blocking_failures.append(f"no_send_candidates {len(no_send_candidates)} != 16")
    if len(constrained_ok) != 20:
        blocking_failures.append(
            f"constrained_llm_candidate_count {len(constrained_ok)} != 20"
        )
    if deterministic_count:
        blocking_failures.append(f"deterministic_renderer_count={deterministic_count}")
    if fallback_count:
        blocking_failures.append(f"fallback_count={fallback_count}")
    if missing_model:
        blocking_failures.append(f"missing_model_id_count={missing_model}")
    if missing_prompt:
        blocking_failures.append(f"missing_prompt_version_count={missing_prompt}")
    if provider_failures:
        blocking_failures.append(f"provider_failures={provider_failures}")
    if parse_failures:
        blocking_failures.append(f"parse_failures={parse_failures}")
    if post_render_failures:
        blocking_failures.append(f"post_render_failures={post_render_failures}")
    if final_text_failures:
        blocking_failures.append(f"final_text_failures={final_text_failures}")
    if oracle_blocking:
        blocking_failures.append(f"oracle_blocking_failures={oracle_blocking}")
    if body_hash_ok != 20:
        blocking_failures.append(f"body_hashes {body_hash_ok} != 20")
    if plan_hash_ok != 20:
        blocking_failures.append(f"plan_hashes {plan_hash_ok} != 20")
    if provider_call_count > 20:
        blocking_failures.append(f"provider_calls {provider_call_count} > 20")

    secrets_exposed = False
    blob = json.dumps(send_candidates + no_send_candidates)
    if any(
        token in blob
        for token in ("refresh_token", "client_secret", "ADMIN_API_KEY", "sk-")
    ):
        secrets_exposed = True
        blocking_failures.append("secrets_exposed")

    provenance_audit_pass = (
        len(constrained_ok) == 20
        and deterministic_count == 0
        and fallback_count == 0
        and missing_model == 0
        and missing_prompt == 0
        and provider_failures == 0
        and not secrets_exposed
    )
    if not provenance_audit_pass:
        blocking_failures.append("provenance_audit_fail")

    semantic_payload = build_candidate_package_semantic_payload(
        runtime_sha=runtime_sha,
        manifest_semantic_hash=str(manifest.get("manifest_semantic_hash") or ""),
        profile_id=profile_id,
        profile_hash=str(manifest.get("profile_hash") or ""),
        send_candidates=send_candidates,
    )
    candidate_package_semantic_hash = compute_candidate_package_semantic_hash(
        semantic_payload
    )

    overall = "PASS" if not blocking_failures else "BLOCKED"
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "runtime_sha": runtime_sha,
        "profile_id": profile_id,
        "overall_status": overall,
        "blocking_failures": blocking_failures,
        "secrets_exposed": secrets_exposed,
        "gmail_sends": 0,
        "gmail_drafts": 0,
        "gmail_triggers": 0,
        "external_writes": 0,
        "require_live_llm": require_live_llm,
        "expected_model": expected_model,
        "llm_readiness": readiness,
        "manifest_semantic_hash": manifest.get("manifest_semantic_hash"),
        "candidate_package_semantic_hash": candidate_package_semantic_hash,
        "candidate_package_semantic_payload": semantic_payload,
        "provenance_audit_pass": provenance_audit_pass and overall == "PASS",
        "constrained_llm_candidate_count": len(constrained_ok),
        "deterministic_renderer_count": deterministic_count,
        "fallback_count": fallback_count,
        "missing_model_id_count": missing_model,
        "missing_prompt_version_count": missing_prompt,
        "provider_failures": provider_failures,
        "parse_failures": parse_failures,
        "post_render_failures": post_render_failures,
        "final_text_failures": final_text_failures,
        "oracle_blocking_failures": oracle_blocking,
        "provider_call_count": provider_call_count,
        "manifest": {k: v for k, v in manifest.items() if k != "semantic_payload"},
        "coverage": coverage_summary(scenarios),
        "send_candidates": send_candidates,
        "no_send_candidates": no_send_candidates,
        "send_candidate_count": len(send_candidates),
        "no_send_candidate_count": len(no_send_candidates),
        "r3_hold_override_generalized": False,
        "human_review_required": True,
        "human_review_complete": False,
        "human_review_authorized": overall == "PASS" and provenance_audit_pass,
        "automatic_gmail": False,
        "production_activation": False,
    }


def write_r4_candidate_package(result: dict[str, Any], status_dir: Path) -> dict[str, Path]:
    status_dir.mkdir(parents=True, exist_ok=True)
    sha = str(result.get("runtime_sha") or "unknown")[:7]
    json_path = status_dir / f"digital-coworker-r4-candidates-{sha}.json"
    md_path = status_dir / f"digital-coworker-r4-candidates-{sha}.md"
    # Do not persist full semantic payload duplicate keys if huge; keep hash.
    out = dict(result)
    out.pop("candidate_package_semantic_payload", None)
    json_path.write_text(
        json.dumps(_redact_obj(out), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# R4 candidate package ({sha})",
        "",
        f"- overall_status: **{result.get('overall_status')}**",
        f"- runtime_sha: `{result.get('runtime_sha')}`",
        f"- require_live_llm: **{result.get('require_live_llm')}**",
        f"- provenance_audit_pass: **{result.get('provenance_audit_pass')}**",
        f"- constrained_llm_candidate_count: **{result.get('constrained_llm_candidate_count')}**",
        f"- deterministic_renderer_count: **{result.get('deterministic_renderer_count')}**",
        f"- fallback_count: **{result.get('fallback_count')}**",
        f"- manifest_semantic_hash: `{result.get('manifest_semantic_hash')}`",
        f"- candidate_package_semantic_hash: `{result.get('candidate_package_semantic_hash')}`",
        f"- send_candidates: **{result.get('send_candidate_count')}**",
        f"- no_send_candidates: **{result.get('no_send_candidate_count')}**",
        f"- gmail_sends: **0**",
        f"- gmail_drafts: **0**",
        f"- blocking_failures: `{result.get('blocking_failures')}`",
        "",
        "## Send candidates",
        "",
    ]
    for row in result.get("send_candidates") or []:
        lines.append(
            f"- `{row.get('scenario_id')}` status={row.get('status')} "
            f"renderer=`{row.get('renderer_type')}` "
            f"model=`{row.get('returned_model_id')}` "
            f"body_hash=`{(row.get('body_hash') or '')[:16]}…` "
            f"fallback={row.get('fallback_used')}"
        )
    lines.extend(["", "## No-send candidates", ""])
    for row in result.get("no_send_candidates") or []:
        lines.append(
            f"- `{row.get('scenario_id')}` reason=`{row.get('no_send_reason')}`"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "md": md_path}
