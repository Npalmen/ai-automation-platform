import json
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.exceptions import LLMClientError
from app.ai.llm.client import get_llm_client
from app.ai.prompts.registry import render_prompt
from app.domain.workflows.models import Job


def get_latest_processor_payload(job: Job, processor_name: str) -> dict[str, Any]:
    for item in reversed(job.processor_history):
        if item.get("processor") != processor_name:
            continue

        result = item.get("result") or {}
        payload = result.get("payload") or {}

        if isinstance(payload, dict):
            return payload

    return {}


def append_processor_result(
    job: Job,
    processor_name: str,
    result: dict[str, Any],
) -> Job:
    job.processor_history.append(
        {
            "processor": processor_name,
            "result": result,
        }
    )
    job.result = result
    return job


def apply_confidence_guardrail(payload: dict[str, Any], threshold: float = 0.6) -> dict[str, Any]:
    confidence = payload.get("confidence")

    if isinstance(confidence, (int, float)) and float(confidence) < threshold:
        payload["low_confidence"] = True
    else:
        payload["low_confidence"] = False

    return payload


def add_observability_fields(
    payload: dict[str, Any],
    *,
    processor_name: str,
    prompt_name: str,
    used_fallback: bool,
    duration_ms: int,
) -> dict[str, Any]:
    payload["processor_name"] = processor_name
    payload["prompt_name"] = prompt_name
    payload["used_fallback"] = used_fallback
    payload["duration_ms"] = duration_ms

    if "confidence" not in payload:
        payload["confidence"] = 0.0

    return payload


def run_ai_step(
    *,
    job: Job,
    processor_name: str,
    prompt_name: str,
    context: dict[str, Any],
    response_model: type[BaseModel],
    success_summary: str,
    success_payload_builder,
    fallback_payload_builder,
) -> Job:
    started = time.perf_counter()

    try:
        prompt = render_prompt(
            prompt_name,
            {
                "context_json": json.dumps(context, ensure_ascii=False, indent=2),
            },
        )

        raw_output = get_llm_client().generate_json(prompt)
        parsed = response_model.model_validate(raw_output)

        duration_ms = int((time.perf_counter() - started) * 1000)

        payload = success_payload_builder(parsed)
        payload = add_observability_fields(
            payload,
            processor_name=processor_name,
            prompt_name=prompt_name,
            used_fallback=False,
            duration_ms=duration_ms,
        )
        payload = apply_confidence_guardrail(payload)

        result = {
            "status": "completed",
            "summary": success_summary,
            "requires_human_review": getattr(parsed, "confidence", 0.0) < 0.70,
            "payload": payload,
        }

        if payload.get("low_confidence"):
            result["requires_human_review"] = True
            payload["recommended_next_step"] = "manual_review"

        return append_processor_result(job, processor_name, result)

    except (LLMClientError, ValidationError, ValueError, TypeError) as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)

        payload = fallback_payload_builder(str(exc))
        payload = add_observability_fields(
            payload,
            processor_name=processor_name,
            prompt_name=prompt_name,
            used_fallback=True,
            duration_ms=duration_ms,
        )

        result = {
            "status": "completed",
            "summary": f"{success_summary} Fallback till manuell granskning.",
            "requires_human_review": True,
            "payload": payload,
        }
        return append_processor_result(job, processor_name, result)