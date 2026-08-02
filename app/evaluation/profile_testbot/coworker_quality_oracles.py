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
    detect_unlocalized_fact_labels,
    detect_unresolved_placeholders,
    validate_customer_surface,
)
from app.workflows.reply_quality.reply_language import authoritative_reply_language
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.provenance import ReplyRenderProvenance

THRESHOLD_VERSION = "coworker_reply_thresholds_v3"

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


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _structural_skeleton(body: str) -> str:
    lines = []
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("-"):
            lines.append("<Q>")
        elif stripped.lower().startswith("hej"):
            lines.append("<GREET>")
        elif "vänliga hälsningar" in stripped.lower():
            lines.append("<CLOSE>")
        elif "tack" in stripped.lower():
            lines.append("<ACK>")
        else:
            lines.append("<BODY>")
    return "|".join(lines)


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
        for label in plan_v2.question_surface_labels or plan_v2.selected_question_labels:
            if label.lower() not in body and plan_v2.service_family != "job_status":
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
        results.append(
            CoworkerOracleResult(
                "no_unresolved_placeholder",
                "fail" if placeholder_issues else "pass",
                "surface_quality",
                ";".join(placeholder_issues[:3]) or "clean",
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
