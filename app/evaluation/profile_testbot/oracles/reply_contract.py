"""Reply contract oracle for profile-driven testbot."""

from __future__ import annotations

from app.evaluation.profile_testbot.oracles.hard_safety import OracleResult
from app.evaluation.profile_testbot.profile_contract import CustomerProfileSnapshot
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


def evaluate_reply_contract(
    *,
    scenario: ProfileScenario,
    profile: CustomerProfileSnapshot,
    reply_text: str,
) -> list[OracleResult]:
    results: list[OracleResult] = []
    text = (reply_text or "").lower()
    if scenario.expected_send_behavior in {"no_reply", "reject", "hold", "observe_only"}:
        results.append(
            OracleResult(
                name="no_reply_expected",
                status="pass" if not text.strip() else "fail",
                detail="reply present when none expected",
                blocker=True,
            )
        )
        return results
    for fact in scenario.required_reply_facts:
        ok = fact == "acknowledgement" and any(
            phrase.lower() in text for phrase in profile.safe_acknowledgements
        )
        results.append(
            OracleResult(
                name=f"required_fact_{fact}",
                status="pass" if ok else "fail",
                detail=f"required={fact}",
                blocker=True,
            )
        )
    for claim in scenario.forbidden_reply_claims:
        results.append(
            OracleResult(
                name=f"forbidden_claim_{claim}",
                status="pass" if claim.lower() not in text else "fail",
                detail=claim,
                blocker=True,
            )
        )
    return results
