"""Package-level precheck aggregation for digital-coworker human-review packs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from app.evaluation.profile_testbot.coworker_quality_oracles import (
    COWORKER_THRESHOLDS,
    dominant_generic_phrase_rate,
    exact_duplicate_reply_groups,
    template_similarity_ratio,
)

PACKAGE_THRESHOLD_VERSION = "coworker_package_thresholds_v1"

# Hermetic R1 baseline (120 scenarios): dominant_generic_phrase_rate≈0.567,
# exact_duplicate_groups≈26 — driven by shared hermetic next-step phrasing.
# Live 40-pack gates are tighter: block cross-family byte duplicates and
# excessive generic next-step reuse while allowing same-family continuity.
PACKAGE_THRESHOLDS: dict[str, float | int] = {
    "fallback_rate_max": COWORKER_THRESHOLDS["fallback_rate_max"],
    "dominant_generic_phrase_rate_max": 0.50,
    "dominant_acknowledgement_rate_max": 0.55,
    "dominant_next_step_phrase_rate_max": 0.50,
    "exact_duplicate_groups_max": 8,
    "exact_duplicate_reply_count_max": 16,
    "cross_family_exact_duplicate_pairs_max": 0,
    "template_similarity_max": COWORKER_THRESHOLDS["template_similarity_max"],
}

_GENERIC_ACK_SV = "tack för att ni hör av er"
_GENERIC_ACK_EN = "thank you for your message"
_GENERIC_NEXT_STEP_SV = "när vi har det underlaget går vi igenom förutsättningarna och återkommer"


def _normalize(body: str) -> str:
    return " ".join((body or "").lower().split())


def dominant_acknowledgement_rate(bodies: list[str]) -> float:
    if not bodies:
        return 0.0
    hits = sum(
        1
        for body in bodies
        if _GENERIC_ACK_SV in (body or "").lower() or _GENERIC_ACK_EN in (body or "").lower()
    )
    return hits / len(bodies)


def dominant_next_step_phrase_rate(bodies: list[str]) -> float:
    if not bodies:
        return 0.0
    hits = sum(1 for body in bodies if _GENERIC_NEXT_STEP_SV in (body or "").lower())
    return hits / len(bodies)


def exact_duplicate_reply_count(groups: list[list[int]]) -> int:
    return sum(len(g) for g in groups)


def cross_family_exact_duplicate_pairs(
    bodies: list[str],
    *,
    families: list[str],
) -> list[tuple[int, int, str, str]]:
    pairs: list[tuple[int, int, str, str]] = []
    norm_map: dict[str, list[int]] = {}
    for idx, body in enumerate(bodies):
        key = _normalize(body)
        norm_map.setdefault(key, []).append(idx)
    for indices in norm_map.values():
        if len(indices) < 2:
            continue
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                a, b = indices[i], indices[j]
                if families[a] != families[b]:
                    pairs.append((a, b, families[a], families[b]))
    return pairs


def multi_turn_vs_first_contact_duplicates(
    bodies: list[str],
    *,
    thread_states: list[str],
) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    norm_map: dict[str, list[int]] = {}
    for idx, body in enumerate(bodies):
        norm_map.setdefault(_normalize(body), []).append(idx)
    for indices in norm_map.values():
        if len(indices) < 2:
            continue
        for i in range(len(indices)):
            for j in range(i + 1, len(indices)):
                a, b = indices[i], indices[j]
                a_cont = thread_states[a] == "continuation"
                b_cont = thread_states[b] == "continuation"
                if a_cont != b_cont:
                    pairs.append((a, b))
    return pairs


@dataclass
class PackagePrecheckResult:
    package_precheck_pass: bool
    scenario_oracles_pass: bool
    fallback_rate_pass: bool
    provider_integrity_pass: bool
    provenance_pass: bool
    duplication_gate_pass: bool
    dominant_phrase_gate_pass: bool
    aggregation_consistent: bool
    fallback_rate: float
    dominant_generic_phrase_rate: float
    dominant_acknowledgement_rate: float
    dominant_next_step_phrase_rate: float
    exact_duplicate_groups: int
    exact_duplicate_reply_count: int
    cross_family_exact_duplicate_pairs: int
    template_similarity: float
    gate_failures: list[str] = field(default_factory=list)
    renderer_distribution: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "package_precheck_pass": self.package_precheck_pass,
            "scenario_oracles_pass": self.scenario_oracles_pass,
            "renderer_pass": self.fallback_rate_pass and self.provider_integrity_pass,
            "fallback_rate_pass": self.fallback_rate_pass,
            "provider_integrity_pass": self.provider_integrity_pass,
            "provenance_pass": self.provenance_pass,
            "duplication_gate_pass": self.duplication_gate_pass,
            "dominant_phrase_gate_pass": self.dominant_phrase_gate_pass,
            "aggregation_consistent": self.aggregation_consistent,
            "fallback_rate": self.fallback_rate,
            "dominant_generic_phrase_rate": self.dominant_generic_phrase_rate,
            "dominant_acknowledgement_rate": self.dominant_acknowledgement_rate,
            "dominant_next_step_phrase_rate": self.dominant_next_step_phrase_rate,
            "exact_duplicate_groups": self.exact_duplicate_groups,
            "exact_duplicate_reply_count": self.exact_duplicate_reply_count,
            "cross_family_exact_duplicate_pairs": self.cross_family_exact_duplicate_pairs,
            "template_similarity": self.template_similarity,
            "gate_failures": self.gate_failures,
            "renderer_distribution": self.renderer_distribution,
            "threshold_version": PACKAGE_THRESHOLD_VERSION,
            "thresholds": PACKAGE_THRESHOLDS,
        }


def evaluate_package_precheck(
    *,
    scenario_pass: Sequence[bool],
    bodies: Sequence[str],
    families: Sequence[str],
    thread_states: Sequence[str],
    use_fallback: Sequence[bool],
    llm_used: Sequence[bool],
    invocation_attempted: Sequence[bool],
    provider_outcomes: Sequence[str],
    live_validation_outcomes: Sequence[str | None],
    aggregation_consistent: Sequence[bool],
    renderer_distribution: dict[str, int] | None = None,
) -> PackagePrecheckResult:
    n = len(scenario_pass)
    gate_failures: list[str] = []

    scenario_oracles_pass = all(scenario_pass)
    if not scenario_oracles_pass:
        gate_failures.append("scenario_oracles_not_all_pass")

    fallback_count = sum(1 for f in use_fallback if f)
    fallback_rate = fallback_count / max(n, 1)
    fallback_rate_pass = fallback_rate <= float(PACKAGE_THRESHOLDS["fallback_rate_max"])
    if not fallback_rate_pass:
        gate_failures.append(
            f"fallback_rate {fallback_rate:.3f} > {PACKAGE_THRESHOLDS['fallback_rate_max']}"
        )

    provider_integrity_pass = True
    for idx in range(n):
        if invocation_attempted[idx] and provider_outcomes[idx] not in {"success", "failed", "skipped"}:
            provider_integrity_pass = False
            gate_failures.append(f"provider_outcome_unknown:scenario_{idx}")
        if llm_used[idx] and use_fallback[idx]:
            provider_integrity_pass = False
            gate_failures.append(f"llm_used_with_fallback:scenario_{idx}")
        if llm_used[idx] and live_validation_outcomes[idx] == "fail":
            provider_integrity_pass = False
            gate_failures.append(f"llm_success_after_live_validation_fail:scenario_{idx}")

    provenance_pass = (
        len(invocation_attempted) == n
        and len(provider_outcomes) == n
        and all(isinstance(v, bool) for v in invocation_attempted)
    )
    if not provenance_pass:
        gate_failures.append("provenance_incomplete")

    body_list = list(bodies)
    family_list = list(families)
    dup_groups = exact_duplicate_reply_groups(body_list)
    dup_count = exact_duplicate_reply_count(dup_groups)
    cross_pairs = cross_family_exact_duplicate_pairs(body_list, families=family_list)
    dom_generic = dominant_generic_phrase_rate(body_list)
    dom_ack = dominant_acknowledgement_rate(body_list)
    dom_next = dominant_next_step_phrase_rate(body_list)
    similarity = template_similarity_ratio(body_list, families=family_list)

    duplication_gate_pass = (
        len(dup_groups) <= int(PACKAGE_THRESHOLDS["exact_duplicate_groups_max"])
        and dup_count <= int(PACKAGE_THRESHOLDS["exact_duplicate_reply_count_max"])
        and len(cross_pairs) <= int(PACKAGE_THRESHOLDS["cross_family_exact_duplicate_pairs_max"])
        and similarity <= float(PACKAGE_THRESHOLDS["template_similarity_max"])
    )
    if len(dup_groups) > int(PACKAGE_THRESHOLDS["exact_duplicate_groups_max"]):
        gate_failures.append(
            f"exact_duplicate_groups {len(dup_groups)} > {PACKAGE_THRESHOLDS['exact_duplicate_groups_max']}"
        )
    if dup_count > int(PACKAGE_THRESHOLDS["exact_duplicate_reply_count_max"]):
        gate_failures.append(
            f"exact_duplicate_reply_count {dup_count} > {PACKAGE_THRESHOLDS['exact_duplicate_reply_count_max']}"
        )
    if cross_pairs:
        gate_failures.append(f"cross_family_exact_duplicates:{len(cross_pairs)}")
    if similarity > float(PACKAGE_THRESHOLDS["template_similarity_max"]):
        gate_failures.append(
            f"template_similarity {similarity:.3f} > {PACKAGE_THRESHOLDS['template_similarity_max']}"
        )

    dominant_phrase_gate_pass = (
        dom_generic <= float(PACKAGE_THRESHOLDS["dominant_generic_phrase_rate_max"])
        and dom_ack <= float(PACKAGE_THRESHOLDS["dominant_acknowledgement_rate_max"])
        and dom_next <= float(PACKAGE_THRESHOLDS["dominant_next_step_phrase_rate_max"])
    )
    if dom_generic > float(PACKAGE_THRESHOLDS["dominant_generic_phrase_rate_max"]):
        gate_failures.append(
            f"dominant_generic_phrase_rate {dom_generic:.3f} > {PACKAGE_THRESHOLDS['dominant_generic_phrase_rate_max']}"
        )
    if dom_ack > float(PACKAGE_THRESHOLDS["dominant_acknowledgement_rate_max"]):
        gate_failures.append(
            f"dominant_acknowledgement_rate {dom_ack:.3f} > {PACKAGE_THRESHOLDS['dominant_acknowledgement_rate_max']}"
        )
    if dom_next > float(PACKAGE_THRESHOLDS["dominant_next_step_phrase_rate_max"]):
        gate_failures.append(
            f"dominant_next_step_phrase_rate {dom_next:.3f} > {PACKAGE_THRESHOLDS['dominant_next_step_phrase_rate_max']}"
        )

    aggregation_consistent = all(aggregation_consistent)
    if not aggregation_consistent:
        gate_failures.append("aggregation_contradictions_present")

    package_precheck_pass = (
        scenario_oracles_pass
        and fallback_rate_pass
        and provider_integrity_pass
        and provenance_pass
        and duplication_gate_pass
        and dominant_phrase_gate_pass
        and aggregation_consistent
    )

    return PackagePrecheckResult(
        package_precheck_pass=package_precheck_pass,
        scenario_oracles_pass=scenario_oracles_pass,
        fallback_rate_pass=fallback_rate_pass,
        provider_integrity_pass=provider_integrity_pass,
        provenance_pass=provenance_pass,
        duplication_gate_pass=duplication_gate_pass,
        dominant_phrase_gate_pass=dominant_phrase_gate_pass,
        aggregation_consistent=aggregation_consistent,
        fallback_rate=fallback_rate,
        dominant_generic_phrase_rate=dom_generic,
        dominant_acknowledgement_rate=dom_ack,
        dominant_next_step_phrase_rate=dom_next,
        exact_duplicate_groups=len(dup_groups),
        exact_duplicate_reply_count=dup_count,
        cross_family_exact_duplicate_pairs=len(cross_pairs),
        template_similarity=similarity,
        gate_failures=gate_failures,
        renderer_distribution=dict(renderer_distribution or {}),
    )
