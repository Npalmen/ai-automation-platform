"""Email approval command parser.

Parses operator reply emails for approval commands. Deterministic, no LLM.
Fail-closed: anything not matching a known command returns parsed=False.

Supported commands (first non-blank line of email body, case-insensitive):
    GODKÄNN              → approve
    APPROVE              → approve
    STOPPA               → reject
    REJECT               → reject
    ÄNDRA: <text>        → change  (change_text = stripped replacement text)
    CHANGE: <text>       → change

Usage:
    from app.workflows.approval_command_parser import parse_approval_command
    result = parse_approval_command(email_body)
    # result["parsed"] is False if no command matched
"""
from __future__ import annotations

import re

# ── command patterns ──────────────────────────────────────────────────────────

_APPROVE_PATTERN = re.compile(
    r"^\s*(godkänn|approve)\s*$",
    re.IGNORECASE,
)

_REJECT_PATTERN = re.compile(
    r"^\s*(stoppa|reject)\s*$",
    re.IGNORECASE,
)

_CHANGE_PATTERN = re.compile(
    r"^\s*(ändra|change)\s*:\s*(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def parse_approval_command(body: str) -> dict:
    """Parse an approval command from an email reply body.

    Inspects the first non-blank, non-quoted line of the body.
    Quoted reply lines (starting with ">") are ignored.
    Signature separators ("--") terminate parsing.

    Returns:
        parsed       : bool   — True if a known command was found
        command      : str | None — "approve" | "reject" | "change"
        change_text  : str | None — replacement text for "change" commands
        raw_match    : str | None — the matched line from the email
        confidence   : "high" | "low"
    """
    if not body or not body.strip():
        return _no_match()

    candidate = _extract_command_line(body)
    if candidate is None:
        return _no_match()

    # APPROVE
    if _APPROVE_PATTERN.match(candidate):
        return {
            "parsed": True,
            "command": "approve",
            "change_text": None,
            "raw_match": candidate.strip(),
            "confidence": "high",
        }

    # REJECT
    if _REJECT_PATTERN.match(candidate):
        return {
            "parsed": True,
            "command": "reject",
            "change_text": None,
            "raw_match": candidate.strip(),
            "confidence": "high",
        }

    # CHANGE
    m = _CHANGE_PATTERN.match(candidate)
    if m:
        change_text = m.group(2).strip()
        if not change_text:
            return _no_match()
        return {
            "parsed": True,
            "command": "change",
            "change_text": change_text,
            "raw_match": candidate.strip(),
            "confidence": "high",
        }

    return _no_match()


def _extract_command_line(body: str) -> str | None:
    """Return the first non-blank, non-quoted line before any signature separator."""
    for line in body.splitlines():
        stripped = line.strip()
        # Stop at email signature separator
        if stripped == "--":
            break
        # Skip blank lines
        if not stripped:
            continue
        # Skip quoted reply lines
        if stripped.startswith(">"):
            continue
        return stripped
    return None


def _no_match() -> dict:
    return {
        "parsed": False,
        "command": None,
        "change_text": None,
        "raw_match": None,
        "confidence": "low",
    }
