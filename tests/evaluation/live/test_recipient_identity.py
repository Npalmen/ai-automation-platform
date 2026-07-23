"""Canonical recipient identity resolution tests."""

from __future__ import annotations

import pytest

from app.evaluation.live.recipient_identity import (
    is_verified_email_address,
    resolve_canonical_recipient_email,
)


def test_me_is_never_verified_email():
    assert is_verified_email_address("me") is False
    assert is_verified_email_address("ME") is False


def test_metadata_email_preferred_over_user_id():
    email, error = resolve_canonical_recipient_email(
        {"user_id": "recipient@eval.test"},
        metadata={"email": "recipient@eval.test"},
        allowlist=frozenset({"recipient@eval.test"}),
    )
    assert email == "recipient@eval.test"
    assert error is None


def test_user_id_email_passes_when_metadata_missing():
    email, error = resolve_canonical_recipient_email(
        {"user_id": "recipient@eval.test"},
        metadata={},
        allowlist=frozenset({"recipient@eval.test"}),
    )
    assert email == "recipient@eval.test"
    assert error is None


def test_user_id_me_without_metadata_fail_closed():
    email, error = resolve_canonical_recipient_email(
        {"user_id": "me"},
        metadata={},
        allowlist=frozenset({"recipient@eval.test"}),
    )
    assert email is None
    assert error == "recipient_identity_unverified"


def test_metadata_and_user_id_conflict_fail_closed():
    email, error = resolve_canonical_recipient_email(
        {"user_id": "other@eval.test"},
        metadata={"email": "recipient@eval.test"},
        allowlist=frozenset({"recipient@eval.test", "other@eval.test"}),
    )
    assert email is None
    assert error == "recipient_identity_conflict"


def test_recipient_not_allowlisted_fail_closed():
    email, error = resolve_canonical_recipient_email(
        {"user_id": "other@eval.test"},
        metadata={},
        allowlist=frozenset({"recipient@eval.test"}),
    )
    assert email is None
    assert error == "recipient_not_allowlisted"
