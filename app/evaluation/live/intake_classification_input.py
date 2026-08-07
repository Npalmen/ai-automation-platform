"""Normalize Gmail inputs before production intake classification."""

from __future__ import annotations

import re

from app.evaluation.live.constants import SUBJECT_TOKEN_PREFIX
from app.workflows.message_partition import partition_message_text

_EVAL_HTML_COMMENT_RE = re.compile(r"<!--\s*KROWOLF_[^>]*-->\s*", re.IGNORECASE)

LIVE_EVAL_INTAKE_ENABLED_JOB_TYPES = frozenset({"lead", "customer_inquiry", "invoice"})


def normalize_intake_classification_inputs(subject: str, body: str) -> tuple[str, str]:
    """Strip live-eval transport metadata that must not affect intake taxonomy."""
    subj = (subject or "").strip()
    if SUBJECT_TOKEN_PREFIX in subj and " | " in subj:
        subj = subj.split(" | ", 1)[1].strip()

    text = (body or "").replace("\r\n", "\n")
    text = _EVAL_HTML_COMMENT_RE.sub("", text)
    current, _quoted = partition_message_text(text)
    norm_body = (current or text).strip()
    return subj, norm_body


def evaluate_gmail_intake_classification_gate(
    subject: str,
    body: str,
    *,
    enabled_job_types: frozenset[str] | None = None,
) -> dict[str, str | bool | None]:
    """Production-equivalent intake proceed/suppress decision from subject+body."""
    from app.workflows.processors.classification_processor import classify_email_type

    enabled = enabled_job_types or LIVE_EVAL_INTAKE_ENABLED_JOB_TYPES
    norm_subject, norm_body = normalize_intake_classification_inputs(subject, body)
    inferred_type = classify_email_type(norm_subject, norm_body)
    if inferred_type not in enabled:
        return {
            "proceeds": False,
            "inferred_type": inferred_type,
            "skip_reason": f"{inferred_type}_disabled",
            "normalized_subject": norm_subject,
        }
    return {
        "proceeds": True,
        "inferred_type": inferred_type,
        "skip_reason": None,
        "normalized_subject": norm_subject,
    }
