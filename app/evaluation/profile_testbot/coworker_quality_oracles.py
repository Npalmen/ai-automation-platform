"""Blocking coworker reply quality oracles (Todo H)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.provenance import ReplyRenderProvenance

THRESHOLD_VERSION = "coworker_reply_thresholds_v1"

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
        ok = marker.lower() in body
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
        for label in plan_v2.selected_question_labels:
            if label.lower() not in body:
                results.append(
                    CoworkerOracleResult(
                        "plan_question_present",
                        "fail",
                        "plan_fidelity",
                        label,
                    )
                )
        for fact in plan_v2.facts_not_allowed_to_repeat:
            token = fact.replace("_", " ")
            if len(token) > 4 and token in body and f"location:{token}" not in body:
                # advisory only unless explicit re-ask pattern
                pass

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
    blockers = [r.name for r in results if r.blocker and r.status == "fail"]
    return {
        "passed": not blockers,
        "blockers": blockers,
        "results": [r.to_dict() for r in results],
    }
