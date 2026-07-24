"""Hermetic regression tests for Live LLM report aggregation semantics."""

from __future__ import annotations

from app.evaluation.live.constants import TELEMETRY_APP_LIVE_LLM
from app.evaluation.live.llm_report import (
    _summarize_llm_events,
    build_live_eval_llm_failure_report,
    build_live_eval_llm_report,
)

_EVAL_RUN_ID = "ed492673-bcca-4fb2-be3d-3e4653dcb709"
_PROMPTS = (
    "classification_v1",
    "entity_extraction_v1",
    "lead_scoring_v1",
    "decisioning_v1",
)
_METRICS = (
    (374, 39, 413, 2050, "8c4729b7a748741e52cc150db4eb8401b3ff3c2b13da877d551bd6f5ad5accfc"),
    (529, 114, 643, 1750, "b7cd7e1cda677e82e0f483160dde122fedff2484c2fd10e4d8f591e5d015a3b6"),
    (705, 75, 780, 1003, "2b11bba5f102284628ed56c84cff9d56619dd9501204537b98df4b2da93208ad"),
    (826, 87, 913, 1656, "8d8b4dc5638557ef91dee350b291a1b82e53328bc2a106859fe7810eaebbfa65"),
)


def _operation_key(prompt_name: str, ordinal: int) -> str:
    return f"{_EVAL_RUN_ID}:{TELEMETRY_APP_LIVE_LLM}:{prompt_name}:{ordinal}"


def _llm_event(
    *,
    operation_key: str,
    prompt_name: str,
    outcome: str,
    metadata: dict | None = None,
) -> dict:
    return {
        "category": TELEMETRY_APP_LIVE_LLM,
        "operation_key": operation_key,
        "operation": prompt_name,
        "outcome": outcome,
        "metadata": metadata or {},
    }


def _reservation_metadata(*, ordinal: int, prompt_name: str) -> dict:
    return {
        "ordinal": ordinal,
        "prompt_name": prompt_name,
        "llm_provider": "openai",
        "llm_requested_model": "gpt-4o-mini",
    }


def _terminal_metadata(
    *,
    ordinal: int,
    prompt_name: str,
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    latency_ms: int,
    output_hash: str,
) -> dict:
    return {
        "ordinal": ordinal,
        "prompt_name": prompt_name,
        "llm_provider": "openai",
        "llm_requested_model": "gpt-4o-mini",
        "returned_model": "gpt-4o-mini-2024-07-18",
        "finish_reason": "stop",
        "schema_validation_status": "passed",
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "latency_ms": latency_ms,
        "output_hash": output_hash,
        "retry_count": 0,
        "fallback_used": False,
    }


def _full_success_events() -> list[dict]:
    events: list[dict] = []
    for ordinal, prompt_name in enumerate(_PROMPTS, start=1):
        input_tokens, output_tokens, total_tokens, latency_ms, output_hash = _METRICS[ordinal - 1]
        operation_key = _operation_key(prompt_name, ordinal)
        events.append(
            _llm_event(
                operation_key=operation_key,
                prompt_name=prompt_name,
                outcome="in_progress",
                metadata=_reservation_metadata(ordinal=ordinal, prompt_name=prompt_name),
            )
        )
        events.append(
            _llm_event(
                operation_key=operation_key,
                prompt_name=prompt_name,
                outcome="succeeded",
                metadata=_terminal_metadata(
                    ordinal=ordinal,
                    prompt_name=prompt_name,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency_ms,
                    output_hash=output_hash,
                ),
            )
        )
    return events


def test_full_success_groups_logical_operations():
    operations, totals = _summarize_llm_events(_full_success_events())

    assert totals == {
        "attempted": 4,
        "succeeded": 4,
        "failed": 0,
        "outcome_unknown": 0,
        "input_tokens": 2434,
        "output_tokens": 315,
        "total_tokens": 2749,
        "latency_ms": 6459,
    }
    assert len(operations) == 4
    assert {op["operation_key"] for op in operations} == {
        _operation_key(prompt, index) for index, prompt in enumerate(_PROMPTS, start=1)
    }
    assert [op["ordinal"] for op in operations] == [1, 2, 3, 4]
    assert [op["prompt_name"] for op in operations] == list(_PROMPTS)

    for operation, metrics in zip(operations, _METRICS, strict=True):
        input_tokens, output_tokens, total_tokens, latency_ms, output_hash = metrics
        assert operation["state"] == "succeeded"
        assert operation["outcome"] == "succeeded"
        assert operation["provider"] == "openai"
        assert operation["requested_model"] == "gpt-4o-mini"
        assert operation["returned_model"] == "gpt-4o-mini-2024-07-18"
        assert operation["finish_reason"] == "stop"
        assert operation["schema_validation_status"] == "passed"
        assert operation["retry_count"] == 0
        assert operation["used_fallback"] is False
        assert operation["input_tokens"] == input_tokens
        assert operation["output_tokens"] == output_tokens
        assert operation["total_tokens"] == total_tokens
        assert operation["latency_ms"] == latency_ms
        assert operation["output_hash"] == output_hash
        assert len(operation["output_hash"]) == 64


