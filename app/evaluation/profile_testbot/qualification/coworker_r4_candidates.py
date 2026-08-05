"""Write-free R4 candidate generation (no Gmail / external writes)."""

from __future__ import annotations

import json
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
from app.evaluation.profile_testbot.qualification.coworker_r4_manifest import (
    build_r4_campaign_manifest,
    validate_r4_manifest,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_EXCLUDED_R3_HOLD_OVERRIDE_SCENARIOS,
    R4_PROFILE_ID,
    R4_SEND_SCENARIO_IDS,
    coverage_summary,
    is_multi_turn,
    is_no_name_phone,
    is_service_prequalification,
    resolve_r4_scenarios,
    scenario_tags,
    validate_r4_scenario_coverage,
)
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import (
    _render_scenario_reply,
)
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario
from app.workflows.reply_quality.provenance import hash_body

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\b(?:\+46|0)\d[\d\s\-]{7,}\d\b")
GMAIL_ID_RE = re.compile(r"\b19[a-f0-9]{14,16}\b", re.I)


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


def _no_send_reason(scenario: ProfileScenario) -> str:
    return str(scenario.expected_send_behavior or "no_send")


def _generate_send_candidate(scenario: ProfileScenario) -> dict[str, Any]:
    from app.evaluation.profile_testbot.qualification.human_review_coworker import (  # noqa: F401
        score_reply_for_review,
    )
    from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
    from app.workflows.reply_quality.thread_context import ThreadReplyContext

    body, plan_dict, provenance = _render_scenario_reply(scenario)
    blockers: list[str] = []
    if not body or not provenance:
        blockers.append("send_candidate_missing_body_or_provenance")
        return {
            "scenario_id": scenario.scenario_id,
            "family": scenario.family,
            "planned_gmail_send": True,
            "status": "BLOCKED",
            "blockers": blockers,
            "tags": scenario_tags(scenario),
        }

    prov = provenance.to_dict() if hasattr(provenance, "to_dict") else dict(provenance)
    body_hash = prov.get("body_hash") or hash_body(body)
    plan_hash = prov.get("plan_hash")
    if not body_hash:
        blockers.append("missing_body_hash")
    if not plan_hash:
        blockers.append("missing_plan_hash")
    if prov.get("use_fallback") and not prov.get("fallback_reason"):
        blockers.append("fallback_without_reason")

    plan_v2 = None
    if isinstance(plan_dict, dict) and plan_dict.get("response_objective"):
        thread_raw = plan_dict.get("thread_context") or {}
        plan_v2 = CustomerReplyPlanV2(
            response_objective=plan_dict["response_objective"],
            acknowledgement_mode=plan_dict["acknowledgement_mode"],
            service_family=plan_dict["service_family"],
            business_intent=plan_dict["business_intent"],
            verified_facts=tuple(plan_dict.get("verified_facts") or []),
            facts_not_allowed_to_repeat=tuple(plan_dict.get("facts_not_allowed_to_repeat") or []),
            selected_questions=tuple(plan_dict.get("selected_questions") or []),
            selected_question_labels=tuple(plan_dict.get("selected_question_labels") or []),
            next_step_statement=plan_dict["next_step_statement"],
            commitment_constraints=tuple(plan_dict.get("commitment_constraints") or []),
            tone_profile=plan_dict["tone_profile"],
            language=plan_dict["language"],
            greeting=plan_dict["greeting"],
            signature_name=plan_dict["signature_name"],
            salutation_strategy=plan_dict["salutation_strategy"],
            closing_strategy=plan_dict["closing_strategy"],
            thread_context=ThreadReplyContext(
                thread_state=thread_raw.get("thread_state", "new_thread"),
                is_first_contact=bool(thread_raw.get("is_first_contact", True)),
                is_continuation=bool(thread_raw.get("is_continuation", False)),
                prior_operator_reply=bool(thread_raw.get("prior_operator_reply", False)),
                prior_safe_ack=bool(thread_raw.get("prior_safe_ack", False)),
                supplied_facts=tuple(thread_raw.get("supplied_facts") or ()),
                summary=thread_raw.get("summary", ""),
                policy_version=thread_raw.get("policy_version", "thread_context_v1"),
            ),
            rendering_constraints=tuple(plan_dict.get("rendering_constraints") or ()),
            fallback_reason=plan_dict.get("fallback_reason"),
            evidence=tuple(plan_dict.get("evidence") or ()),
            playbook_id=plan_dict["playbook_id"],
            policy_version=plan_dict["policy_version"],
            acknowledgement_statement=plan_dict.get("acknowledgement_statement") or "",
            question_surface_labels=tuple(plan_dict.get("question_surface_labels") or []),
            location_phrase=plan_dict.get("location_phrase"),
            case_reference_phrase=plan_dict.get("case_reference_phrase"),
            language_decision_evidence=tuple(
                plan_dict.get("language_decision_evidence") or []
            ),
            scenario_family=plan_dict.get("scenario_family"),
            attachment_state=plan_dict.get("attachment_state"),
        )

    oracle_rows: list[dict[str, Any]] = []
    try:
        oracle_results = evaluate_coworker_reply_oracles(
            scenario=scenario,
            reply_body=body,
            plan_v2=plan_v2,
            provenance=provenance if hasattr(provenance, "renderer_type") else None,
        )
        for item in oracle_results:
            row = item.to_dict() if hasattr(item, "to_dict") else {
                "name": getattr(item, "name", None),
                "status": getattr(item, "status", None),
                "blocker": getattr(item, "blocker", False),
                "detail": getattr(item, "detail", None),
            }
            oracle_rows.append(row)
            if getattr(item, "blocker", False) and getattr(item, "status", "") == "fail":
                blockers.append(f"oracle:{getattr(item, 'name', 'unknown')}")
    except Exception as exc:  # noqa: BLE001
        blockers.append(f"oracle_error:{type(exc).__name__}")

    return _redact_obj(
        {
            "scenario_id": scenario.scenario_id,
            "family": scenario.family,
            "language": scenario.input.language if scenario.input else "sv",
            "planned_gmail_send": True,
            "status": "PASS" if not blockers else "BLOCKED",
            "blockers": blockers,
            "tags": scenario_tags(scenario),
            "multi_turn": is_multi_turn(scenario),
            "no_name_phone": is_no_name_phone(scenario),
            "service_specific_prequalification": is_service_prequalification(scenario),
            "renderer_type": prov.get("renderer_type"),
            "model_id": prov.get("model_id"),
            "prompt_version": prov.get("prompt_version"),
            "plan_hash": plan_hash,
            "body_hash": body_hash,
            "rendered_body": body,
            "fallback": {
                "used": bool(prov.get("use_fallback")),
                "reason": prov.get("fallback_reason"),
            },
            "selected_questions": list((plan_dict or {}).get("selected_questions") or []),
            "known_facts": list((plan_dict or {}).get("verified_facts") or []),
            "next_step": (plan_dict or {}).get("next_step_statement"),
            "playbook_id": (plan_dict or {}).get("playbook_id"),
            "oracle_results": oracle_rows,
            "approval_eligibility": True,
            "r3_hold_override_applied": False,
            "external_actions": [],
            "gmail_mutations": 0,
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
) -> dict[str, Any]:
    manifest = build_r4_campaign_manifest(
        runtime_sha=runtime_sha, profile_id=profile_id, seed=seed
    )
    manifest_blockers = validate_r4_manifest(manifest)
    profile = load_customer_profile(profile_id)
    scenarios = resolve_r4_scenarios(profile, seed=seed)
    coverage_blockers = validate_r4_scenario_coverage(scenarios)

    send_candidates: list[dict[str, Any]] = []
    no_send_candidates: list[dict[str, Any]] = []
    blocking_failures: list[str] = []
    blocking_failures.extend(manifest_blockers)
    blocking_failures.extend(coverage_blockers)

    for scenario in scenarios:
        if scenario.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND:
            row = _generate_send_candidate(scenario)
            send_candidates.append(row)
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

    if len(send_candidates) > 20:
        blocking_failures.append(f"send_candidates {len(send_candidates)} > 20")
    if len(no_send_candidates) < 16:
        blocking_failures.append(f"no_send_candidates {len(no_send_candidates)} < 16")

    missing_hashes = [
        c["scenario_id"]
        for c in send_candidates
        if not c.get("body_hash")
    ]
    if missing_hashes:
        blocking_failures.append(f"send_candidates_missing_body_hash:{missing_hashes}")

    fallback_count = sum(
        1 for c in send_candidates if (c.get("fallback") or {}).get("used")
    )
    # Excessive fallback blocks qualification; hermetic structured path is expected for many.
    # Only block when fallback lacks reason or every send fell to empty/no_reply.
    empty_bodies = [c["scenario_id"] for c in send_candidates if not (c.get("rendered_body") or "").strip()]
    if empty_bodies:
        blocking_failures.append(f"empty_send_bodies:{empty_bodies}")

    secrets_exposed = False
    blob = json.dumps(send_candidates + no_send_candidates)
    if any(token in blob for token in ("refresh_token", "client_secret", "ADMIN_API_KEY")):
        secrets_exposed = True
        blocking_failures.append("secrets_exposed")

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
        "external_writes": 0,
        "manifest_semantic_hash": manifest.get("manifest_semantic_hash"),
        "manifest": {
            k: v for k, v in manifest.items() if k != "semantic_payload"
        },
        "coverage": coverage_summary(scenarios),
        "send_candidates": send_candidates,
        "no_send_candidates": no_send_candidates,
        "fallback_count": fallback_count,
        "send_candidate_count": len(send_candidates),
        "no_send_candidate_count": len(no_send_candidates),
        "r3_hold_override_generalized": False,
        "human_review_required": True,
        "human_review_complete": False,
    }


def write_r4_candidate_package(result: dict[str, Any], status_dir: Path) -> dict[str, Path]:
    status_dir.mkdir(parents=True, exist_ok=True)
    sha = str(result.get("runtime_sha") or "unknown")[:7]
    json_path = status_dir / f"digital-coworker-r4-candidates-{sha}.json"
    md_path = status_dir / f"digital-coworker-r4-candidates-{sha}.md"
    json_path.write_text(
        json.dumps(_redact_obj(result), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# R4 candidate package ({sha})",
        "",
        f"- overall_status: **{result.get('overall_status')}**",
        f"- runtime_sha: `{result.get('runtime_sha')}`",
        f"- manifest_semantic_hash: `{result.get('manifest_semantic_hash')}`",
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
            f"body_hash=`{(row.get('body_hash') or '')[:16]}…` "
            f"fallback={((row.get('fallback') or {}).get('used'))}"
        )
    lines.extend(["", "## No-send candidates", ""])
    for row in result.get("no_send_candidates") or []:
        lines.append(
            f"- `{row.get('scenario_id')}` reason=`{row.get('no_send_reason')}`"
        )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": json_path, "md": md_path}
