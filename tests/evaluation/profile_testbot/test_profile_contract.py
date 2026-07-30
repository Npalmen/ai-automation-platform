"""Profile contract tests."""

from __future__ import annotations

from app.evaluation.profile_testbot.profile_contract import (
    compute_profile_snapshot_hash,
    load_customer_profile,
    validate_profile_payload,
)


def test_profile_schema_validates():
    profile = load_customer_profile("pilot-service-company-v1")
    assert profile.profile_id == "pilot-service-company-v1"
    assert profile.version == 1
    assert validate_profile_payload(profile.raw) == []


def test_profile_hash_stable():
    profile = load_customer_profile("pilot-service-company-v1")
    assert profile.profile_snapshot_hash == compute_profile_snapshot_hash(profile.raw)
