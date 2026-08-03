"""R3 readiness contract tests."""

from __future__ import annotations

from pathlib import Path

from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (
    QUALIFIED_REPLY_SHA,
    R3_APPROVED_SEND_BODY_HASHES,
    R3_INSTRUMENTATION_ALLOWLIST,
    R3_SEMI_AUTO_CONTEXT_PREFIXES,
    assert_r3_code_equivalence,
    compare_send_body_hashes,
    evaluate_coworker_r3_readiness,
)


class TestCoworkerR3ReadinessContract:
    def test_instrumentation_allowlist_is_bounded(self):
        assert len(R3_INSTRUMENTATION_ALLOWLIST) >= 5
        assert "coworker_r3_frozen_bodies.py" in R3_INSTRUMENTATION_ALLOWLIST[-1] or any(
            "frozen" in path for path in R3_INSTRUMENTATION_ALLOWLIST
        )
        assert all(path.endswith((".py", ".json")) for path in R3_INSTRUMENTATION_ALLOWLIST)

    def test_approved_send_hashes_cover_eight_sends(self):
        assert len(R3_APPROVED_SEND_BODY_HASHES) == 8

    def test_semi_auto_blockers_are_isolated_prefixes(self):
        sample = (
            "PROFILE_DRIVEN_SEMI_AUTO_GMAIL_QUALIFIED already registered; "
            "new live semi-auto run requires re-qualification"
        )
        assert any(sample.startswith(prefix) for prefix in R3_SEMI_AUTO_CONTEXT_PREFIXES)

    def test_body_hash_drift_detection(self):
        rows = [
            {
                "scenario_id": "PTB-DCQ-0000",
                "planned_gmail_send": True,
                "body_hash": R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0000"],
            },
            {
                "scenario_id": "PTB-DCQ-0022",
                "planned_gmail_send": True,
                "body_hash": "different-hash",
            },
        ]
        drift, required = compare_send_body_hashes(rows)
        assert required is True
        assert "PTB-DCQ-0022" in drift

    def test_predeploy_does_not_require_manual_send_approval(self, monkeypatch):
        repo_root = Path(__file__).resolve().parents[1]
        monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
        monkeypatch.setenv("LIVE_EVAL_APP_BASE_URL", "http://127.0.0.1:8010")
        monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
        monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
        monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
        monkeypatch.setenv(
            "LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN",
            "sender-token",
        )
        monkeypatch.setenv(
            "LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN",
            "recipient-token",
        )
        monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "client-id")
        monkeypatch.setenv("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT", "yes")

        result = evaluate_coworker_r3_readiness(
            phase="predeploy",
            profile_id="niklas-demo-live-eval-v1",
            tenant_id="TENANT_LIVE_EVAL",
            instrumentation_merge_sha=QUALIFIED_REPLY_SHA,
            repo_root=repo_root,
            render_rows=[],
            send_budget=8,
            no_send_count=7,
        )
        assert result.r3_canary_ready_for_manual_send_approval is False
        assert result.postdeploy_preflight_pass is False
        assert any(
            item.startswith("PROFILE_DRIVEN_SEMI_AUTO_GMAIL_QUALIFIED")
            for item in result.unrelated_qualification_context
        ) or result.unrelated_qualification_context == []

    def test_code_equivalence_requires_distinct_merge_sha(self, tmp_path: Path):
        result = assert_r3_code_equivalence(
            repo_root=tmp_path,
            qualified_reply_sha="a" * 40,
            instrumentation_merge_sha="a" * 40,
        )
        assert result.passed is False
        assert "instrumentation commit required" in result.assertion