def test_in_progress_only_operation():
    operation_key = _operation_key("classification_v1", 1)
    events = [
        _llm_event(
            operation_key=operation_key,
            prompt_name="classification_v1",
            outcome="in_progress",
            metadata=_reservation_metadata(ordinal=1, prompt_name="classification_v1"),
        )
    ]

    operations, totals = _summarize_llm_events(events)

    assert totals["attempted"] == 1
    assert totals["succeeded"] == 0
    assert totals["failed"] == 0
    assert totals["outcome_unknown"] == 0
    assert len(operations) == 1
    assert operations[0]["state"] == "in_progress"
    assert operations[0]["requested_model"] == "gpt-4o-mini"
    assert operations[0]["provider"] == "openai"


def test_failed_operation_preserves_reservation_metadata():
    operation_key = _operation_key("classification_v1", 1)
    events = [
        _llm_event(
            operation_key=operation_key,
            prompt_name="classification_v1",
            outcome="in_progress",
            metadata=_reservation_metadata(ordinal=1, prompt_name="classification_v1"),
        ),
        _llm_event(
            operation_key=operation_key,
            prompt_name="classification_v1",
            outcome="failed",
            metadata={
                "ordinal": 1,
                "prompt_name": "classification_v1",
                "failure_reason": "schema_validation_failed",
                "schema_validation_status": "failed",
            },
        ),
    ]

    operations, totals = _summarize_llm_events(events)

    assert totals["attempted"] == 1
    assert totals["failed"] == 1
    assert totals["succeeded"] == 0
    assert len(operations) == 1
    assert operations[0]["state"] == "failed"
    assert operations[0]["requested_model"] == "gpt-4o-mini"
    assert operations[0]["provider"] == "openai"
    assert operations[0]["schema_validation_status"] == "failed"
    assert operations[0]["failure_reason"] == "schema_validation_failed"


def test_outcome_unknown_operation():
    operation_key = _operation_key("classification_v1", 1)
    events = [
        _llm_event(
            operation_key=operation_key,
            prompt_name="classification_v1",
            outcome="in_progress",
            metadata=_reservation_metadata(ordinal=1, prompt_name="classification_v1"),
        ),
        _llm_event(
            operation_key=operation_key,
            prompt_name="classification_v1",
            outcome="outcome_unknown",
            metadata={
                "ordinal": 1,
                "prompt_name": "classification_v1",
                "failure_reason": "timeout",
            },
        ),
    ]

    operations, totals = _summarize_llm_events(events)

    assert totals["attempted"] == 1
    assert totals["outcome_unknown"] == 1
    assert totals["succeeded"] == 0
    assert len(operations) == 1
    assert operations[0]["state"] == "outcome_unknown"


def test_blocked_event_does_not_create_operation():
    events = [
        _llm_event(
            operation_key=_operation_key("classification_v1", 1),
            prompt_name="classification_v1",
            outcome="blocked",
            metadata={"reason": "budget_exhausted"},
        )
    ]

    operations, totals = _summarize_llm_events(events)

    assert totals["attempted"] == 0
    assert operations == []


