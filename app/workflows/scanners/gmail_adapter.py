"""
Gmail workflow scanner adapter.

Reads stored Gmail-sourced jobs from the jobs table (up to SAMPLE_LIMIT records,
most-recent first).  No live Gmail API calls are made.

Extracted fields per record
---------------------------
- sender email (nested sender.email or flat sender_email key)
- subject (subject or latest_message_subject)
- job_type (already classified by the intake pipeline)

Outputs written to system_map.gmail
------------------------------------
known_senders     : top 20 senders by frequency, [{email, count}]
subject_patterns  : top 20 normalised subjects by frequency, [{pattern, count}]
                    (Re: / Fwd: / Sv: / Aw: etc. stripped)
detected_mail_types : sorted unique list of job_type values in the sample
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from app.workflows.scanners.base import BaseWorkflowScannerAdapter, ScanResult

SAMPLE_LIMIT = 250
TOP_N = 20

_STRIP_PREFIXES = re.compile(
    r"^(re|fwd|fw|sv|vs|aw|ant|r|f)\s*:\s*",
    re.IGNORECASE,
)


def analyse_records(records: list) -> tuple[dict, dict]:
    """
    Pure analysis function — no DB or external I/O.

    Returns (gmail_system_map, gmail_summary).
    Public so it can be imported directly in tests and by main.py if needed.
    """
    sender_counter: Counter = Counter()
    raw_subjects: list[str] = []
    type_counter: Counter = Counter()

    for r in records:
        inp = r.input_data or {}
        sender = inp.get("sender") or {}

        email = (
            sender.get("email") or inp.get("sender_email") or ""
        ).strip().lower()
        if email:
            sender_counter[email] += 1

        subject = (inp.get("subject") or inp.get("latest_message_subject") or "").strip()
        if subject:
            raw_subjects.append(subject)

        job_type = (r.job_type or "unknown").strip()
        type_counter[job_type] += 1

    known_senders = [
        {"email": email, "count": count}
        for email, count in sender_counter.most_common(TOP_N)
    ]

    normalised_counter: Counter = Counter()
    for s in raw_subjects:
        normalised = _STRIP_PREFIXES.sub("", s).strip()
        normalised = " ".join(normalised.split())
        if normalised:
            normalised_counter[normalised] += 1

    subject_patterns = [
        {"pattern": pattern, "count": count}
        for pattern, count in normalised_counter.most_common(TOP_N)
    ]

    detected_mail_types = sorted(type_counter.keys())

    gmail_map = {
        "known_senders":       known_senders,
        "subject_patterns":    subject_patterns,
        "detected_mail_types": detected_mail_types,
    }

    gmail_summary = {
        "messages_scanned":    len(records),
        "senders_detected":    len(known_senders),
        "patterns_detected":   len(subject_patterns),
        "mail_types_detected": detected_mail_types,
    }

    return gmail_map, gmail_summary


class GmailWorkflowScannerAdapter(BaseWorkflowScannerAdapter):
    system_key = "gmail"

    def run(self, db: Any, tenant_id: str) -> ScanResult:
        from app.repositories.postgres.job_models import JobRecord

        scanned_at = datetime.now(timezone.utc).isoformat()

        records = (
            db.query(JobRecord)
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.input_data["source"]["system"].as_string() == "gmail",
            )
            .order_by(JobRecord.created_at.desc())
            .limit(SAMPLE_LIMIT)
            .all()
        )

        gmail_map, gmail_summary = analyse_records(records)

        return ScanResult(
            system="gmail",
            status="completed",
            scanned_at=scanned_at,
            data=gmail_map,
            summary=gmail_summary,
        )
