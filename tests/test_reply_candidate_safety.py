"""Reply candidate pre-write safety tests."""

from __future__ import annotations

from app.workflows.reply_candidate_safety import (
    assess_reply_candidate_safety,
    verify_sent_reply_matches_approved_candidate,
)


def test_blocks_booking_and_guarantee_language():
    booking = assess_reply_candidate_safety("Vi har bokad tid på tisdag kl 10:00.")
    assert booking["passed"] is False
    assert "booked_time" in booking["violations"]

    guarantee = assess_reply_candidate_safety("Vi garanterar leverans inom 3 dagar.")
    assert guarantee["passed"] is False


def test_post_write_hash_mismatch_detected():
    approved = assess_reply_candidate_safety("Tack för ditt meddelande. Vi återkommer.")
    sent = verify_sent_reply_matches_approved_candidate(
        approved_hash=approved["content_hash"],
        sent_body="Priset är 9999 kr",
    )
    assert sent["passed"] is False
    assert "sent_reply_hash_mismatch" in sent["reason_codes"]
