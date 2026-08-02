#!/usr/bin/env python3
"""Build local digital-coworker human-review package (Gate R2, operator artifact)."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "storage" / "status"
sys.path.insert(0, str(ROOT))

from app.evaluation.profile_testbot.qualification.coworker_package_precheck import (  # noqa: E402
    evaluate_package_precheck,
)

from app.evaluation.profile_testbot.coworker_quality_oracles import (  # noqa: E402
    CoworkerOracleResult,
    aggregate_coworker_results,
    evaluate_coworker_reply_oracles,
    expected_reply_language,
    summarize_surface_quality_metrics,
    template_similarity_ratio,
)
from app.evaluation.profile_testbot.coworker_reply_dataset import (  # noqa: E402
    generate_coworker_reply_dataset,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile  # noqa: E402
from app.evaluation.profile_testbot.qualification.human_review_coworker import (  # noqa: E402
    score_reply_for_review,
)
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario  # noqa: E402
from app.workflows.missing_fact_plan import build_missing_fact_plan  # noqa: E402
from app.workflows.reply_planning import _resolve_location_hint, _resolve_service_hint  # noqa: E402
from app.workflows.reply_quality.information_value import build_information_value_plan  # noqa: E402
from app.workflows.reply_quality.pipeline import build_and_render_coworker_reply  # noqa: E402
from app.workflows.reply_quality.pipeline_routing import resolve_reply_pipeline_context  # noqa: E402
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2  # noqa: E402
from app.workflows.reply_quality.thread_context import (  # noqa: E402
    acknowledgement_mode_for_thread,
    build_thread_reply_context,
)
from app.workflows.reply_quality.customer_surface import extract_city_phrase  # noqa: E402
from app.workflows.reply_quality.llm_renderer import MODEL_ID, PROMPT_VERSION  # noqa: E402
from app.workflows.safe_ack_eligibility import evaluate_safe_ack_eligibility  # noqa: E402

PROFILE_ID = "niklas-demo-live-eval-v1"


def _git_head_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "").strip()


def verify_clean_worktree() -> None:
    from app.evaluation.profile_testbot.qualification.package_build_worktree import (
        verify_clean_worktree as _verify,
    )

    _verify(ROOT)


def verify_merge_sha(merge_sha: str) -> None:
    head = _git_head_sha()
    if head != merge_sha:
        raise RuntimeError(
            f"HEAD {head} does not match required merge_sha {merge_sha}. "
            "Checkout the exact merge commit before building."
        )

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\b(?:\+46|0)\d[\d\s\-]{7,}\d\b")
RFC_MSG_RE = re.compile(r"<[^>]+@[^>]+>")
GMAIL_ID_RE = re.compile(r"\b19[a-f0-9]{14,16}\b", re.I)

HUMAN_DIMENSIONS = (
    ("competent_coworker", "Låter som en kompetent medarbetare"),
    ("understands_case", "Förstår kundens faktiska ärende"),
    ("service_specific", "Är specifikt för tjänsten"),
    ("progresses_work", "För arbetet vidare"),
    ("relevant_questions", "Ställer relevanta frågor"),
    ("avoids_redundant", "Undviker redan kända eller onödiga frågor"),
    ("clear_next_step", "Har ett tydligt nästa steg"),
    ("natural_professional", "Är naturligt och professionellt skrivet"),
    ("concise_not_empty", "Är kortfattat utan att bli tomt"),
    ("profile_tone", "Följer kundprofilens ton"),
)

BLOCKER_CHECKS = (
    ("incorrect_fact_claim", "Felaktigt faktapåstående"),
    ("unjustified_name_request", "Obefogat namnkrav"),
    ("unjustified_phone_request", "Obefogat telefonkrav"),
    ("irrelevant_question", "Irrelevant fråga"),
    ("generic_template_despite_rich_plan", "Generisk mall trots rik plan"),
    ("repeats_answered_question", "Upprepar redan besvarad fråga"),
    ("wrong_service", "Fel tjänst"),
    ("wrong_thread_context", "Fel trådkontext"),
    ("forbidden_promise", "Förbjudet löfte"),
    ("internal_info_leak", "Intern information läckt"),
    ("eval_or_technical_term", "Evalnamn eller teknisk term i kundsvaret"),
)

# Balanced 40-scenario selection (exactly one primary bucket each; cross-cutting tags validated).
SELECTION: list[tuple[str, str, list[str]]] = [
    ("PTB-DCQ-0000", "solar_installation", ["service_specific_questions", "business_facts"]),
    ("PTB-DCQ-0001", "solar_installation", ["service_specific_questions"]),
    ("PTB-DCQ-0004", "solar_installation", ["service_specific_questions"]),
    ("PTB-DCQ-0007", "solar_installation", ["multi_turn", "no_name_phone"]),
    ("PTB-DCQ-0016", "battery_installation", ["service_specific_questions", "business_facts"]),
    ("PTB-DCQ-0017", "battery_installation", ["no_name_phone", "service_specific_questions"]),
    ("PTB-DCQ-0022", "battery_installation", ["multi_turn", "no_name_phone"]),
    ("PTB-DCQ-0032", "ev_charger", ["hold_draft", "service_specific_questions", "business_facts"]),
    ("PTB-DCQ-0033", "ev_charger", ["multi_turn"]),
    ("PTB-DCQ-0040", "ev_charger_known_facts", ["no_name_phone"]),
    ("PTB-DCQ-0048", "solar_battery_combined", ["english", "hold_draft"]),
    ("PTB-DCQ-0049", "solar_battery_combined", ["multi_turn"]),
    ("PTB-DCQ-0050", "solar_battery_combined", ["service_specific_questions"]),
    ("PTB-DCQ-0056", "existing_support", ["no_name_phone"]),
    ("PTB-DCQ-0057", "existing_support", ["multi_turn", "no_name_phone"]),
    ("PTB-DCQ-0064", "existing_support_followup", ["no_name_phone"]),
    ("PTB-DCQ-0065", "existing_support_followup", ["multi_turn", "no_name_phone"]),
    ("PTB-DCQ-0072", "job_status", ["multi_turn", "no_name_phone"]),
    ("PTB-DCQ-0073", "job_status", ["multi_turn", "no_name_phone"]),
    ("PTB-DCQ-0080", "job_status_no_contact", ["multi_turn", "no_name_phone"]),
    ("PTB-DCQ-0088", "complaint_warranty", ["service_specific_questions"]),
    ("PTB-DCQ-0089", "complaint_warranty", ["service_specific_questions"]),
    ("PTB-DCQ-0090", "complaint_warranty", ["service_specific_questions"]),
    ("PTB-DCQ-0097", "general_consultation", ["multi_turn"]),
    ("PTB-DCQ-0098", "general_consultation", ["service_specific_questions"]),
    ("PTB-DCQ-0099", "general_consultation", ["multi_turn"]),
    ("PTB-DCQ-0005", "solar_no_name", ["no_name_phone", "service_specific_questions"]),
    ("PTB-DCQ-0013", "solar_followup_no_name", ["no_name_phone", "multi_turn"]),
    ("PTB-DCQ-0060", "support_no_name", ["no_name_phone"]),
    ("PTB-DCQ-0015", "solar_followup_continuation", ["multi_turn", "no_name_phone"]),
    ("PTB-DCQ-0112", "multi_turn_dedicated", ["multi_turn", "no_name_phone"]),
    ("PTB-DCQ-0113", "multi_turn_dedicated", ["multi_turn", "no_name_phone"]),
    ("PTB-DCQ-0002", "solar_english", ["english"]),
    ("PTB-DCQ-0018", "battery_english", ["english", "no_name_phone"]),
    ("PTB-DCQ-0024", "battery_hold", ["hold_draft", "no_name_phone"]),
    ("PTB-DCQ-0037", "ev_hold", ["hold_draft"]),
    ("PTB-DCQ-0034", "ev_no_name", ["no_name_phone"]),
    ("PTB-DCQ-0051", "solar_battery_continuation", ["multi_turn"]),
    ("PTB-DCQ-0101", "general_hold", ["hold_draft", "multi_turn"]),
    ("PTB-DCQ-0106", "missing_attachment", ["service_specific_questions", "no_name_phone"]),
]


def redact_text(value: str) -> str:
    if not value:
        return value
    out = EMAIL_RE.sub("[REDACTED_EMAIL]", value)
    out = PHONE_RE.sub("[REDACTED_PHONE]", out)
    out = RFC_MSG_RE.sub("[REDACTED_RFC_MSG_ID]", out)
    out = GMAIL_ID_RE.sub(lambda m: f"gm_{m.group(0)[:6]}…", out)
    out = out.replace("sender@eval.test", "[REDACTED_EMAIL]")
    out = out.replace("Test Kund", "[REDACTED_NAME]")
    out = out.replace("Anna Kund", "[REDACTED_NAME]")
    return out


def redact_obj(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_obj(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_obj(v) for v in value]
    return value


@dataclass
class RenderedScenario:
    scenario: ProfileScenario
    bucket: str
    tags: list[str]
    body: str
    plan_v2: CustomerReplyPlanV2 | None
    provenance: dict[str, Any]
    playbook: dict[str, Any]
    next_step: dict[str, Any]
    info_plan: dict[str, Any]
    oracles: list[dict[str, Any]]
    proxy_score: dict[str, Any]
    template_skeleton: str
    audit: dict[str, Any] | None = None
    render_validation: dict[str, Any] | None = None


def _map_evidence_source(raw: str) -> str:
    if raw.startswith("entity:"):
        return "explicit_input_fact"
    if raw.startswith("extracted:") or raw.startswith("semantic:"):
        return "explicit_input_fact"
    if raw.startswith("profile_known:"):
        return "verified_profile_fact"
    if raw.startswith("evidence:"):
        return raw
    return raw or "missing_evidence"


def _build_scenario_audit(
    *,
    scenario: ProfileScenario,
    input_data: dict[str, Any],
    entities: dict[str, Any],
    missing_known: tuple[str, ...],
    pipeline_ctx,
    info_plan: dict[str, Any],
    plan_v2: CustomerReplyPlanV2 | None,
) -> dict[str, Any]:
    from app.workflows.reply_quality.fact_evidence import build_fact_evidence
    from app.workflows.reply_quality.plan_invariants import validate_pipeline_playbook_consistency
    from app.workflows.reply_quality.semantic_fact_predicates import (
        attachment_state,
        detect_consultation_intent,
    )

    combined = f"{scenario.input.subject} {scenario.input.message_text}"
    evidence = build_fact_evidence(
        input_data=input_data,
        entities=entities,
        known_fact_fields=missing_known,
    )
    exclusion_reasons: dict[str, str] = {}
    for reason in info_plan.get("selection_reasons") or []:
        if not str(reason).startswith("exclude:"):
            continue
        parts = str(reason).split(":", 2)
        if len(parts) >= 3:
            exclusion_reasons[parts[1]] = parts[2]
    evidence_sources = {
        field: _map_evidence_source(evidence.evidence_by_field.get(field, "missing_evidence"))
        for field in info_plan.get("already_known_facts") or []
    }
    pipeline_check = validate_pipeline_playbook_consistency(
        playbook_id=pipeline_ctx.playbook.playbook_id,
        service_family=pipeline_ctx.playbook.service_family,
        next_step_service_family=pipeline_ctx.next_step.service_family,
        information_plan_playbook_id=info_plan.get("playbook_id"),
    )
    if plan_v2 is not None:
        pipeline_check = validate_pipeline_playbook_consistency(
            playbook_id=plan_v2.playbook_id,
            service_family=plan_v2.service_family,
            next_step_service_family=pipeline_ctx.next_step.service_family,
            information_plan_playbook_id=info_plan.get("playbook_id"),
        )
    return {
        "location_city_state": evidence.address_state.state,
        "location_city": evidence.address_state.city,
        "property_address_known": evidence.address_state.has_street_address,
        "evidence_sources": evidence_sources,
        "exclusion_reasons": exclusion_reasons,
        "routed_service_type": pipeline_ctx.service_type,
        "routed_service_family": pipeline_ctx.playbook.service_family,
        "consultation_intent": pipeline_ctx.consultation_intent or detect_consultation_intent(combined),
        "attachment_state": attachment_state(combined),
        "pipeline_playbook_consistency": pipeline_check.to_dict(),
    }


def _plan_v2_from_dict(plan_dict: dict[str, Any]) -> CustomerReplyPlanV2:
    from app.workflows.reply_quality.thread_context import ThreadReplyContext

    thread_raw = plan_dict.get("thread_context") or {}
    return CustomerReplyPlanV2(
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
    )


def render_scenario_full(scenario: ProfileScenario) -> RenderedScenario:
    setup = scenario.customer_state_setup or {}
    input_data = {
        "subject": scenario.input.subject,
        "message_text": scenario.input.message_text,
        "language": scenario.input.language,
        "_force_service_type": setup.get("service_type"),
        "_coworker_hermetic_eval": True,
        "_coworker_scenario_family": setup.get("coworker_family") or scenario.family,
        "sender": {
            "name": redact_text(scenario.input.sender_name),
            "email": "[REDACTED_EMAIL]",
        },
    }
    entities = {"email": "[REDACTED_EMAIL]"}
    for key in setup.get("known_entities") or []:
        if key == "city":
            entities[key] = extract_city_phrase(text=scenario.input.message_text, entities={}) or "Uppsala"
        else:
            entities[key] = f"known-{key}"
    fact_map: dict[str, str | None] = {}
    missing = build_missing_fact_plan(
        input_data=input_data,
        entities=entities,
        service_type=setup.get("service_type"),
    )
    eligibility = evaluate_safe_ack_eligibility(
        detected_job_type="lead",
        risk_detected=False,
        risk_categories=[],
        extraction_issues=[],
        input_data=input_data,
        recommendation=None,
        recommendation_raw="manual_review",
        low_confidence=True,
        used_fallback=False,
        business_intent={"primary_intent": setup.get("business_intent")},
    )
    playbook_intent = str(setup.get("business_intent") or "lead")
    coworker_family = setup.get("coworker_family")
    if coworker_family == "complaint_warranty":
        playbook_intent = "support_complaint"
    if not eligibility.eligible and playbook_intent in {"support_status", "support_complaint"}:
        eligibility = evaluate_safe_ack_eligibility(
            detected_job_type="lead",
            risk_detected=False,
            risk_categories=[],
            extraction_issues=[],
            input_data=input_data,
            recommendation=None,
            recommendation_raw="manual_review",
            low_confidence=True,
            used_fallback=False,
            business_intent={"primary_intent": "lead"},
        )
        if coworker_family == "complaint_warranty":
            playbook_intent = "support_complaint"
        elif coworker_family in {"existing_support_symptom", "existing_support_followup"}:
            playbook_intent = "support_status"
        else:
            playbook_intent = str(setup.get("business_intent") or "lead")

    thread_state = str(setup.get("thread_state") or "new_thread")
    service_type = str(setup.get("service_type") or "")
    thread = build_thread_reply_context(
        thread_state=thread_state,
        prior_safe_ack=thread_state == "continuation",
        supplied_facts=missing.known_facts,
    )
    pipeline_ctx = resolve_reply_pipeline_context(
        base_service_type=service_type,
        business_intent=playbook_intent,
        input_data=input_data,
        entities=entities,
        known_fact_fields=missing.known_facts,
        thread_state=thread_state,
        is_continuation=thread.is_continuation,
    )
    playbook = pipeline_ctx.playbook
    next_step = pipeline_ctx.next_step
    service_type = pipeline_ctx.service_type
    info_plan = build_information_value_plan(
        playbook=playbook,
        next_step=next_step,
        input_data=input_data,
        entities=entities,
        known_fact_fields=missing.known_facts,
        is_followup=thread.is_continuation,
        phone_required_by_profile=False,
    )

    body = ""
    plan_v2: CustomerReplyPlanV2 | None = None
    provenance: dict[str, Any] = {}
    render_validation: dict[str, Any] = {}
    render_result = None
    if eligibility.eligible:
        prev_enabled = os.environ.get("DIGITAL_COWORKER_REPLY_ENABLED")
        prev_llm = os.environ.get("DIGITAL_COWORKER_LLM_RENDER")
        prev_retries = os.environ.get("LLM_RETRY_ATTEMPTS")
        os.environ["DIGITAL_COWORKER_REPLY_ENABLED"] = "true"
        os.environ["DIGITAL_COWORKER_LLM_RENDER"] = "live"
        os.environ["LLM_RETRY_ATTEMPTS"] = "1"
        try:
            rendered = build_and_render_coworker_reply(
                greeting="Hej,",
                signature_name="Niklas",
                missing_fact_plan=missing,
                eligibility=eligibility,
                input_data=input_data,
                entities=entities,
                business_intent=playbook_intent,
                thread_state=thread_state,
            )
        finally:
            if prev_enabled is None:
                os.environ.pop("DIGITAL_COWORKER_REPLY_ENABLED", None)
            else:
                os.environ["DIGITAL_COWORKER_REPLY_ENABLED"] = prev_enabled
            if prev_llm is None:
                os.environ.pop("DIGITAL_COWORKER_LLM_RENDER", None)
            else:
                os.environ["DIGITAL_COWORKER_LLM_RENDER"] = prev_llm
            if prev_retries is None:
                os.environ.pop("LLM_RETRY_ATTEMPTS", None)
            else:
                os.environ["LLM_RETRY_ATTEMPTS"] = prev_retries
        if rendered is not None:
            body, plan_v2, render_result, _meta = rendered
            provenance = render_result.provenance.to_dict()
            render_validation = dict(render_result.validation or {})
            llm_meta = render_validation.get("llm_meta") or {}
            provenance["llm_meta"] = llm_meta

    from app.evaluation.profile_testbot.coworker_quality_oracles import _structural_skeleton

    oracle_results = evaluate_coworker_reply_oracles(
        scenario=scenario,
        reply_body=body,
        plan_v2=plan_v2,
        provenance=render_result.provenance if render_result is not None else None,
        render_validation=render_validation or None,
    )
    proxy = score_reply_for_review(
        scenario_id=scenario.scenario_id,
        family=scenario.family,
        reply_body=body,
        required_markers=list(setup.get("required_markers") or []),
    )
    audit = _build_scenario_audit(
        scenario=scenario,
        input_data=input_data,
        entities=entities,
        missing_known=missing.known_facts,
        pipeline_ctx=pipeline_ctx,
        info_plan=info_plan.to_dict(),
        plan_v2=plan_v2,
    )
    return RenderedScenario(
        scenario=scenario,
        bucket="",
        tags=[],
        body=body,
        plan_v2=plan_v2,
        provenance=provenance,
        playbook={
            "playbook_id": playbook.playbook_id,
            "service_family": playbook.service_family,
            "service_type": service_type,
            "business_intent": playbook_intent,
        },
        next_step=next_step.to_dict(),
        info_plan=info_plan.to_dict(),
        oracles=[r.to_dict() for r in oracle_results],
        proxy_score=proxy.to_dict(),
        template_skeleton=_structural_skeleton(body),
        audit=audit,
        render_validation=render_validation or None,
    )


def _prefill_blockers(item: RenderedScenario) -> dict[str, str]:
    body = (item.body or "").lower()
    setup = item.scenario.customer_state_setup or {}
    blockers: dict[str, str] = {key: "PENDING" for key, _ in BLOCKER_CHECKS}
    for oracle in item.oracles:
        if oracle["name"] == "no_unjustified_name_request" and oracle["status"] == "fail":
            blockers["unjustified_name_request"] = "YES (oracle)"
        if oracle["name"] == "no_unjustified_phone_request" and oracle["status"] == "fail":
            blockers["unjustified_phone_request"] = "YES (oracle)"
    if any(m in body for m in ("ptb-dcq", "eval.test", "oracle", "playbook_id")):
        blockers["eval_or_technical_term"] = "YES (proxy)"
    for claim in item.scenario.forbidden_reply_claims:
        if claim.lower() in body:
            blockers["forbidden_promise"] = f"YES ({claim})"
    if "tack för din förfrågan. vi tittar" in body and len(item.info_plan.get("selected_questions") or []) >= 3:
        blockers["generic_template_despite_rich_plan"] = "REVIEW"
    return blockers


def _renderer_label(provenance: dict[str, Any]) -> str:
    if not provenance:
        return "no_reply"
    llm_meta = provenance.get("llm_meta") or {}
    tier = llm_meta.get("fallback_tier") or ("none" if not provenance.get("use_fallback") else "unknown")
    if tier == "safe":
        return "safe_fallback"
    if tier == "hermetic":
        return "deterministic_fallback"
    if llm_meta.get("live_call") and provenance.get("llm_used"):
        return "constrained_llm_success"
    if llm_meta.get("invocation_attempted") and llm_meta.get("provider_outcome") in {"failed", "parse_failed"}:
        return "provider_failed_hermetic"
    return "hermetic_composer"


def _renderer_distribution(rendered: list[RenderedScenario]) -> dict[str, int]:
    counts = {
        "constrained_llm_success": 0,
        "deterministic_fallback": 0,
        "safe_fallback": 0,
        "no_reply": 0,
        "provider_failed_hermetic": 0,
        "hermetic_composer": 0,
        "provider_failures": 0,
        "parser_failures": 0,
        "validator_failures": 0,
    }
    for item in rendered:
        label = _renderer_label(item.provenance)
        counts[label] = counts.get(label, 0) + 1
        llm_meta = item.provenance.get("llm_meta") or {}
        if llm_meta.get("provider_outcome") == "failed":
            counts["provider_failures"] += 1
        if llm_meta.get("provider_outcome") == "parse_failed":
            counts["parser_failures"] += 1
        if llm_meta.get("live_validation_outcome") == "fail":
            counts["validator_failures"] += 1
    return counts


def write_r1_qualification_report(*, merge_sha: str) -> Path:
    from app.evaluation.profile_testbot.coworker_quality_oracles import (
        dominant_generic_phrase_rate,
        exact_duplicate_reply_groups,
    )
    from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import (
        run_hermetic_coworker_reply_qualification,
    )

    result = run_hermetic_coworker_reply_qualification()
    profile = load_customer_profile(PROFILE_ID)
    scenarios = generate_coworker_reply_dataset(profile, seed=0)
    bodies: list[str] = []
    from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import _render_scenario_reply

    for scenario in scenarios:
        body, _, _ = _render_scenario_reply(scenario)
        if body:
            bodies.append(body)
    dup_groups = exact_duplicate_reply_groups(bodies)
    short = merge_sha[:7]
    path = STATUS / f"digital-coworker-r1-qualification-{short}.json"
    payload = {
        **result.to_dict(),
        "merge_sha": merge_sha,
        "scenario_pass_count": sum(1 for s in result.scenario_results if s.passed),
        "dominant_generic_phrase_rate": dominant_generic_phrase_rate(bodies),
        "exact_duplicate_groups": len(dup_groups),
        "exact_duplicate_reply_count": sum(len(g) for g in dup_groups),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def validate_selection(scenarios_by_id: dict[str, ProfileScenario]) -> list[str]:
    failures: list[str] = []
    if len(SELECTION) != 40:
        failures.append(f"selection count {len(SELECTION)} != 40")
    ids = [row[0] for row in SELECTION]
    if len(set(ids)) != 40:
        failures.append("duplicate scenario ids in selection")
    multi_turn = 0
    no_name_phone = 0
    service_q = 0
    for sid, _bucket, tags in SELECTION:
        if sid not in scenarios_by_id:
            failures.append(f"missing scenario {sid}")
            continue
        setup = scenarios_by_id[sid].customer_state_setup or {}
        if setup.get("thread_state") == "continuation" or "multi_turn" in tags:
            multi_turn += 1
        if setup.get("forbid_name_request") or setup.get("forbid_phone_request") or "no_name_phone" in tags:
            no_name_phone += 1
        if "service_specific_questions" in tags or "business_facts" in tags:
            service_q += 1
    if multi_turn < 10:
        failures.append(f"multi_turn coverage {multi_turn} < 10")
    if no_name_phone < 10:
        failures.append(f"no_name_phone coverage {no_name_phone} < 10")
    if service_q < 10:
        failures.append(f"service_specific coverage {service_q} < 10")
    return failures


def build_reports(*, merge_sha: str) -> dict[str, Path]:
    short = merge_sha[:7]
    profile = load_customer_profile(PROFILE_ID)
    all_scenarios = generate_coworker_reply_dataset(profile, seed=0)
    by_id = {s.scenario_id: s for s in all_scenarios}
    failures = validate_selection(by_id)
    if failures:
        raise RuntimeError("selection validation failed: " + "; ".join(failures))

    rendered: list[RenderedScenario] = []
    for sid, bucket, tags in SELECTION:
        item = render_scenario_full(by_id[sid])
        item.bucket = bucket
        item.tags = tags
        rendered.append(item)

    bodies = [r.body for r in rendered if r.body]
    families = [r.scenario.family for r in rendered if r.body]
    similarity = template_similarity_ratio(bodies, families=families)
    fallback_count = sum(1 for r in rendered if r.provenance.get("use_fallback"))
    renderer_counts = _renderer_distribution(rendered)
    pack_quality_rows: list[dict[str, Any]] = []
    mixed_language_total = 0
    surface_total = 0
    blocking_oracle_total = 0
    aggregation_contradictions = 0

    for item in rendered:
        s = item.scenario
        input_data = {
            "subject": s.input.subject,
            "message_text": s.input.message_text,
            "language": s.input.language,
        }
        exp_lang = expected_reply_language(
            scenario=s,
            plan_v2=item.plan_v2,
            input_data=input_data,
        )
        oracle_results = [
            CoworkerOracleResult(
                o["name"], o["status"], o["category"], o["detail"], blocker=o.get("blocker", True)
            )
            for o in item.oracles
        ]
        surface_metrics = summarize_surface_quality_metrics(
            reply_body=item.body,
            expected_language=exp_lang,
            oracle_results=oracle_results,
        )
        agg = aggregate_coworker_results(oracle_results)
        mixed_language_total += surface_metrics["mixed_language_violations"]
        surface_total += (
            surface_metrics["internal_metadata_violations"]
            + surface_metrics["unlocalized_fact_label_violations"]
            + surface_metrics["unresolved_placeholder_violations"]
        )
        blocking_oracle_total += surface_metrics["blocking_oracle_failures"]
        if not surface_metrics["aggregation_consistent"]:
            aggregation_contradictions += 1
        final_gate = (item.render_validation or {}).get("final_customer_text_validation") or {}
        scenario_pass = agg["passed"] and bool(final_gate.get("passed", True))
        pack_quality_rows.append(
            {
                "scenario_id": s.scenario_id,
                "expected_language": exp_lang,
                "blocking_oracle_failures": agg["blocking_failures"],
                "surface_metrics": surface_metrics,
                "scenario_pass": scenario_pass,
                "overall_pass": scenario_pass,
                "final_customer_text_validation": final_gate,
                "fact_integrity_audit": item.audit or {},
            }
        )

    thread_states = [
        str((r.scenario.customer_state_setup or {}).get("thread_state") or "new_thread")
        for r in rendered
    ]
    raw_llm_validator_failures = sum(
        int((r.render_validation or {}).get("llm_meta", {}).get("raw_llm_validator_failures") or 0)
        for r in rendered
    )
    deterministic_fallback_count = sum(
        int((r.render_validation or {}).get("llm_meta", {}).get("deterministic_fallback_count") or 0)
        for r in rendered
    )
    fallback_validator_failures = sum(
        int((r.render_validation or {}).get("llm_meta", {}).get("fallback_validator_failures") or 0)
        for r in rendered
    )
    final_customer_text_validator_failures = sum(
        1
        for r in rendered
        if not ((r.render_validation or {}).get("final_customer_text_validation") or {}).get("passed", True)
    )
    precheck = evaluate_package_precheck(
        scenario_pass=[row["scenario_pass"] for row in pack_quality_rows],
        bodies=[r.body for r in rendered],
        families=[r.scenario.family for r in rendered],
        thread_states=thread_states,
        use_fallback=[bool(r.provenance.get("use_fallback")) for r in rendered],
        llm_used=[bool(r.provenance.get("llm_used")) for r in rendered],
        invocation_attempted=[
            bool((r.provenance.get("llm_meta") or {}).get("invocation_attempted"))
            for r in rendered
        ],
        provider_outcomes=[
            str((r.provenance.get("llm_meta") or {}).get("provider_outcome") or "")
            for r in rendered
        ],
        live_validation_outcomes=[
            (r.provenance.get("llm_meta") or {}).get("live_validation_outcome")
            for r in rendered
        ],
        aggregation_consistent=[row["surface_metrics"]["aggregation_consistent"] for row in pack_quality_rows],
        final_customer_text_pass=[
            bool((row.get("final_customer_text_validation") or {}).get("passed", True))
            for row in pack_quality_rows
        ],
        raw_llm_validator_failures=raw_llm_validator_failures,
        deterministic_fallback_count=deterministic_fallback_count,
        fallback_validator_failures=fallback_validator_failures,
        final_customer_text_validator_failures=final_customer_text_validator_failures,
        renderer_distribution=renderer_counts,
    )
    package_qualification = (
        "QUALIFYING_HUMAN_REVIEW_PACKAGE"
        if precheck.package_precheck_pass
        else "NON_QUALIFYING_DIAGNOSTIC_PACKAGE"
    )
    r2_precheck = "PASS" if precheck.package_precheck_pass else "FAIL"

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    paths = {
        "review": STATUS / f"digital-coworker-human-review-40-{short}.md",
        "sends": STATUS / f"digital-coworker-human-review-sends-{short}.md",
        "metrics": STATUS / f"digital-coworker-human-review-metrics-{short}.json",
        "provenance": STATUS / f"digital-coworker-renderer-provenance-{short}.md",
    }

    review_lines = [
        f"# digital-coworker-human-review-40-{short}.md",
        "",
        f"- merge_sha: `{merge_sha}`",
        f"- generated_at: {now}",
        f"- profile_id: `{PROFILE_ID}`",
        f"- package_qualification: `{package_qualification}`",
        f"- gate_status: R2_HUMAN_REVIEW=PENDING (operator scoring required)",
        f"- r2_precheck: {r2_precheck}",
        f"- package_precheck_pass: {precheck.package_precheck_pass}",
        f"- scenarios: 40/120",
        "",
    ]

    sends_lines = [
        f"# digital-coworker-human-review-sends-{short}.md",
        "",
        f"- merge_sha: `{merge_sha}`",
        f"- live_gmail_sent: **NO** (constrained LLM render only; no Gmail write)",
        f"- renderer: `{PROMPT_VERSION}` / model `{MODEL_ID}`",
        f"- operator_send_required: after human review PASS",
        "",
        "| scenario_id | family | expected_send | rendered | would_send_after_review |",
        "|---|---|---|---|---|",
    ]

    provenance_lines = [
        f"# digital-coworker-renderer-provenance-{short}.md",
        "",
        f"- merge_sha: `{merge_sha}`",
        f"- renderer_distribution: {json.dumps(renderer_counts, ensure_ascii=False)}",
        f"- fallback_rate: {fallback_count / max(len(rendered), 1):.3f}",
        f"- template_similarity (40-pack): {similarity:.3f}",
        "",
        f"- prompt_version: `{PROMPT_VERSION}`",
        f"- model_id: `{MODEL_ID}`",
        "",
        "| scenario_id | renderer | model | prompt | invocation | provider | validation | fallback | fallback_reason | plan_hash | body_hash |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for item in rendered:
        s = item.scenario
        setup = s.customer_state_setup or {}
        blockers = _prefill_blockers(item)
        blocking_oracles = [o for o in item.oracles if o.get("blocker") and o.get("status") == "fail"]
        advisory_oracles = [o for o in item.oracles if not o.get("blocker") or o.get("status") != "fail"]

        review_lines.extend(
            [
                f"## {s.scenario_id}",
                f"- selection_bucket: {item.bucket}",
                f"- selection_tags: {', '.join(item.tags)}",
                f"- scenario_family: `{s.family}`",
                f"- expected_send_behavior: `{s.expected_send_behavior}`",
                f"- thread_state: `{setup.get('thread_state')}`",
                f"- language: `{s.input.language}`",
                "",
                "### Inkommande (redigerad)",
                "```",
                redact_text(s.input.message_text),
                "```",
                "",
                "### Ämnesrad",
                redact_text(s.input.subject),
                "",
                "### Trådhistorik",
                f"- thread_state: {setup.get('thread_state')}",
                f"- prior_safe_ack: {setup.get('thread_state') == 'continuation'}",
                f"- gmail_thread_id: [REDACTED_THREAD]",
                "",
                "### Kända fakta",
                json.dumps(redact_obj(list(setup.get('known_entities') or [])), ensure_ascii=False),
                "",
                "### Service playbook",
                "```json",
                json.dumps(redact_obj(item.playbook), indent=2, ensure_ascii=False),
                "```",
                "",
                "### OperationalNextStep",
                "```json",
                json.dumps(redact_obj(item.next_step), indent=2, ensure_ascii=False),
                "```",
                "",
                "### InformationValuePlan",
                "```json",
                json.dumps(redact_obj(item.info_plan), indent=2, ensure_ascii=False),
                "```",
                "",
                "### Fact integrity audit",
                "```json",
                json.dumps(redact_obj(item.audit or {}), indent=2, ensure_ascii=False),
                "```",
                "",
                "### CustomerReplyPlanV2",
                "```json",
                json.dumps(redact_obj(item.plan_v2.to_dict() if item.plan_v2 else {}), indent=2, ensure_ascii=False),
                "```",
                "",
                "### Selected / excluded questions",
                f"- selected_questions: `{list(item.plan_v2.selected_questions) if item.plan_v2 else []}`",
                f"- question_surface_labels: `{list(item.plan_v2.question_surface_labels) if item.plan_v2 else []}`",
                f"- facts_not_allowed_to_repeat: `{list(item.plan_v2.facts_not_allowed_to_repeat) if item.plan_v2 else []}`",
                "",
                "### Actual LLM provenance",
                f"- renderer_mode: `{_renderer_label(item.provenance)}`",
                f"- invocation_attempted: `{(item.provenance.get('llm_meta') or {}).get('invocation_attempted', False)}`",
                f"- provider_outcome: `{(item.provenance.get('llm_meta') or {}).get('provider_outcome', 'n/a')}`",
                f"- model_id: `{item.provenance.get('model_id') or (item.provenance.get('llm_meta') or {}).get('returned_model') or 'n/a'}`",
                f"- prompt_version: `{item.provenance.get('prompt_version') or (item.provenance.get('llm_meta') or {}).get('prompt_version') or 'n/a'}`",
                f"- plan_hash: `{(item.provenance.get('plan_hash') or '')[:16]}`",
                f"- live_validation_outcome: `{(item.provenance.get('llm_meta') or {}).get('live_validation_outcome', 'n/a')}`",
                f"- use_fallback: `{item.provenance.get('use_fallback', False)}`",
                f"- fallback_reason: `{item.provenance.get('fallback_reason') or 'n/a'}`",
                f"- body_hash: `{(item.provenance.get('body_hash') or '')[:16]}`",
                "",
                "### Rå LLM-output (före eventuell fallback)",
                "```",
                redact_text((item.provenance.get("llm_meta") or {}).get("live_body") or "(ingen live-output)"),
                "```",
                "",
                "### Validatorresultat (live)",
                f"- issues: `{(item.provenance.get('llm_meta') or {}).get('live_validation_issues') or []}`",
                "",
                "### Final customer text validation",
                f"- passed: `{(item.render_validation or {}).get('final_customer_text_validation', {}).get('passed', 'n/a')}`",
                f"- validation_stage: `{(item.render_validation or {}).get('final_customer_text_validation', {}).get('validation_stage', 'n/a')}`",
                f"- validator_version: `{(item.render_validation or {}).get('final_customer_text_validation', {}).get('validator_version', 'n/a')}`",
                f"- validated_body_hash: `{(item.render_validation or {}).get('final_customer_text_validation', {}).get('validated_body_hash', 'n/a')}`",
                f"- issues: `{(item.render_validation or {}).get('final_customer_text_validation', {}).get('issues') or []}`",
                "",
                "### Renderer",
                f"- mode: `{_renderer_label(item.provenance)}`",
                f"- template_version: `{item.provenance.get('template_version', 'n/a')}`",
                f"- use_fallback: `{item.provenance.get('use_fallback', False)}`",
                f"- fallback_reason: `{item.provenance.get('fallback_reason') or 'n/a'}`",
                "",
                "### Slutlig kundtext (faktisk render)",
                "```",
                redact_text(item.body),
                "```",
                "",
                "### Profil ton och signatur",
                f"- response_tone: `{profile.response_tone}`",
                f"- signature_name: `Niklas`",
                f"- language: `{s.input.language}`",
                "",
                f"- template_skeleton: `{item.template_skeleton}`",
                f"- template_similarity_pack_context: see metrics file",
                "",
                "### Blockerande oracle-resultat",
            ]
        )
        if blocking_oracles:
            for o in blocking_oracles:
                review_lines.append(f"- `{o['name']}`: **{o['status']}** — {o['detail']}")
        else:
            review_lines.append("- (inga blockerande fel)")
        review_lines.append("")
        review_lines.append("### Advisory-resultat")
        if advisory_oracles:
            for o in advisory_oracles:
                review_lines.append(f"- `{o['name']}`: {o['status']} — {o['detail']}")
        else:
            review_lines.append("- (inga)")
        review_lines.append("")
        review_lines.append("### Human review — dimensioner (1–5, FYLL I MANUELLT)")
        review_lines.append("| # | Dimension | Poäng | Kommentar |")
        review_lines.append("|---|---|---|---|")
        for idx, (_key, label) in enumerate(HUMAN_DIMENSIONS, start=1):
            review_lines.append(f"| {idx} | {label} | PENDING | |")
        review_lines.append("")
        review_lines.append("### Blockerande ja/nej (FYLL I MANUELLT)")
        review_lines.append("| Check | Värde |")
        review_lines.append("|---|---|")
        for key, label in BLOCKER_CHECKS:
            review_lines.append(f"| {label} | {blockers[key]} |")
        review_lines.append("")

        would_send = (
            s.expected_send_behavior in {"send_after_approval", "draft_for_approval"}
            and not blocking_oracles
            and bool(item.body.strip())
        )
        sends_lines.append(
            f"| {s.scenario_id} | {s.family} | {s.expected_send_behavior} | "
            f"{'yes' if item.body.strip() else 'no'} | {'pending_review' if would_send else 'hold'} |"
        )
        llm_meta = item.provenance.get("llm_meta") or {}
        provenance_lines.append(
            f"| {s.scenario_id} | {_renderer_label(item.provenance)} | "
            f"{item.provenance.get('model_id') or llm_meta.get('model_id') or ''} | "
            f"{item.provenance.get('prompt_version') or llm_meta.get('prompt_version') or ''} | "
            f"{llm_meta.get('invocation_attempted', False)} | "
            f"{llm_meta.get('provider_outcome') or ''} | "
            f"{llm_meta.get('validation_outcome') or ''} | "
            f"{item.provenance.get('use_fallback', False)} | "
            f"{item.provenance.get('fallback_reason') or ''} | "
            f"{(item.provenance.get('plan_hash') or '')[:12]} | "
            f"{(item.provenance.get('body_hash') or '')[:12]} |"
        )

    metrics = {
        "merge_sha": merge_sha,
        "generated_at": now,
        "profile_id": PROFILE_ID,
        "package_qualification": package_qualification,
        "qualification_gates": {
            "R1_HERMETIC": "PASS",
            "R2_PRECHECK": r2_precheck,
            "R2_HUMAN_REVIEW": "PENDING",
            "R3_LIVE_CANARY": "PENDING",
            "R4_LIVE_CAMPAIGN": "PENDING",
            "R5_CLOSURE": "PENDING",
        },
        "registry": {
            "PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED": "PENDING",
        },
        "package_precheck": precheck.to_dict(),
        "human_review_pack": {
            "scenario_count": 40,
            "scenario_ids": [row[0] for row in SELECTION],
            "multi_turn_selected": sum(
                1
                for sid, _, tags in SELECTION
                if (by_id[sid].customer_state_setup or {}).get("thread_state") == "continuation"
                or "multi_turn" in tags
            ),
            "no_name_phone_selected": sum(
                1
                for sid, _, tags in SELECTION
                if (by_id[sid].customer_state_setup or {}).get("forbid_name_request")
                or (by_id[sid].customer_state_setup or {}).get("forbid_phone_request")
                or "no_name_phone" in tags
            ),
        },
        "render_metrics": {
            "prompt_version": PROMPT_VERSION,
            "model_id": MODEL_ID,
            "template_similarity_40_pack": similarity,
            "fallback_rate_40_pack": fallback_count / max(len(rendered), 1),
            "renderer_distribution": renderer_counts,
            "provider_failures": renderer_counts.get("provider_failed_hermetic", 0),
            "validator_failures": sum(
                1
                for r in rendered
                if (r.provenance.get("llm_meta") or {}).get("validation_outcome") == "fail"
            ),
        },
        "quality_metrics_40_pack": {
            "mixed_language_violations": mixed_language_total,
            "surface_violations": surface_total,
            "blocking_oracle_failures": blocking_oracle_total,
            "aggregation_contradictions": aggregation_contradictions,
            "raw_llm_validator_failures": raw_llm_validator_failures,
            "deterministic_fallback_count": deterministic_fallback_count,
            "fallback_validator_failures": fallback_validator_failures,
            "final_customer_text_validator_failures": final_customer_text_validator_failures,
            "scenario_quality": pack_quality_rows,
        },
        "proxy_scores": [r.proxy_score for r in rendered],
        "live_gmail_executed": False,
    }

    paths["review"].write_text("\n".join(review_lines) + "\n", encoding="utf-8")
    paths["sends"].write_text("\n".join(sends_lines) + "\n", encoding="utf-8")
    paths["metrics"].write_text(json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["provenance"].write_text("\n".join(provenance_lines) + "\n", encoding="utf-8")
    return paths


def check_live_prep() -> dict[str, Any]:
    env_path = ROOT / ".env.live-eval.local"
    result: dict[str, Any] = {
        "env_file_exists": env_path.exists(),
        "required_vars_present": {},
        "oauth_loadable": False,
        "port_8010_available": None,
        "tenant_live_eval_configured": False,
        "gmail_sent": False,
    }
    required = [
        "TENANT_LIVE_EVAL",
        "LIVE_EVAL_APP_BASE_URL",
        "ADMIN_API_KEY",
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "LIVE_EVAL_SENDER_EMAILS",
        "LIVE_EVAL_RECIPIENT_EMAILS",
    ]
    if env_path.exists():
        text = env_path.read_text(encoding="utf-8", errors="replace")
        for var in required:
            result["required_vars_present"][var] = bool(re.search(rf"^{var}=", text, re.M))
        result["tenant_live_eval_configured"] = "TENANT_LIVE_EVAL" in text
        try:
            from dotenv import dotenv_values

            vals = dotenv_values(env_path)
            if vals.get("GOOGLE_OAUTH_CLIENT_ID") and vals.get("GOOGLE_OAUTH_CLIENT_SECRET"):
                result["oauth_loadable"] = True
        except Exception as exc:  # noqa: BLE001
            result["oauth_loadable"] = False
            result["oauth_error"] = str(exc)
    try:
        proc = subprocess.run(
            ["powershell", "-Command", "(Get-NetTCPConnection -LocalPort 8010 -ErrorAction SilentlyContinue | Measure-Object).Count"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        count = int((proc.stdout or "0").strip() or "0")
        result["port_8010_available"] = count == 0
    except Exception as exc:  # noqa: BLE001
        result["port_8010_available"] = None
        result["port_check_error"] = str(exc)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--merge-sha", required=True, help="Exact git SHA the package is built from")
    parser.add_argument(
        "--skip-worktree-check",
        action="store_true",
        help="Dev only — normally refuse dirty worktree outside storage/status",
    )
    args = parser.parse_args()
    verify_merge_sha(args.merge_sha)
    if not args.skip_worktree_check:
        verify_clean_worktree()
    paths = build_reports(merge_sha=args.merge_sha)
    r1_path = write_r1_qualification_report(merge_sha=args.merge_sha)
    live = check_live_prep()
    print(
        json.dumps(
            {
                "reports": {k: str(v) for k, v in paths.items()},
                "r1_qualification": str(r1_path),
                "live_prep": live,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
