"""Tests for R3 digital coworker live canary operator execution runner."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_live_canary_manifest import (
    COWORKER_LIVE_CANARY_MANIFEST_HASH,
    COWORKER_LIVE_CANARY_SCENARIO_IDS,
    COWORKER_LIVE_CANARY_SEND_MAX,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
    R3_APPROVAL_TYPE,
    R3_APPROVED_SEND_BODY_HASHES,
    R3_SEND_SCENARIO_IDS,
    R3ApprovalArtifact,
    R3ExecutionResult,
    R3ScenarioOutcome,
    approval_artifact_hash,
    approval_operation_id,
    body_hash,
    load_approval_artifact,
    recipient_matches_approval,
    run_r3_live_canary,
    scan_for_secrets,
    validate_approval_artifact,
    validate_manifest_contract,
    validate_render_rows,
    validate_scenario_allowlist,
    write_execution_reports,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bodies import (
    load_r3_approved_send_body_texts,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (
    CoworkerR3ReadinessResult,
)
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario, ProfileScenarioInput

REPO_ROOT = Path(__file__).resolve().parents[1]
APPROVED_RECIPIENT = "niklas@sol-f.se"
FROZEN_BODIES = load_r3_approved_send_body_texts()


def _approval_payload(**overrides) -> dict:
    payload = {
        "approval_type": R3_APPROVAL_TYPE,
        "approved_at": "2026-08-03T14:53:00Z",
        "approved_by": "operator",
        "approval_scope": "exactly_eight_gmail_sends",
        "recipient_email_redacted": "ni…@sol-f.se",
        "send_scenario_ids": sorted(R3_SEND_SCENARIO_IDS),
        "instrumentation_merge_sha": "c" * 40,
        "qualified_reply_sha": "d" * 40,
        "tenant_id": LIVE_EVAL_TENANT_ID,
        "postdeploy_preflight_pass": True,
        "human_render_rereview_required": False,
        "body_hashes_approved": True,
        "gmail_sent_at_approval": False,
        "gmail_drafts_at_approval": False,
        "registry_status": "PENDING",
    }
    payload.update(overrides)
    return payload


def _manifest_payload() -> dict:
    return {
        "campaign_type": "coworker-reply-live-canary",
        "manifest_hash": COWORKER_LIVE_CANARY_MANIFEST_HASH,
        "tenant_id": LIVE_EVAL_TENANT_ID,
        "scenario_ids": list(COWORKER_LIVE_CANARY_SCENARIO_IDS),
        "send_budget": COWORKER_LIVE_CANARY_SEND_MAX,
        "hold_reject_no_reply_count": 7,
        "approved_send_body_hashes": dict(R3_APPROVED_SEND_BODY_HASHES),
    }


def _render_rows_pass() -> list[dict]:
    rows: list[dict] = []
    for scenario_id in COWORKER_LIVE_CANARY_SCENARIO_IDS:
        planned_send = scenario_id in R3_SEND_SCENARIO_IDS
        approved = R3_APPROVED_SEND_BODY_HASHES.get(scenario_id)
        frozen_text = FROZEN_BODIES.get(scenario_id, "") if planned_send else ""
        current = approved or body_hash("")
        rows.append(
            {
                "scenario_id": scenario_id,
                "planned_gmail_send": planned_send,
                "approval_required": planned_send,
                "body_hash": current,
                "approved_body_hash": approved,
                "body_hash_matches_approved": True if planned_send else None,
                "frozen_customer_text": frozen_text,
                "final_customer_text": frozen_text,
                "body_source": "frozen_manifest",
                "final_customer_text_validation": {"passed": True},
                "oracle_blocking_failures": [],
                "oracle_passed": True,
                "approval_operation_id": approval_operation_id("camp", scenario_id),
            }
        )
    return rows


def _ready_readiness_result(**overrides) -> CoworkerR3ReadinessResult:
    base = CoworkerR3ReadinessResult(
        phase="postdeploy",
        qualified_reply_sha="d" * 40,
        instrumentation_merge_sha="c" * 40,
        runner_sha="c" * 40,
        api_runtime_sha="c" * 40,
        worker_runtime_sha="c" * 40,
        runtime_sha_consistent=True,
        runner_sha_auditable=True,
        predeploy_preflight_pass=False,
        postdeploy_preflight_pass=True,
        r3_canary_ready_for_manual_send_approval=True,
        oauth_ready=True,
        tenant_isolation_verified=True,
        duplicate_replay_protection=True,
        runner_ready_for_live_execution=True,
        send_budget=8,
        no_send_count=7,
        stop_conditions=[],
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


@pytest.fixture
def approval_file(tmp_path: Path) -> Path:
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(_approval_payload()), encoding="utf-8")
    return path


@pytest.fixture
def manifest_file(tmp_path: Path) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_manifest_payload()), encoding="utf-8")
    return path


class TestR3ExecutionValidation:
    def test_recipient_matches_approval(self):
        assert recipient_matches_approval(APPROVED_RECIPIENT) is True
        assert recipient_matches_approval("other@sol-f.se") is False
        assert recipient_matches_approval("niklas@example.com") is False

    def test_scenario_allowlist_exact(self):
        assert not validate_scenario_allowlist(list(COWORKER_LIVE_CANARY_SCENARIO_IDS))
        assert validate_scenario_allowlist(list(COWORKER_LIVE_CANARY_SCENARIO_IDS) + ["EXTRA"])

    def test_manifest_contract_passes_locked_manifest(self):
        assert not validate_manifest_contract(_manifest_payload())

    def test_manifest_contract_rejects_extra_scenario(self):
        payload = _manifest_payload()
        payload["scenario_ids"] = list(COWORKER_LIVE_CANARY_SCENARIO_IDS) + ["PTB-DCQ-9999"]
        assert validate_manifest_contract(payload)

    def test_approval_validation_passes(self, approval_file: Path):
        approval = load_approval_artifact(approval_file)
        assert not validate_approval_artifact(
            approval,
            recipient_email=APPROVED_RECIPIENT,
            runtime_sha="c" * 40,
        )

    def test_execute_without_approval_blocked(self, approval_file: Path):
        payload = _approval_payload(body_hashes_approved=False)
        approval = R3ApprovalArtifact(
            path=approval_file,
            payload=payload,
            artifact_hash=approval_artifact_hash(payload),
        )
        assert validate_approval_artifact(
            approval,
            recipient_email=APPROVED_RECIPIENT,
            runtime_sha="c" * 40,
        )

    def test_wrong_tenant_blocked(self, approval_file: Path):
        payload = _approval_payload(tenant_id="T_WRONG")
        approval = R3ApprovalArtifact(
            path=approval_file,
            payload=payload,
            artifact_hash=approval_artifact_hash(payload),
        )
        issues = validate_approval_artifact(
            approval,
            recipient_email=APPROVED_RECIPIENT,
            runtime_sha="c" * 40,
        )
        assert any("tenant" in item for item in issues)

    def test_wrong_recipient_blocked(self, approval_file: Path):
        approval = load_approval_artifact(approval_file)
        assert validate_approval_artifact(
            approval,
            recipient_email="other@sol-f.se",
            runtime_sha="c" * 40,
        )

    def test_wrong_runtime_sha_does_not_block_approval_artifact(self, approval_file: Path):
        approval = load_approval_artifact(approval_file)
        assert not validate_approval_artifact(
            approval,
            recipient_email=APPROVED_RECIPIENT,
            runtime_sha="f" * 40,
        )

    def test_body_hash_drift_blocked(self):
        rows = _render_rows_pass()
        rows[0]["body_hash"] = "different"
        rows[0]["body_hash_matches_approved"] = False
        issues = validate_render_rows(rows)
        assert any("body hash does not match approved hash" in item for item in issues)

    def test_final_validation_fail_blocked(self):
        rows = _render_rows_pass()
        rows[0]["final_customer_text_validation"] = {"passed": False}
        issues = validate_render_rows(rows)
        assert any("final customer text validation failed" in item for item in issues)

    def test_blocking_oracle_blocked(self):
        rows = _render_rows_pass()
        rows[0]["oracle_blocking_failures"] = ["bad_oracle"]
        issues = validate_render_rows(rows)
        assert any("blocking oracles" in item for item in issues)

    def test_secrets_not_in_reports(self):
        blob = json.dumps({"email": "secret@example.com", "token": "ya29.abcdef"})
        assert scan_for_secrets(blob)


class TestR3DryRun:
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.get_live_eval_config")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.build_r3_render_rows")
    @patch(
        "app.evaluation.profile_testbot.qualification.coworker_r3_execution.evaluate_coworker_r3_readiness"
    )
    def test_dry_run_creates_no_external_writes(
        self,
        mock_readiness,
        mock_render,
        mock_config,
        approval_file: Path,
        manifest_file: Path,
    ):
        mock_config.return_value = MagicMock(
            sender_emails=["sender@eval.test"],
            recipient_emails=[APPROVED_RECIPIENT],
        )
        mock_render.return_value = _render_rows_pass()
        mock_readiness.return_value = _ready_readiness_result()
        result = run_r3_live_canary(
            mode="dry_run",
            manifest_path=manifest_file,
            approval_path=approval_file,
            expected_runtime_sha="c" * 40,
            repo_root=REPO_ROOT,
        )
        assert result.mode == "dry_run"
        assert result.overall_status == "DRY_RUN_PASS"
        assert result.successful_sends == 0
        assert result.readiness.get("r3_canary_ready_for_execution") is True

    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.get_live_eval_config")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.build_r3_render_rows")
    @patch(
        "app.evaluation.profile_testbot.qualification.coworker_r3_execution.evaluate_coworker_r3_readiness"
    )
    def test_dry_run_blocked_when_not_ready(
        self,
        mock_readiness,
        mock_render,
        mock_config,
        approval_file: Path,
        manifest_file: Path,
    ):
        mock_config.return_value = MagicMock(
            sender_emails=["sender@eval.test"],
            recipient_emails=[APPROVED_RECIPIENT],
        )
        mock_render.return_value = _render_rows_pass()
        mock_readiness.return_value = _ready_readiness_result(
            postdeploy_preflight_pass=False,
            stop_conditions=["runtime blocked"],
        )
        result = run_r3_live_canary(
            mode="dry_run",
            manifest_path=manifest_file,
            approval_path=approval_file,
            expected_runtime_sha="c" * 40,
            repo_root=REPO_ROOT,
        )
        assert result.overall_status == "BLOCKED"


class TestR3Execute:
    def _ready_execution_readiness(self) -> dict:
        return {
            "r3_canary_ready_for_execution": True,
            "postdeploy_preflight_pass": True,
            "runtime_sha_consistent": True,
            "human_render_rereview_required": False,
            "execution_blockers": [],
        }

    def _scenario(self, scenario_id: str, behavior: str) -> ProfileScenario:
        return ProfileScenario(
            scenario_id=scenario_id,
            profile_id="niklas-demo-live-eval-v1",
            profile_snapshot_hash="hash",
            family="test",
            intent="test",
            risk_class="low",
            input=ProfileScenarioInput(
                subject="Test",
                message_text="Hej",
                sender_name="Test",
                sender_email="sender@eval.test",
            ),
            expected_classification={},
            expected_route={},
            expected_authorization={},
            expected_send_behavior=behavior,
        )

    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.evaluate_r3_execution_readiness")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.build_coworker_live_canary_manifest")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.load_customer_profile")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.get_live_eval_config")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.build_r3_render_rows")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.build_r3_frozen_execution_rows")
    def test_body_hash_drift_stops_before_send(
        self,
        mock_frozen_render,
        mock_render,
        mock_config,
        mock_profile,
        mock_manifest,
        mock_eval_ready,
        approval_file: Path,
        manifest_file: Path,
    ):
        mock_eval_ready.return_value = self._ready_execution_readiness()
        mock_config.return_value = MagicMock(
            sender_emails=["sender@eval.test"],
            recipient_emails=[APPROVED_RECIPIENT],
        )
        rows = [row for row in _render_rows_pass() if row["scenario_id"] == "PTB-DCQ-0000"]
        rows[0]["frozen_customer_text"] = "tampered frozen body"
        rows[0]["final_customer_text"] = rows[0]["frozen_customer_text"]
        rows[0]["body_hash"] = body_hash(rows[0]["frozen_customer_text"])
        rows[0]["body_hash_matches_approved"] = False
        mock_frozen_render.return_value = rows
        mock_render.return_value = rows
        mock_profile.return_value = MagicMock()
        scenario = self._scenario("PTB-DCQ-0000", "send_after_approval")
        mock_manifest.return_value = MagicMock(scenarios=[scenario])

        backend = MagicMock()
        backend.gmail_sends = 0
        backend.sent_keys = set()
        backend.external_writes = {"sheets": 0, "monday": 0, "visma": 0}
        backend.automatic_verify_link_merge = 0
        backend.send_test_message.return_value = MagicMock(
            provider_message_id="msg-1",
            inbound_provider_message_id="in-1",
            inbound_rfc_message_id="rfc-1",
        )
        backend.observe_intake.return_value = MagicMock(tenant_id=LIVE_EVAL_TENANT_ID)
        backend.observe_processing.return_value = MagicMock(
            approval_state="pending",
            draft_text="different body text",
        )
        backend.bind_frozen_send_body = MagicMock()

        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_execution.COWORKER_LIVE_CANARY_SCENARIO_IDS",
            ("PTB-DCQ-0000",),
        ):
            result = run_r3_live_canary(
                mode="execute",
                manifest_path=manifest_file,
                approval_path=approval_file,
                expected_runtime_sha="c" * 40,
                repo_root=REPO_ROOT,
                backend=backend,
            )
        assert result.overall_status in {"FAIL", "PARTIAL"}
        assert result.human_render_rereview_required is False
        backend.approve_via_lifecycle.assert_not_called()
        backend.bind_frozen_send_body.assert_not_called()

    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.evaluate_r3_execution_readiness")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.build_coworker_live_canary_manifest")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.load_customer_profile")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.get_live_eval_config")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.build_r3_render_rows")
    def test_no_send_never_calls_approve(
        self,
        mock_render,
        mock_config,
        mock_profile,
        mock_manifest,
        mock_eval_ready,
        approval_file: Path,
        manifest_file: Path,
    ):
        from app.evaluation.profile_testbot.campaign.semi_auto_contract import ReplyVerification

        mock_eval_ready.return_value = self._ready_execution_readiness()
        mock_config.return_value = MagicMock(
            sender_emails=["sender@eval.test"],
            recipient_emails=[APPROVED_RECIPIENT],
        )
        rows = [row for row in _render_rows_pass() if row["scenario_id"] == "PTB-DCQ-0032"]
        mock_render.return_value = rows
        mock_profile.return_value = MagicMock()
        scenario = self._scenario("PTB-DCQ-0032", "draft_for_approval")
        mock_manifest.return_value = MagicMock(scenarios=[scenario])

        backend = MagicMock()
        backend.gmail_sends = 0
        backend.sent_keys = set()
        backend.external_writes = {"sheets": 0, "monday": 0, "visma": 0}
        backend.automatic_verify_link_merge = 0
        backend.send_test_message.return_value = MagicMock(
            provider_message_id="msg-1",
            inbound_provider_message_id="in-1",
            inbound_rfc_message_id="rfc-1",
        )
        backend.observe_intake.return_value = MagicMock(tenant_id=LIVE_EVAL_TENANT_ID)
        backend.observe_processing.return_value = MagicMock(
            approval_state="pending",
            draft_text="draft text",
        )
        backend.verify_reply.return_value = ReplyVerification(
            execution_intents=0,
            adapter_invocations=0,
            provider_accepted=False,
            recipient_verified=True,
            duplicate_send=False,
            reply_hash=None,
        )

        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_execution.COWORKER_LIVE_CANARY_SCENARIO_IDS",
            ("PTB-DCQ-0032",),
        ):
            result = run_r3_live_canary(
                mode="execute",
                manifest_path=manifest_file,
                approval_path=approval_file,
                expected_runtime_sha="c" * 40,
                repo_root=REPO_ROOT,
                backend=backend,
            )
        backend.approve_via_lifecycle.assert_not_called()
        assert result.no_send_verified == 1

    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.evaluate_r3_execution_readiness")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.build_coworker_live_canary_manifest")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.load_customer_profile")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.get_live_eval_config")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.build_r3_render_rows")
    def test_duplicate_operation_blocked(
        self,
        mock_render,
        mock_config,
        mock_profile,
        mock_manifest,
        mock_eval_ready,
        approval_file: Path,
        manifest_file: Path,
    ):
        mock_eval_ready.return_value = self._ready_execution_readiness()
        mock_config.return_value = MagicMock(
            sender_emails=["sender@eval.test"],
            recipient_emails=[APPROVED_RECIPIENT],
        )
        rows = [row for row in _render_rows_pass() if row["scenario_id"] == "PTB-DCQ-0000"]
        mock_render.return_value = rows
        mock_profile.return_value = MagicMock()
        scenario = self._scenario("PTB-DCQ-0000", "send_after_approval")
        mock_manifest.return_value = MagicMock(scenarios=[scenario])

        backend = MagicMock()
        backend.gmail_sends = 0
        backend.sent_keys = {f"camp:PTB-DCQ-0000:send"}
        backend.external_writes = {"sheets": 0, "monday": 0, "visma": 0}

        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_execution.COWORKER_LIVE_CANARY_SCENARIO_IDS",
            ("PTB-DCQ-0000",),
        ):
            result = run_r3_live_canary(
                mode="execute",
                manifest_path=manifest_file,
                approval_path=approval_file,
                expected_runtime_sha="c" * 40,
                repo_root=REPO_ROOT,
                backend=backend,
            )
        assert result.overall_status in {"FAIL", "PARTIAL"}

    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.evaluate_r3_execution_readiness")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.build_coworker_live_canary_manifest")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.load_customer_profile")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.get_live_eval_config")
    @patch("app.evaluation.profile_testbot.qualification.coworker_r3_execution.build_r3_render_rows")
    def test_unknown_outcome_stops_remaining(
        self,
        mock_render,
        mock_config,
        mock_profile,
        mock_manifest,
        mock_eval_ready,
        approval_file: Path,
        manifest_file: Path,
    ):
        from app.evaluation.profile_testbot.campaign.semi_auto_contract import ReplyVerification

        mock_eval_ready.return_value = self._ready_execution_readiness()
        mock_config.return_value = MagicMock(
            sender_emails=["sender@eval.test"],
            recipient_emails=[APPROVED_RECIPIENT],
        )
        rows = [row for row in _render_rows_pass() if row["scenario_id"] == "PTB-DCQ-0000"]
        mock_render.return_value = rows
        mock_profile.return_value = MagicMock()
        scenario = self._scenario("PTB-DCQ-0000", "send_after_approval")
        mock_manifest.return_value = MagicMock(scenarios=[scenario])
        approved_hash = R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0000"]

        backend = MagicMock()
        backend.gmail_sends = 0
        backend.sent_keys = set()
        backend.external_writes = {"sheets": 0, "monday": 0, "visma": 0}
        backend.automatic_verify_link_merge = 0
        backend.send_test_message.return_value = MagicMock(
            provider_message_id="msg-1",
            inbound_provider_message_id="in-1",
            inbound_rfc_message_id="rfc-1",
        )
        backend.observe_intake.return_value = MagicMock(tenant_id=LIVE_EVAL_TENANT_ID)
        backend.observe_processing.return_value = MagicMock(
            approval_state="pending",
            draft_text="pipeline draft differs",
        )
        backend.bind_frozen_send_body = MagicMock()
        backend.approve_via_lifecycle.return_value = MagicMock(
            already_resolved=False,
            reply_action_operation_id="reply-op",
        )
        backend.verify_reply.return_value = ReplyVerification(
            execution_intents=1,
            adapter_invocations=0,
            provider_accepted=False,
            recipient_verified=False,
            duplicate_send=False,
            reply_hash=None,
            reply_execution_status="outcome_unknown",
        )

        with patch(
            "app.evaluation.profile_testbot.qualification.coworker_r3_execution.COWORKER_LIVE_CANARY_SCENARIO_IDS",
            ("PTB-DCQ-0000",),
        ):
            result = run_r3_live_canary(
                mode="execute",
                manifest_path=manifest_file,
                approval_path=approval_file,
                expected_runtime_sha="c" * 40,
                repo_root=REPO_ROOT,
                backend=backend,
            )
        assert result.unknown_outcomes == 1
        assert result.overall_status == "PARTIAL"
        assert len(result.scenario_outcomes) == 1


class TestR3Reports:
    def test_write_execution_reports_no_secrets(self, tmp_path: Path):
        result = R3ExecutionResult(
            mode="dry_run",
            campaign_id="camp-1",
            runtime_sha="c" * 40,
            manifest_hash=COWORKER_LIVE_CANARY_MANIFEST_HASH,
            approval_artifact_hash="a" * 64,
            overall_status="DRY_RUN_PASS",
            planned_sends=8,
            successful_sends=0,
            failed_sends=0,
            unknown_outcomes=0,
            no_send_verified=7,
            duplicates_blocked=0,
            human_render_rereview_required=False,
            stop_reason=None,
            scenario_outcomes=[
                R3ScenarioOutcome(
                    scenario_id="PTB-DCQ-0000",
                    planned_gmail_send=True,
                    status="dry_run_planned",
                    recipient_redacted="ni…@sol-f.se",
                )
            ],
        )
        paths = write_execution_reports(result=result, status_dir=tmp_path)
        blob = paths["summary_json"].read_text(encoding="utf-8")
        assert "ya29." not in blob
        assert "@sol-f.se" not in blob or "ni…@" in blob
