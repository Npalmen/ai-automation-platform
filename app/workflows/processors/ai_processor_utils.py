import json
import re
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.exceptions import LLMClientError
from app.ai.llm.client import get_llm_client
from app.ai.prompts.registry import render_prompt
from app.domain.workflows.models import Job


# ── shared extraction helpers ─────────────────────────────────────────────────

# Matches Swedish and international phone numbers; requires ≥7 digits.
_PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(\+46|0046)?"
    r"[\s\-]?"
    r"(0\d{1,3}|\d{2,3})"
    r"[\s\-]?"
    r"\d{2,4}"
    r"(?:[\s\-]?\d{2,4}){1,3}"
    r"(?!\d)",
)


def extract_phone(subject: str, body_text: str) -> str | None:
    """Return the first plausible phone number in subject or body, or None."""
    for text in (subject, body_text):
        m = _PHONE_RE.search(text or "")
        if m:
            raw = m.group(0).strip()
            return re.sub(r"[\s\-]+", "-", raw)
    return None


def normalize_sender(input_data: dict[str, Any]) -> dict[str, str]:
    """Return a clean sender dict from nested or flat input_data fields.

    Reads nested ``input_data["sender"]`` first; falls back to flat
    ``sender_name`` / ``sender_email`` / ``sender_phone`` keys.
    All values are stripped strings; missing fields are omitted.
    """
    nested = input_data.get("sender") or {}
    name = (nested.get("name") or input_data.get("sender_name") or "").strip()
    email = (nested.get("email") or input_data.get("sender_email") or "").strip().lower()
    phone = (nested.get("phone") or input_data.get("sender_phone") or "").strip()
    sender: dict[str, str] = {}
    if name:
        sender["name"] = name
    if email:
        sender["email"] = email
    if phone:
        sender["phone"] = phone
    return sender


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