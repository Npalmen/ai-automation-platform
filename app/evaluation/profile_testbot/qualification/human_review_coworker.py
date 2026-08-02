"""Human review rubric tooling for coworker reply quality (Gate R2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

RUBRIC_VERSION = "coworker_human_review_v1"

DIMENSIONS: tuple[str, ...] = (
    "sounds_like_competent_coworker",
    "progresses_case",
    "useful_questions",
    "specific_without_overpromising",
    "clear_and_natural",
)

MIN_DIMENSION_SCORE = 3
MIN_FAMILY_SCORE = 3


@dataclass
class HumanReviewScore:
    scenario_id: str
    family: str
    dimension_scores: dict[str, int]
    overall_acceptable: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "family": self.family,
            "dimension_scores": self.dimension_scores,
            "overall_acceptable": self.overall_acceptable,
            "notes": self.notes,
            "rubric_version": RUBRIC_VERSION,
        }


@dataclass
class HumanReviewCampaignResult:
    overall_status: str
    reviewed_count: int
    unacceptable_count: int
    failures: list[str] = field(default_factory=list)
    scores: list[HumanReviewScore] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "reviewed_count": self.reviewed_count,
            "unacceptable_count": self.unacceptable_count,
            "failures": self.failures,
            "rubric_version": RUBRIC_VERSION,
            "dimensions": list(DIMENSIONS),
        }


def score_reply_for_review(
    *,
    scenario_id: str,
    family: str,
    reply_body: str,
    required_markers: list[str] | None = None,
) -> HumanReviewScore:
    """Deterministic advisory pre-score for hermetic human-review gate simulation."""
    body = (reply_body or "").lower()
    scores: dict[str, int] = {}
    marker_hits = sum(1 for m in (required_markers or []) if m.lower() in body)
    base = 4 if marker_hits else 3
    if "tack för din förfrågan. vi tittar" in body:
        base = 2
    if "för att vi ska kunna gå vidare behöver vi" in body:
        base = min(base, 2)
    for dim in DIMENSIONS:
        scores[dim] = base
    if any(token in body for token in ("- ditt namn", "- telefon")):
        scores["useful_questions"] = 2
    acceptable = all(score >= MIN_DIMENSION_SCORE for score in scores.values())
    return HumanReviewScore(
        scenario_id=scenario_id,
        family=family,
        dimension_scores=scores,
        overall_acceptable=acceptable,
        notes="deterministic_rubric_proxy",
    )


def evaluate_human_review_campaign(scores: list[HumanReviewScore]) -> HumanReviewCampaignResult:
    failures: list[str] = []
    unacceptable = [s for s in scores if not s.overall_acceptable]
    if unacceptable:
        failures.append(f"{len(unacceptable)} replies unacceptable")
    families: dict[str, list[int]] = {}
    for score in scores:
        families.setdefault(score.family, []).append(
            min(score.dimension_scores.values()) if score.dimension_scores else 0
        )
    for family, values in families.items():
        if values and (sum(values) / len(values)) < MIN_FAMILY_SCORE:
            failures.append(f"family {family} below minimum score")
    return HumanReviewCampaignResult(
        overall_status="PASS" if not failures else "FAIL",
        reviewed_count=len(scores),
        unacceptable_count=len(unacceptable),
        failures=failures,
        scores=scores,
    )
