"""Parse live-eval correlation tokens from Gmail subject/body."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.evaluation.live.constants import SUBJECT_TOKEN_PREFIX

_TOKEN_RE = re.compile(
    rf"^{re.escape(SUBJECT_TOKEN_PREFIX)}/([^/]+)/([^/]+)/(\d+)",
    re.IGNORECASE,
)
_BODY_RE = re.compile(
    r"KROWOLF_EVAL:evaluation_run_id=([a-f0-9\-]{8,36})",
    re.IGNORECASE,
)

_REPLY_PREFIXES = (
    "re:",
    "fw:",
    "fwd:",
    "sv:",
    "aw:",
    "antw:",
    "vs:",
)


def _strip_reply_prefixes(subject: str) -> str:
    text = (subject or "").strip()
    while text:
        lowered = text.lower()
        stripped = False
        for prefix in _REPLY_PREFIXES:
            if lowered.startswith(prefix):
                text = text[len(prefix) :].lstrip()
                stripped = True
                break
        if not stripped:
            break
    return text


@dataclass(frozen=True)
class ParsedCorrelation:
    evaluation_run_id: str
    scenario_id: str
    attempt_id: int


def parse_subject_token(subject: str) -> ParsedCorrelation | None:
    subject = _strip_reply_prefixes(subject or "")
    if SUBJECT_TOKEN_PREFIX not in subject:
        return None
    for part in subject.split("|"):
        candidate = part.strip()
        match = _TOKEN_RE.match(candidate)
        if match:
            return ParsedCorrelation(
                evaluation_run_id=match.group(1),
                scenario_id=match.group(2),
                attempt_id=int(match.group(3)),
            )
    match = _TOKEN_RE.search(subject)
    if match:
        return ParsedCorrelation(
            evaluation_run_id=match.group(1),
            scenario_id=match.group(2),
            attempt_id=int(match.group(3)),
        )
    return None


def parse_body_marker(body: str) -> str | None:
    match = _BODY_RE.search(body or "")
    if not match:
        return None
    return match.group(1)


def build_subject_with_token(
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    base_subject: str,
) -> str:
    token = f"{SUBJECT_TOKEN_PREFIX}/{evaluation_run_id}/{scenario_id}/{attempt_id}"
    base = (base_subject or "Live eval").strip()
    return f"{token} | {base}"
