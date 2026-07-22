"""Subject parser contract tests."""

from __future__ import annotations

from app.evaluation.live.subject_parser import (
    build_subject_with_token,
    parse_body_marker,
    parse_subject_token,
)


def test_parse_subject_token_roundtrip():
    subject = build_subject_with_token(
        evaluation_run_id="550e8400-e29b-41d4-a716-446655440000",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=2,
        base_subject="Lead inquiry",
    )
    parsed = parse_subject_token(subject)
    assert parsed is not None
    assert parsed.evaluation_run_id == "550e8400-e29b-41d4-a716-446655440000"
    assert parsed.scenario_id == "S01_lead_laddbox_quality"
    assert parsed.attempt_id == 2


def test_parse_subject_token_ignores_unrelated_subjects():
    assert parse_subject_token("Normal customer email") is None


def test_body_marker_is_not_authoritative_for_scenario():
    marker = parse_body_marker(
        "KROWOLF_EVAL:evaluation_run_id=550e8400-e29b-41d4-a716-446655440000"
    )
    assert marker == "550e8400-e29b-41d4-a716-446655440000"
