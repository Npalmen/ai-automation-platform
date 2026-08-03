"""R3 recipient readiness gate and failure-stage regression tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.evaluation.live.recipient_gmail_readiness import RecipientGmailReadinessResult
from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
    ORPHANED_R3_INBOUND_TRIGGERS,
    R3ApprovalArtifact,
    R3_SEND_SCENARIO_IDS,
    _execute_live_scenario,
    _failed_scenario_outcome,
    run_r3_live_canary,
    validate_r3_pre_execute_gates,
)


def _approval() -> R3ApprovalArtifact:
    return R3ApprovalArtifact(
        path=Path("approval.json"),
        payload={
            "approval_type": "R3_LIVE_CANARY_MANUAL_SEND",
            "body_hashes_approved": True,
            "send_scenario_ids": sorted(R3_SEND_SCENARIO_IDS),
        },
        artifact_hash="hash",
    )


def test_execute_stops_before_trigger_when_recipient_readiness_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()

    backend = MagicMock()
    with patch(
        "app.evaluation.profile_testbot.qualification.coworker_r3_execution.run_sender_readiness_read_only",
        return_value=MagicMock(ready=True, issues=[]),
    ), patch(
        "app.evaluation.profile_testbot.qualification.coworker_r3_execution.run_recipient_gmail_readiness",
        return_value=RecipientGmailReadinessResult(
            recipient_oauth_configured=True,
            blockers=["recipient list_labels failed"],
        ),
    ), patch(
        "app.evaluation.profile_testbot.qualification.coworker_r3_execution.evaluate_r3_execution_readiness",
        return_value={"r3_canary_ready_for_execution": True, "execution_blockers": []},
    ):
        result = validate_r3_pre_execute_gates(
            runtime_sha="a" * 40,
            repo_root=tmp_path,
            render_rows=[],
            approval=_approval(),
            recipient_email="recipient@eval.test",
            manifest={},
        )

    assert result["ready"] is False
    assert result["failure_stage"] == "pre_execute_readiness"
    backend.send_test_message.assert_not_called()


def test_delivery_observation_failure_stage_reported():
    outcome = _failed_scenario_outcome(
        scenario_id="PTB-DCQ-0000",
        planned_gmail_send=True,
        failure_stage="delivery_observation",
        failure_reason="delivery_observation: HTTP 503 — blocked",
    )
    assert outcome.failure_stage == "delivery_observation"
    assert "delivery_observation" in (outcome.failure_reason or "")


def test_execute_handles_delivery_http_error_with_correct_stage(tmp_path):
    from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
        build_r3_frozen_execution_rows,
        build_coworker_live_canary_manifest,
    )
    from app.evaluation.profile_testbot.profile_contract import load_customer_profile

    profile = load_customer_profile("niklas-demo-live-eval-v1")
    built = build_coworker_live_canary_manifest(profile_id="niklas-demo-live-eval-v1", seed=0)
    scenario = next(s for s in built.scenarios if s.scenario_id == "PTB-DCQ-0000")
    manifest = {
        "manifest_hash": "abc",
        "approved_send_body_hashes": {},
        "approved_send_body_texts": {},
        "scenario_ids": [],
    }
    rows = build_r3_frozen_execution_rows(manifest=manifest, campaign_id="camp")
    row = next(r for r in rows if r["scenario_id"] == "PTB-DCQ-0000")
    backend = MagicMock()
    backend.gmail_sends = 0
    backend.send_test_message.return_value = MagicMock(
        provider_message_id="msg-1",
        inbound_provider_message_id="msg-1",
        inbound_rfc_message_id="<abc@mail>",
    )
    response = httpx.Response(503, json={"detail": {"failure_stage": "delivery_observation"}})
    backend.observe_intake.side_effect = httpx.HTTPStatusError(
        "blocked", request=MagicMock(), response=response
    )
    outcome = _execute_live_scenario(
        campaign_id="camp",
        scenario=scenario,
        backend=backend,
        render_row=row,
        recipient_email="niklas@sol-f.se",
        claimed_operations=set(),
        gmail_send_budget_remaining=8,
    )
    assert outcome.status == "failed"
    assert outcome.failure_stage == "delivery_observation"
    assert "delivery_observation" in (outcome.failure_reason or "")


def test_orphan_trigger_not_counted_as_approved_reply():
    orphan = ORPHANED_R3_INBOUND_TRIGGERS[0]
    assert orphan["inbound_trigger_sent"] is True
    assert orphan["approved_reply_sent"] is False
    assert orphan["draft_created"] is False
    assert orphan["exclude_from_approved_reply_count"] is True


def test_dry_run_uses_same_recipient_readiness_gate(tmp_path, monkeypatch):
    from tests.test_coworker_r3_live_execution import (
        APPROVED_RECIPIENT,
        REPO_ROOT,
        _approval_payload,
        _manifest_payload,
        _ready_readiness_result,
        _render_rows_pass,
    )

    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(_approval_payload()), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")

    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    with (
        patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_execution.evaluate_coworker_r3_readiness",
            return_value=_ready_readiness_result(),
        ),
        patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_execution.build_r3_render_rows",
            return_value=_render_rows_pass(),
        ),
        patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_execution.get_live_eval_config",
            return_value=MagicMock(
                sender_emails=["sender@eval.test"],
                recipient_emails=[APPROVED_RECIPIENT],
            ),
        ),
        patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_execution.validate_r3_pre_execute_gates",
        ) as mock_pre_execute,
    ):
        mock_pre_execute.return_value = {
            "ready": True,
            "blockers": [],
            "failure_stage": None,
            "registration_contract_valid": True,
        }
        result = run_r3_live_canary(
            mode="dry_run",
            manifest_path=manifest_path,
            approval_path=approval_path,
            expected_runtime_sha="c" * 40,
            repo_root=REPO_ROOT,
        )
    mock_pre_execute.assert_called_once()
    assert result.overall_status == "DRY_RUN_PASS"


def test_registration_success_not_misclassified_as_registration_failure():
    outcome = _failed_scenario_outcome(
        scenario_id="PTB-DCQ-0000",
        planned_gmail_send=True,
        failure_stage="delivery_observation",
        failure_reason="delivery_observation: HTTP 503 — blocked",
    )
    assert outcome.failure_stage != "live_run_registration"
