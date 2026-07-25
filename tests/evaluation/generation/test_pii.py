"""PII and synthetic data validation for 2G generation."""

from __future__ import annotations

import json
import re

from app.evaluation.generation.generator import generate_batch

FORBIDDEN_PATTERNS = [
    re.compile(r"sk-[a-zA-Z0-9]{10,}"),
    re.compile(r"\bBearer\s+"),
    re.compile(r"access_token"),
    re.compile(r"refresh_token"),
    re.compile(r"client_secret"),
    re.compile(r"C:\\Users\\"),
    re.compile(r"/home/"),
]
NON_EXAMPLE_EMAIL = re.compile(r"@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def test_synthetic_data_passes_pii_scan():
    result = generate_batch(templates_per_parent=2, base_seed=0)
    for record in result.records:
        blob = json.dumps(record.scenario.model_dump(mode="json"))
        for pattern in FORBIDDEN_PATTERNS:
            assert pattern.search(blob) is None, f"PII pattern {pattern.pattern} in {record.scenario.scenario_id}"
        for match in NON_EXAMPLE_EMAIL.finditer(blob):
            email_fragment = match.group(0)
            assert email_fragment.endswith("@example.com"), (
                f"Non-synthetic email {email_fragment} in {record.scenario.scenario_id}"
            )