def test_failure_report_live_llm_calls_use_logical_operations():
    events = [
        _llm_event(
            operation_key=_operation_key("classification_v1", 1),
            prompt_name="classification_v1",
            outcome="in_progress",
            metadata=_reservation_metadata(ordinal=1, prompt_name="classification_v1"),
        ),
        _llm_event(
            operation_key=_operation_key("classification_v1", 1),
            prompt_name="classification_v1",
            outcome="succeeded",
            metadata=_terminal_metadata(
                ordinal=1,
                prompt_name="classification_v1",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                latency_ms=100,
                output_hash="a" * 64,
            ),
        ),
        _llm_event(
            operation_key=_operation_key("entity_extraction_v1", 2),
            prompt_name="entity_extraction_v1",
            outcome="in_progress",
            metadata=_reservation_metadata(ordinal=2, prompt_name="entity_extraction_v1"),
        ),
        _llm_event(
            operation_key=_operation_key("entity_extraction_v1", 2),
            prompt_name="entity_extraction_v1",
            outcome="succeeded",
            metadata=_terminal_metadata(
                ordinal=2,
                prompt_name="entity_extraction_v1",
                input_tokens=20,
                output_tokens=6,
                total_tokens=26,
                latency_ms=200,
                output_hash="b" * 64,
            ),
        ),
        _llm_event(
            operation_key=_operation_key("lead_scoring_v1", 3),
            prompt_name="lead_scoring_v1",
            outcome="in_progress",
            metadata=_reservation_metadata(ordinal=3, prompt_name="lead_scoring_v1"),
        ),
    ]

    payload = build_live_eval_llm_failure_report(
        evaluation_run_id=_EVAL_RUN_ID,
        scenario_id="S01_lead_laddbox_quality",
        failure_stage="assertions",
        failure_category="assertion_failed",
        observation={"events": events},
    )

    assert payload["token_usage"]["attempted"] == 3
    assert payload["live_llm_calls"] == 3
    assert payload["llm_operations"] == 3
    assert len(payload["operations"]) == 3


def test_legacy_metadata_aliases_are_mapped():
    operation_key = _operation_key("classification_v1", 1)
    events = [
        _llm_event(
            operation_key=operation_key,
            prompt_name="classification_v1",
            outcome="in_progress",
            metadata={
                "ordinal": 1,
                "provider": "openai",
                "requested_model": "gpt-4o-mini",
            },
        ),
        _llm_event(
            operation_key=operation_key,
            prompt_name="classification_v1",
            outcome="succeeded",
            metadata={
                "ordinal": 1,
                "provider": "openai",
                "requested_model": "gpt-4o-mini",
                "returned_model": "gpt-4o-mini-2024-07-18",
                "finish_reason": "stop",
                "schema_validation_status": "passed",
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "latency_ms": 100,
                "output_hash": "c" * 64,
            },
        ),
    ]

    operations, totals = _summarize_llm_events(events)

    assert totals["attempted"] == 1
    assert operations[0]["provider"] == "openai"
    assert operations[0]["requested_model"] == "gpt-4o-mini"


def test_conflicting_terminal_outcomes_are_not_silent_success():
    operation_key = _operation_key("classification_v1", 1)
    events = [
        _llm_event(
            operation_key=operation_key,
            prompt_name="classification_v1",
            outcome="in_progress",
            metadata=_reservation_metadata(ordinal=1, prompt_name="classification_v1"),
        ),
        _llm_event(
            operation_key=operation_key,
            prompt_name="classification_v1",
            outcome="succeeded",
            metadata=_terminal_metadata(
                ordinal=1,
                prompt_name="classification_v1",
                input_tokens=10,
                output_tokens=5,
                total_tokens=15,
                latency_ms=100,
                output_hash="d" * 64,
            ),
        ),
        _llm_event(
            operation_key=operation_key,
            prompt_name="classification_v1",
            outcome="failed",
            metadata={
                "ordinal": 1,
                "prompt_name": "classification_v1",
                "failure_reason": "schema_validation_failed",
            },
        ),
    ]

    operations, totals = _summarize_llm_events(events)

    assert totals["attempted"] == 1
    assert totals["succeeded"] == 0
    assert totals["failed"] == 1
    assert operations[0]["state"] == "conflict"
    assert operations[0]["failure_reason"].startswith("conflicting_terminal_outcomes:")


def test_success_report_uses_grouped_operations():
    report = build_live_eval_llm_report(
        evaluation_run_id=_EVAL_RUN_ID,
        run={
            "scenario_id": "S01_lead_laddbox_quality",
            "transport_mode": "fixture_input",
            "ai_mode": "live_llm",
            "llm_provider": "openai",
            "llm_requested_model": "gpt-4o-mini",
        },
        observation={"events": _full_success_events(), "job": {}},
        result="passed",
    )

    assert report.token_usage["attempted"] == 4
    assert len(report.operations) == 4
    assert report.report_schema_version == "2f.3.llm"
