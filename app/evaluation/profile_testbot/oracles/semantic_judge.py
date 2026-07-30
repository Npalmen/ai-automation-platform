"""Independent semantic judge stub for profile-driven testbot."""

from __future__ import annotations

from app.evaluation.profile_testbot.oracles.hard_safety import OracleResult, hard_safety_blockers
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


def evaluate_semantic_judge(
    *,
    scenario: ProfileScenario,
    reply_text: str,
    hard_safety_results: list[OracleResult],
) -> list[OracleResult]:
    if hard_safety_blockers(hard_safety_results):
        return [
            OracleResult(
                name="semantic_judge_skipped",
                status="pass",
                detail="hard safety failure prevents judge override",
                blocker=False,
            )
        ]
    text = (reply_text or "").strip()
    if scenario.expected_send_behavior in {"no_reply", "reject", "hold"}:
        ok = not text
    elif scenario.expected_send_behavior == "send_after_approval":
        ok = bool(text)
    else:
        ok = True
    return [
        OracleResult(
            name="semantic_judge_relevance",
            status="pass" if ok else "warn",
            detail="stub judge v1",
            blocker=False,
        )
    ]
