"""Tests for R3 frozen approved send bodies."""

from __future__ import annotations

from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bodies import (
    load_r3_approved_send_body_texts,
    r3_send_body_hash,
    validate_frozen_send_bodies,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (
    R3_APPROVED_SEND_BODY_HASHES,
)


def test_locked_bodies_hash_to_approved_values():
    bodies = load_r3_approved_send_body_texts()
    assert set(bodies) == set(R3_APPROVED_SEND_BODY_HASHES)
    for scenario_id, approved_hash in R3_APPROVED_SEND_BODY_HASHES.items():
        assert r3_send_body_hash(bodies[scenario_id]) == approved_hash


def test_validate_frozen_send_bodies_passes_locked_manifest():
    manifest = {
        "approved_send_body_hashes": dict(R3_APPROVED_SEND_BODY_HASHES),
        "approved_send_body_texts": load_r3_approved_send_body_texts(),
    }
    assert not validate_frozen_send_bodies(manifest=manifest)


def test_frozen_execution_rows_are_stable():
    from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
        build_r3_frozen_execution_rows,
    )

    manifest = {
        "approved_send_body_hashes": dict(R3_APPROVED_SEND_BODY_HASHES),
        "approved_send_body_texts": load_r3_approved_send_body_texts(),
    }
    first = build_r3_frozen_execution_rows(manifest=manifest, campaign_id="camp-a")
    second = build_r3_frozen_execution_rows(manifest=manifest, campaign_id="camp-b")
    by_first = {row["scenario_id"]: row["body_hash"] for row in first if row["planned_gmail_send"]}
    by_second = {row["scenario_id"]: row["body_hash"] for row in second if row["planned_gmail_send"]}
    assert by_first == by_second


def test_validate_frozen_send_bodies_blocks_tampered_text():
    bodies = load_r3_approved_send_body_texts()
    tampered = dict(bodies)
    first = next(iter(tampered))
    tampered[first] = tampered[first] + " extra"
    manifest = {
        "approved_send_body_hashes": dict(R3_APPROVED_SEND_BODY_HASHES),
        "approved_send_body_texts": tampered,
    }
    issues = validate_frozen_send_bodies(manifest=manifest)
    assert any("hash mismatch" in item for item in issues)
