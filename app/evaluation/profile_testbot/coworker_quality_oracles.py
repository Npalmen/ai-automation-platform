"""Blocking coworker reply quality oracles (Todo H)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario
from app.workflows.reply_quality.surface_contract import (
    detect_internal_metadata_leaks,
    detect_key_value_fragments,
    detect_mixed_language,
    detect_robotic_template_composition,
    detect_semantic_placeholders,
    detect_unlocalized_fact_labels,
    detect_unresolved_placeholders,
    validate_customer_surface,
)
from app.workflows.reply_quality.fact_extraction import extract_customer_facts, is_valid_case_reference
from app.workflows.reply_quality.post_render_validator import validate_post_render_reply
from app.workflows.reply_quality.reply_language import authoritative_reply_language
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.provenance import ReplyRenderProvenance
from app.workflows.reply_quality.fact_evidence import (
    ADDRESS_STATE_PROPERTY_ADDRESS,
    build_fact_evidence,
)
from app.workflows.reply_quality.plan_invariants import validate_pipeline_playbook_consistency
from app.workflows.reply_quality.semantic_fact_predicates import (
    attachment_state,
    detect_consultation_intent,
    detect_semantic_fact_ids,
    existing_solar_verified,
    is_battery_retrofit_intent,
)

THRESHOLD_VERSION = "coworker_reply_thresholds_v4"

COWORKER_THRESHOLDS = {
    "hard_safety_pass_rate": 1.0,
    "plan_fidelity_pass_rate": 1.0,
    "template_similarity_max": 0.72,
    "fallback_rate_max": 0.15,
    "service_specificity_min": 0.85,
    "question_utility_min": 0.90,
}


@dataclass
class CoworkerOracleResult:
    name: str
    status: str
    category: str
    detail: str
    blocker: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "category": self.category,
            "detail": self.detail,
            "blocker": self.blocker,
        }


_MARKER_SYNONYMS: dict[str, tuple[str, ...]] = {
    "sol": ("sol", "solcell", "solar"),
    "solar": ("solar", "solcell", "sol"),
    "batteri": ("batteri", "battery", "batterilager"),
    "battery": ("battery", "batteri", "batterilager"),
    "laddbox": ("laddbox", "ladd", "charger"),
    "charger": ("charger", "laddbox", "ladd"),
    "meddelande": ("meddelande", "message"),
    "message": ("message", "meddelande"),
    "uppföljning": ("uppföljning", "följer upp", "follow-up", "follow up"),
    "kompletter": ("kompletter", "kompletterande"),
    "status": ("status", "ärende"),
    "ärende": ("ärende", "status"),
    "befintlig": ("befintlig", "befintliga", "existing"),
    "reklamation": ("reklamation", "complaint"),
}


_TRANSPORT_INPUT_PATTERNS = (
    re.compile(r"\bmeddelande\s+\d+\s+om\b", re.I),
    re.compile(r"\bkompletterande info punkt\b", re.I),
    re.compile(r"\boffertförfrågan\s+0\b", re.I),
    re.compile(r"\bupptäcktes för den här veckan\b", re.I),
)

_GENERIC_NEXT_STEP_SV = "när vi har det underlaget går vi igenom förutsättningarna och återkommer"


def _oracle_pass(name: str, category: str, detail: str) -> CoworkerOracleResult:
    return CoworkerOracleResult(name, "pass", category, detail)


def _oracle_fail(name: str, category: str, detail: str) -> CoworkerOracleResult:
    return CoworkerOracleResult(name, "fail", category, detail)


def evaluate_input_realism_oracles(*, scenario: ProfileScenario) -> list[CoworkerOracleResult]:
    text = f"{scenario.input.subject} {scenario.input.message_text}"
    issues: list[str] = []
    for pattern in _TRANSPORT_INPUT_PATTERNS:
        if pattern.search(text):
            issues.append(pattern.pattern)
    return [
        _oracle_fail("realistic_customer_input", "dataset_quality", ";".join(issues[:3]))
        if issues
        else _oracle_pass("realistic_customer_input", "dataset_quality", "realistic")
    ]


def evaluate_scenario_family_alignment(*, scenario: ProfileScenario) -> list[CoworkerOracleResult]:
    family = scenario.family or ""
    text = f"{scenario.input.subject} {scenario.input.message_text}".lower()
    issues: list[str] = []
    if family == "missing_attachment" and not any(
        token in text for token in ("saknar", "bifog", "ritning", "drawing", "attach", "utan bifog")
    ):
        issues.append("missing_attachment_without_attachment_context")
    if family == "solar_battery_combined" and not (
        ("sol" in text or "solar" in text) and ("batteri" in text or "battery" in text)
    ):
        issues.append("solar_battery_missing_dual_topic")
    if family == "multi_turn_continuation" and "kompletterande info punkt" in text:
        issues.append("transport_continuation_text")
    return [
        _oracle_fail("scenario_family_input_alignment", "dataset_quality", issues[0])
        if issues
        else _oracle_pass("scenario_family_input_alignment", "dataset_quality", family)
    ]


def evaluate_valid_reference_oracle(*, scenario: ProfileScenario) -> list[CoworkerOracleResult]:
    text = f"{scenario.input.subject} {scenario.input.message_text}"
    refs = re.findall(r"\b(?:ärende|offertförfrågan|case|order)\s*(\d+)\b", text, re.I)
    bad = [ref for ref in refs if not is_valid_case_reference(ref)]
    return [
        _oracle_fail("valid_reference_value", "dataset_quality", ",".join(bad))
        if bad
        else _oracle_pass("valid_reference_value", "dataset_quality", "valid")
    ]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


_FOLLOWUP_ACK_FORBIDDEN_ON_NEW = re.compile(
    r"\b(igen|återkomst|uppföljning|kompletterande|again|follow[- ]up)\b",
    re.I,
)
_MALFORMED_QUESTION = re.compile(
    r"\bom (?:du|ni) har om (?:du|ni) har\b|\bkan (?:du|ni) skicka vilken\b|if you have if you have"
    r"|\bbekräfta om det finns redan\b"
    r"|\bkan (?:du|ni) bekräfta huruvida\b",
    re.I,
)


def _scenario_evidence_context(scenario: ProfileScenario) -> tuple[dict[str, Any], tuple[str, ...]]:
    from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario as _ProfileScenario

    _ = _ProfileScenario
    setup = scenario.customer_state_setup or {}
    entities: dict[str, Any] = {"email": scenario.input.sender_email or "customer@example.com"}
    from app.workflows.reply_quality.customer_surface import extract_city_phrase

    for key in setup.get("known_entities") or []:
        if key == "city":
            entities[key] = (
                extract_city_phrase(text=scenario.input.message_text, entities={}) or "Uppsala"
            )
        else:
            entities[key] = f"known-{key}"
    return entities, tuple(setup.get("known_facts") or ())


def _semantic_known_fields(fact_ids: set[str]) -> set[str]:
    from app.workflows.reply_quality.semantic_fact_predicates import semantic_known_question_fields

    return semantic_known_question_fields(fact_ids)


def evaluate_semantic_human_review_oracles(
    *,
    scenario: ProfileScenario,
    reply_body: str,
    plan_v2: CustomerReplyPlanV2 | None,
) -> list[CoworkerOracleResult]:
    """Blocking oracles for semantic human-review closure."""
    if plan_v2 is None:
        return []

    text = f"{scenario.input.subject} {scenario.input.message_text}"
    lowered = (reply_body or "").lower()
    setup = scenario.customer_state_setup or {}
    thread_state = setup.get("thread_state", "new_thread")
    results: list[CoworkerOracleResult] = []
    extracted = extract_customer_facts(
        input_data={"subject": scenario.input.subject, "message_text": scenario.input.message_text}
    )
    semantic_ids = detect_semantic_fact_ids(text)
    selected = set(plan_v2.selected_questions or ())

    if "requested_service" in selected and (
        "requested_service_explicit" in semantic_ids
        or "requested_service" in extracted.known_question_fields
    ):
        results.append(
            _oracle_fail("explicit_service_reask", "question_utility", "requested_service")
        )
    else:
        results.append(_oracle_pass("explicit_service_reask", "question_utility", "clean"))

    if "housing_association_context" in selected and semantic_ids.intersection(
        {"property_type_villa", "property_type_private"}
    ):
        results.append(
            _oracle_fail("property_context_reask", "question_utility", "housing_association_context")
        )
    else:
        results.append(_oracle_pass("property_context_reask", "question_utility", "clean"))

    if "load_balancing_need" in selected and "load_balancing_stated" in semantic_ids:
        results.append(
            _oracle_fail("requested_feature_reask", "question_utility", "load_balancing_need")
        )
    else:
        results.append(_oracle_pass("requested_feature_reask", "question_utility", "clean"))

    if thread_state == "new_thread" and _FOLLOWUP_ACK_FORBIDDEN_ON_NEW.search(
        plan_v2.acknowledgement_statement or ""
    ):
        if not any(
            token in text.lower()
            for token in ("kompletterande", "following up", "follow-up", "follow up", "bifogar nu", "again")
        ):
            results.append(
                _oracle_fail(
                    "thread_acknowledgement_evidence",
                    "conversation_quality",
                    "followup_wording_without_evidence",
                )
            )
        else:
            results.append(
                _oracle_pass("thread_acknowledgement_evidence", "conversation_quality", "evidence_present")
            )
    else:
        results.append(
            _oracle_pass("thread_acknowledgement_evidence", "conversation_quality", "allowed")
        )

    attach = attachment_state(text)
    if attach in {"attachment_claimed_kwh", "attachment_present_kwh"} and re.search(
        r"\b(?:skicka|send)\b.{0,24}\bigen\b", lowered
    ):
        results.append(
            _oracle_fail("attachment_state_alignment", "conversation_quality", "resend_with_claimed_kwh")
        )
    elif attach == "attachment_missing_drawing" and "resend" in lowered and thread_state == "new_thread":
        results.append(
            _oracle_fail("attachment_state_alignment", "conversation_quality", "resend_without_prior_send")
        )
    else:
        results.append(_oracle_pass("attachment_state_alignment", "conversation_quality", "aligned"))

    if extracted.location_city and "property_address" not in semantic_ids:
        address_known = (
            "address" in (plan_v2.facts_not_allowed_to_repeat or ())
            or any(v.startswith("internal_known:address") for v in (plan_v2.verified_facts or ()))
        )
        if address_known and plan_v2.location_phrase:
            results.append(
                _oracle_fail("city_address_granularity", "question_utility", "city_treated_as_address")
            )
        else:
            results.append(_oracle_pass("city_address_granularity", "question_utility", "clean"))
    else:
        results.append(_oracle_pass("city_address_granularity", "question_utility", "clean"))

    entities, _known_facts = _scenario_evidence_context(scenario)
    evidence = build_fact_evidence(
        input_data={"subject": scenario.input.subject, "message_text": scenario.input.message_text},
        entities=entities,
        known_fact_fields=tuple(plan_v2.facts_not_allowed_to_repeat or ()),
    )
    evidence_failures: list[str] = []
    for field in plan_v2.facts_not_allowed_to_repeat or ():
        if field in evidence.evidenced_question_fields:
            continue
        if field in {"existing_solar_system", "current_inverter"} and not existing_solar_verified(
            semantic_ids, set(extracted.known_question_fields)
        ):
            evidence_failures.append(field)
        elif field == "address" and evidence.address_state.state != ADDRESS_STATE_PROPERTY_ADDRESS:
            evidence_failures.append(field)
        elif field in {"contact_name", "phone_or_email"}:
            if field == "phone_or_email" and "@" in text:
                continue
            evidence_failures.append(field)
        else:
            evidence_failures.append(field)
    if evidence_failures:
        results.append(
            _oracle_fail(
                "verified_fact_requires_positive_evidence",
                "question_utility",
                ",".join(sorted(set(evidence_failures))[:3]),
            )
        )
    else:
        results.append(
            _oracle_pass("verified_fact_requires_positive_evidence", "question_utility", "clean")
        )

    exclusion_failures = [
        reason
        for reason in (plan_v2.evidence or ())
        if reason.startswith("exclude:") and reason.endswith(":already_known")
    ]
    if exclusion_failures:
        results.append(
            _oracle_fail(
                "excluded_question_does_not_imply_known_fact",
                "question_utility",
                exclusion_failures[0],
            )
        )
    else:
        results.append(
            _oracle_pass("excluded_question_does_not_imply_known_fact", "question_utility", "clean")
        )

    playbook_check = validate_pipeline_playbook_consistency(
        playbook_id=plan_v2.playbook_id,
        service_family=plan_v2.service_family,
        next_step_service_family=plan_v2.service_family,
    )
    if not playbook_check.passed:
        results.append(
            _oracle_fail(
                "pipeline_playbook_consistency",
                "plan_fidelity",
                ";".join(playbook_check.violations[:2]),
            )
        )
    else:
        results.append(_oracle_pass("pipeline_playbook_consistency", "plan_fidelity", "aligned"))

    consultation_intent = detect_consultation_intent(text)
    if consultation_intent:
        if "project_description" in selected:
            results.append(
                _oracle_fail("consultation_question_relevance", "question_utility", "project_description")
            )
        else:
            results.append(_oracle_pass("consultation_question_relevance", "question_utility", "clean"))
        if consultation_intent != "consultation_booking":
            results.append(
                _oracle_pass("consultation_intent_alignment", "question_utility", consultation_intent)
            )
        else:
            lowered_body = (reply_body or "").lower()
            if not any(token in lowered_body for token in ("call", "samtal", "times", "tider")):
                results.append(
                    _oracle_fail("booking_request_not_ignored", "conversation_quality", "call_not_acknowledged")
                )
            else:
                results.append(
                    _oracle_pass("booking_request_not_ignored", "conversation_quality", "acknowledged")
                )
            results.append(
                _oracle_pass("consultation_intent_alignment", "question_utility", consultation_intent)
            )
        if consultation_intent == "consultation_booking" and "requested_service" in selected:
            results.append(
                _oracle_fail("explicit_request_acknowledged", "conversation_quality", "service_reask")
            )
        elif consultation_intent:
            results.append(
                _oracle_pass("explicit_request_acknowledged", "conversation_quality", "acknowledged")
            )
    else:
        results.append(_oracle_pass("consultation_intent_alignment", "question_utility", "n/a"))
        results.append(_oracle_pass("consultation_question_relevance", "question_utility", "n/a"))
        results.append(_oracle_pass("explicit_request_acknowledged", "conversation_quality", "n/a"))
        results.append(_oracle_pass("booking_request_not_ignored", "conversation_quality", "n/a"))

    retrofit = is_battery_retrofit_intent(text)
    if retrofit and selected.intersection({"roof_type", "property_type"}):
        results.append(
            _oracle_fail("service_playbook_alignment", "question_utility", "retrofit_asks_solar_install_facts")
        )
    else:
        results.append(_oracle_pass("service_playbook_alignment", "question_utility", "aligned"))

    if not existing_solar_verified(semantic_ids, set(extracted.known_question_fields)) and (
        "existing_solar_system" in selected or "current_inverter" in selected
    ):
        if "existing_installation" not in selected:
            results.append(
                _oracle_fail(
                    "conditional_fact_premise",
                    "question_utility",
                    "solar_questions_without_verified_installation",
                )
            )
        else:
            results.append(_oracle_pass("conditional_fact_premise", "question_utility", "installation_first"))
    else:
        results.append(_oracle_pass("conditional_fact_premise", "question_utility", "clean"))

    irrelevant = [
        field
        for field in selected
        if field in extracted.known_question_fields or field in _semantic_known_fields(semantic_ids)
    ]
    if irrelevant:
        results.append(
            _oracle_fail(
                "semantic_question_relevance",
                "question_utility",
                ",".join(sorted(irrelevant)[:3]),
            )
        )
    else:
        results.append(_oracle_pass("semantic_question_relevance", "question_utility", "clean"))

    if _MALFORMED_QUESTION.search(reply_body or ""):
        results.append(
            _oracle_fail("malformed_natural_question", "surface_quality", "malformed_question_phrase")
        )
    else:
        results.append(_oracle_pass("malformed_natural_question", "surface_quality", "natural"))

    return results


def evaluate_coworker_reply_oracles(
    *,
    scenario: ProfileScenario,
    reply_body: str,
    plan_v2: CustomerReplyPlanV2 | None,
    provenance: ReplyRenderProvenance | None,
) -> list[CoworkerOracleResult]:
    setup = scenario.customer_state_setup or {}
    if not setup.get("oracle_applicability", {}).get("coworker_reply_quality", True):
        return [
            CoworkerOracleResult(
                "coworker_not_applicable",
                "not_applicable",
                "coworker_reply_quality",
                "oracle not applicable",
                blocker=False,
            )
        ]

    results: list[CoworkerOracleResult] = []
    results.extend(evaluate_input_realism_oracles(scenario=scenario))
    results.extend(evaluate_scenario_family_alignment(scenario=scenario))
    results.extend(evaluate_valid_reference_oracle(scenario=scenario))
    results.extend(
        evaluate_semantic_human_review_oracles(
            scenario=scenario,
            reply_body=reply_body,
            plan_v2=plan_v2,
        )
    )
    body = _normalize(reply_body)

    for marker in setup.get("required_markers") or []:
        synonyms = _MARKER_SYNONYMS.get(marker.lower(), (marker.lower(),))
        ok = any(term in body for term in synonyms)
        results.append(
            CoworkerOracleResult(
                f"required_marker_{marker}",
                "pass" if ok else "fail",
                "service_specificity",
                marker,
            )
        )

    for marker in setup.get("forbidden_markers") or []:
        ok = marker.lower() not in body
        results.append(
            CoworkerOracleResult(
                f"forbidden_marker_{marker}",
                "pass" if ok else "fail",
                "conversation_quality",
                marker,
            )
        )

    if setup.get("forbid_name_request"):
        bad = bool(re.search(r"\b(ditt namn|ditt fullständiga namn)\b", body))
        results.append(
            CoworkerOracleResult(
                "no_unjustified_name_request",
                "fail" if bad else "pass",
                "question_utility",
                "name",
            )
        )

    if setup.get("forbid_phone_request"):
        bad = bool(re.search(r"\b(telefon|mobilnummer)\b", body))
        results.append(
            CoworkerOracleResult(
                "no_unjustified_phone_request",
                "fail" if bad else "pass",
                "question_utility",
                "phone",
            )
        )

    if plan_v2 is not None:
        expected_language = "en" if (plan_v2.language or "sv").lower().startswith("en") else "sv"
        normalized_body = body
        for label in plan_v2.question_surface_labels or plan_v2.selected_question_labels:
            if not label or plan_v2.service_family == "job_status":
                continue
            if label.lower() in normalized_body:
                continue
            tokens = [t for t in re.split(r"\W+", label.lower()) if len(t) > 4]
            if tokens and any(t in normalized_body for t in tokens[:2]):
                continue
            results.append(
                CoworkerOracleResult(
                    "plan_question_present",
                    "fail",
                    "plan_fidelity",
                    label,
                )
            )

        metadata_issues = detect_internal_metadata_leaks(reply_body)
        results.append(
            CoworkerOracleResult(
                "no_internal_metadata_leak",
                "fail" if metadata_issues else "pass",
                "surface_quality",
                ";".join(metadata_issues[:3]) or "clean",
            )
        )
        mixed = detect_mixed_language(reply_body, expected_language=expected_language)
        results.append(
            CoworkerOracleResult(
                "single_reply_language",
                "fail" if mixed else "pass",
                "surface_quality",
                ";".join(mixed[:3]) or expected_language,
            )
        )
        placeholder_issues = detect_unresolved_placeholders(reply_body)
        semantic_placeholder_issues = detect_semantic_placeholders(reply_body)
        results.append(
            CoworkerOracleResult(
                "unresolved_semantic_placeholder",
                "fail" if semantic_placeholder_issues else "pass",
                "surface_quality",
                ";".join(semantic_placeholder_issues[:3]) or "clean",
            )
        )
        results.append(
            CoworkerOracleResult(
                "no_unresolved_placeholder",
                "fail" if placeholder_issues else "pass",
                "surface_quality",
                ";".join(placeholder_issues[:3]) or "clean",
            )
        )
        validation = validate_post_render_reply(plan=plan_v2, body=reply_body)
        selected_known = [
            issue for issue in validation.get("issues", []) if issue.startswith("reask_known_fact:")
        ]
        results.append(
            CoworkerOracleResult(
                "selected_known_fact_conflict",
                "fail" if selected_known else "pass",
                "question_utility",
                ";".join(selected_known[:3]) or "clean",
            )
        )
        pronoun_issues = [
            issue for issue in validation.get("issues", []) if issue.startswith("pronoun_register:")
        ]
        results.append(
            CoworkerOracleResult(
                "pronoun_register_consistency",
                "fail" if pronoun_issues else "pass",
                "surface_quality",
                ";".join(pronoun_issues[:3]) or "consistent",
            )
        )
        grammar_issues = [
            issue for issue in validation.get("issues", []) if issue.startswith("grammatical_question_composition:")
        ]
        results.append(
            CoworkerOracleResult(
                "grammatical_question_composition",
                "fail" if grammar_issues else "pass",
                "surface_quality",
                ";".join(grammar_issues[:3]) or "natural",
            )
        )
        extracted = extract_customer_facts(
            input_data={
                "subject": scenario.input.subject,
                "message_text": scenario.input.message_text,
            }
        )
        reask_hits = [
            field
            for field in extracted.known_question_fields
            if field in (plan_v2.selected_questions or ())
        ]
        results.append(
            CoworkerOracleResult(
                "input_fact_reask",
                "fail" if reask_hits else "pass",
                "question_utility",
                ",".join(reask_hits[:3]) or "clean",
            )
        )
        robotic = detect_robotic_template_composition(reply_body)
        results.append(
            CoworkerOracleResult(
                "natural_surface_text",
                "fail" if robotic else "pass",
                "surface_quality",
                ";".join(robotic[:3]) or "natural",
            )
        )
        kv_issues = detect_key_value_fragments(reply_body)
        unlocalized = detect_unlocalized_fact_labels(reply_body)
        results.append(
            CoworkerOracleResult(
                "customer_facing_localization_complete",
                "fail" if kv_issues or unlocalized else "pass",
                "surface_quality",
                ";".join((kv_issues + unlocalized)[:3]) or "localized",
            )
        )
        if plan_v2.case_reference_phrase and re.search(
            r"\b(ärendenummer|case reference|order reference)\b", body
        ):
            results.append(
                CoworkerOracleResult(
                    "no_known_fact_reask",
                    "fail",
                    "question_utility",
                    "case_reference",
                )
            )
        if "kompletteringen" in body and "continuation_with_new_facts" not in " ".join(
            plan_v2.language_decision_evidence
        ):
            if "kompletterande information" not in (plan_v2.acknowledgement_statement or "").lower():
                if "kompletteringen" in body:
                    results.append(
                        CoworkerOracleResult(
                            "acknowledgement_evidence_fidelity",
                            "fail",
                            "conversation_quality",
                            "unsupported_completion_ack",
                        )
                    )
        surface = validate_customer_surface(reply_body, expected_language=expected_language)
        if not surface["passed"]:
            results.append(
                CoworkerOracleResult(
                    "customer_surface_contract",
                    "fail",
                    "surface_quality",
                    ";".join(surface["issues"][:3]),
                )
            )

    if provenance is not None and provenance.use_fallback:
        results.append(
            CoworkerOracleResult(
                "fallback_used",
                "advisory",
                "fallback_usage",
                provenance.fallback_reason or "fallback",
                blocker=False,
            )
        )

    if not body:
        results.append(
            CoworkerOracleResult(
                "non_empty_reply",
                "fail",
                "conversation_quality",
                "empty body",
            )
        )

    return results


_NEXT_STEP_SKELETON_MARKERS: tuple[tuple[str, str], ...] = (
    ("takets förutsättningar", "<NEXT_SOLAR>"),
    ("offertprocessen", "<NEXT_SOLAR_FOLLOWUP>"),
    ("sista uppgifterna", "<NEXT_SOLAR_CONT>"),
    ("kompatibilitet med befintligt system", "<NEXT_BATTERY>"),
    ("installationsförutsättningar", "<NEXT_EV>"),
    ("felbilden", "<NEXT_SUPPORT>"),
    ("supportärendet", "<NEXT_SUPPORT_FOLLOWUP>"),
    ("ärendets aktuella status", "<NEXT_STATUS>"),
    ("fler kontaktuppgifter", "<NEXT_STATUS_NO_CONTACT>"),
    ("reklamationen", "<NEXT_COMPLAINT>"),
    ("rätt tjänst", "<NEXT_CONSULT>"),
    ("filen igen", "<NEXT_ATTACHMENT>"),
    ("roof conditions", "<NEXT_SOLAR>"),
    ("battery", "<NEXT_BATTERY>"),
    ("installation conditions", "<NEXT_EV>"),
    ("fault picture", "<NEXT_SUPPORT>"),
    ("case status", "<NEXT_STATUS>"),
)


def _next_step_skeleton_tag(line: str) -> str | None:
    lowered = line.lower()
    if _GENERIC_NEXT_STEP_SV in lowered:
        return "<NEXT_GENERIC>"
    for marker, tag in _NEXT_STEP_SKELETON_MARKERS:
        if marker in lowered:
            return tag
    return None


def _structural_skeleton(body: str) -> str:
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("-"):
            lines.append("<Q>")
        elif stripped.lower().startswith("hej") or stripped.lower().startswith("hi"):
            lines.append("<GREET>")
        elif "vänliga hälsningar" in stripped.lower() or "kind regards" in stripped.lower():
            lines.append("<CLOSE>")
        elif "tack" in stripped.lower() or "thank" in stripped.lower():
            lines.append("<ACK>")
        else:
            next_tag = _next_step_skeleton_tag(stripped)
            lines.append(next_tag or "<BODY>")
    return "|".join(lines)


def dominant_generic_phrase_rate(bodies: list[str]) -> float:
    if not bodies:
        return 0.0
    hits = sum(1 for body in bodies if _GENERIC_NEXT_STEP_SV in (body or "").lower())
    return hits / len(bodies)


def exact_duplicate_reply_groups(bodies: list[str]) -> list[list[int]]:
    groups: dict[str, list[int]] = {}
    for idx, body in enumerate(bodies):
        key = _normalize(body)
        groups.setdefault(key, []).append(idx)
    return [indices for indices in groups.values() if len(indices) > 1]


def template_similarity_ratio(bodies: list[str], *, families: list[str] | None = None) -> float:
    if len(bodies) < 2:
        return 0.0
    skeletons = [_structural_skeleton(body) for body in bodies]
    if not families or len(families) != len(bodies):
        unique = len(set(skeletons))
        return 1.0 - (unique / len(skeletons))

    # Only penalize identical skeletons across different families.
    cross_pairs = 0
    mismatched = 0
    for i in range(len(skeletons)):
        for j in range(i + 1, len(skeletons)):
            if families[i] == families[j]:
                continue
            cross_pairs += 1
            if skeletons[i] == skeletons[j]:
                mismatched += 1
    if cross_pairs == 0:
        return 0.0
    return mismatched / cross_pairs


def aggregate_coworker_results(results: list[CoworkerOracleResult]) -> dict[str, Any]:
    blockers = [
        {"oracle_id": r.name, "status": r.status, "detail": r.detail, "category": r.category}
        for r in results
        if r.blocker and r.status == "fail"
    ]
    advisory = [
        {"oracle_id": r.name, "status": r.status, "detail": r.detail}
        for r in results
        if not r.blocker or r.status != "fail"
    ]
    return {
        "passed": not blockers,
        "blockers": [b["oracle_id"] for b in blockers],
        "blocking_failures": blockers,
        "advisory_results": advisory,
        "results": [r.to_dict() for r in results],
    }


def expected_reply_language(
    *,
    scenario: ProfileScenario,
    plan_v2: CustomerReplyPlanV2 | None,
    input_data: dict[str, Any] | None = None,
    profile_default_language: str = "sv",
) -> str:
    if plan_v2 is not None and plan_v2.language:
        return "en" if plan_v2.language.lower().startswith("en") else "sv"
    if input_data is not None:
        return authoritative_reply_language(
            input_data=input_data,
            profile_default_language=profile_default_language,
        ).language
    lang = (scenario.input.language or profile_default_language).lower()
    return "en" if lang.startswith("en") else "sv"


def summarize_surface_quality_metrics(
    *,
    reply_body: str,
    expected_language: str,
    oracle_results: list[CoworkerOracleResult],
) -> dict[str, Any]:
    mixed = detect_mixed_language(reply_body, expected_language=expected_language)
    metadata = detect_internal_metadata_leaks(reply_body)
    unlocalized = detect_unlocalized_fact_labels(reply_body)
    placeholders = detect_unresolved_placeholders(reply_body)
    blocking = [r for r in oracle_results if r.blocker and r.status == "fail"]
    return {
        "expected_language": expected_language,
        "mixed_language_violations": len(mixed),
        "mixed_language_issues": mixed,
        "internal_metadata_violations": len(metadata),
        "internal_metadata_issues": metadata,
        "unlocalized_fact_label_violations": len(unlocalized),
        "unlocalized_fact_label_issues": unlocalized,
        "unresolved_placeholder_violations": len(placeholders),
        "blocking_oracle_failures": len(blocking),
        "blocking_oracle_ids": [r.name for r in blocking],
        "aggregation_consistent": (len(mixed) == 0 or any(r.name == "single_reply_language" and r.status == "fail" for r in oracle_results)),
    }
