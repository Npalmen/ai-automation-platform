"""Gmail send payload builders for profile semi-auto live campaigns."""

from __future__ import annotations

from app.evaluation.live.subject_parser import build_subject_with_token
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


def build_profile_testbot_message_body(
    *,
    scenario: ProfileScenario,
    evaluation_run_id: str,
    campaign_id: str,
) -> str:
    marker = f"<!-- KROWOLF_EVAL:evaluation_run_id={evaluation_run_id} -->"
    campaign_marker = f"<!-- KROWOLF_PROFILE_TESTBOT:campaign_id={campaign_id} -->"
    scenario_marker = f"<!-- KROWOLF_PROFILE_TESTBOT:scenario_id={scenario.scenario_id} -->"
    profile_marker = f"<!-- KROWOLF_PROFILE:{scenario.profile_id} -->"
    text = (scenario.input.message_text or "").strip()
    return "\n".join([marker, campaign_marker, scenario_marker, profile_marker, text])


def build_profile_testbot_subject(
    *,
    scenario: ProfileScenario,
    evaluation_run_id: str,
    attempt_id: int = 1,
) -> str:
    return build_subject_with_token(
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario.scenario_id,
        attempt_id=attempt_id,
        base_subject=scenario.input.subject,
    )
