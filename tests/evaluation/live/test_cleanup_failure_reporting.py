"""Cleanup-only failure observability tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.evaluation.live.exit_codes import EXIT_CLEANUP
from app.evaluation.live.runner import cleanup_only


def test_cleanup_only_reports_safety_error(capsys):
    with patch(
        "app.evaluation.live.runner.acquire_run_writer_lock",
        return_value=MagicMock(),
    ), patch(
        "app.evaluation.live.runner.release_run_writer_lock",
    ), patch(
        "app.evaluation.live.runner.load_checkpoint",
        return_value=MagicMock(
            sender_gmail_message_id="sender-1",
            recipient_gmail_message_id="recipient-1",
        ),
    ), patch(
        "app.evaluation.live.runner.LiveEvalObserver",
    ) as observer_cls:
        observer = observer_cls.return_value
        observer.get_run.return_value = {"root_job_id": "job-1", "root_gmail_message_id": "recipient-1"}
        observer.cleanup_recipient.side_effect = RuntimeError("archive failed")

        exit_code = cleanup_only(
            base_url="http://app",
            admin_api_key="key",
            tenant_id="TENANT_LIVE_EVAL",
            evaluation_run_id="run-cleanup-fail",
            recipient_gmail_message_id="recipient-1",
            phase="post_claim",
        )

    assert exit_code == EXIT_CLEANUP
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["cleanup_state"] == "failed"
    assert payload["reason_type"] == "exception"
    assert payload["gmail_mutations"] == 0
