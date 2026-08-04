"""Tests for R3 frozen live-canary mutation contract and intake credential parity."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

pytest_plugins = ["tests.evaluation.live.conftest"]

from app.evaluation.live.delivery_mailbox_reader import (
    CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
    CREDENTIAL_SOURCE_TENANT_GOOGLE_MAIL,
    DeliveryMailboxReaderResolution,
    GoogleMailClientDeliveryReader,
    is_r3_frozen_live_eval_run,
    probe_orphan_intake_observation,
)
from app.evaluation.live.errors import LiveEvalSafetyError, LiveEvalSafetyRejectedError
from app.evaluation.live.safety import validate_live_gmail_run_for_mutation
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_live_canary_manifest import (
    COWORKER_LIVE_CANARY_MANIFEST_HASH,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
    ORPHANED_R3_INBOUND_TRIGGERS,
    _format_safety_rejected,
    run_r3_live_canary,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_mutation_contract import (
    R3_MUTATION_BIND_FROZEN_BODY,
    R3_MUTATION_PROCESS_DELIVERY,
    R3_ORPHAN_ATTEMPT_EVALUATION_RUN_IDS,
    ReaderMailboxAdapter,
    validate_r3_frozen_live_run_contract,
    validate_r3_process_delivery_readiness,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_registration_contract import (
    R3_FROZEN_EXECUTION_MODE,
    R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
)
from app.repositories.postgres.live_eval_models import LiveEvalExternalEventRow, LiveEvalRunRow


RUNTIME_SHA = "c87ac36c391285c87fd44a665be277a533a76897"
R3_RECIPIENT = "niklas.palm@sol-f.se"
R3_SENDER = "qvarsken@gmail.com"


@pytest.fixture
def live_eval_env(monkeypatch):
    """Override plugin fixture with R3-approved sender/recipient allowlist."""
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_GMAIL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", LIVE_EVAL_TENANT_ID)
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", R3_SENDER)
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", R3_RECIPIENT)
    monkeypatch.setenv("LIVE_EVAL_GMAIL_LABEL", "krowolf-live-eval")
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_QUALITY_APPROVED", "yes")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED", "yes")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED_SHA", RUNTIME_SHA)
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


@pytest.fixture(autouse=True)
def runtime_sha_env(monkeypatch):
    monkeypatch.setenv("BUILD_GIT_SHA", RUNTIME_SHA)


def _seed_eval_tenant(db) -> None:
    from app.repositories.postgres.tenant_config_models import TenantConfigRecord

    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).replace(microsecond=0).isoformat()
    db.add(
        TenantConfigRecord(
            tenant_id=LIVE_EVAL_TENANT_ID,
            name="Live Eval",
            slug="live-eval",
            status="active",
            lifecycle_status="active",
            is_test_tenant=True,
            allowed_integrations=["google_mail"],
            enabled_job_types=["lead", "customer_inquiry", "invoice"],
            settings={
                "intake": {"enabled": True, "intake_cutoff_at": cutoff},
                "live_eval": {"seeded": True},
            },
        )
    )
    db.commit()


def _r3_row(**overrides) -> LiveEvalRunRow:
    now = datetime.now(timezone.utc)
    base = LiveEvalRunRow(
        evaluation_run_id="run-r3-new",
        tenant_id=LIVE_EVAL_TENANT_ID,
        scenario_id="PTB-DCQ-0000",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode=R3_FROZEN_EXECUTION_MODE,
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender=R3_SENDER,
        expected_recipient=R3_RECIPIENT,
        status="registered",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="abc",
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _quality_row() -> LiveEvalRunRow:
    now = datetime.now(timezone.utc)
    return LiveEvalRunRow(
        evaluation_run_id="run-quality",
        tenant_id=LIVE_EVAL_TENANT_ID,
        scenario_id="PTB-Q96-0000",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="live_llm",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender=R3_SENDER,
        expected_recipient=R3_RECIPIENT,
        status="registered",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="abc",
    )


def test_r3_frozen_run_allowed_through_validate_live_gmail_run_for_mutation(db, live_eval_env):
    row = _r3_row()
    db.add(row)
    db.add(
        LiveEvalExternalEventRow(
            event_key="evt-r3-allow",
            operation_key="op-r3-allow",
            tenant_id=row.tenant_id,
            evaluation_run_id=row.evaluation_run_id,
            integration_type="google_mail",
            category="app_live_eval_delivery_observed",
            operation="msg-new-0001",
            outcome="succeeded",
            started_at=datetime.now(timezone.utc),
            redacted_metadata={"recipient_gmail_message_id": "msg-new-0001"},
        )
    )
    db.commit()
    validate_live_gmail_run_for_mutation(
        row,
        tenant_id=LIVE_EVAL_TENANT_ID,
        recipient_message_id="msg-new-0001",
        mutation_operation=R3_MUTATION_PROCESS_DELIVERY,
        db=db,
    )


def test_quality_live_gmail_still_requires_live_llm(db, live_eval_env):
    row = _quality_row()
    row.ai_mode = "fixture_ai"
    db.add(row)
    db.commit()
    with pytest.raises(LiveEvalSafetyError, match="live_llm"):
        validate_live_gmail_run_for_mutation(
            row,
            tenant_id=LIVE_EVAL_TENANT_ID,
            recipient_message_id="msg-1",
            db=db,
        )


def test_r3_frozen_wrong_campaign_type_blocked():
    row = _r3_row()
    with pytest.raises(LiveEvalSafetyError):
        validate_r3_frozen_live_run_contract(
            row,
            tenant_id=LIVE_EVAL_TENANT_ID,
            operation=R3_MUTATION_PROCESS_DELIVERY,
            recipient_message_id="msg-1",
            campaign_type="wrong_campaign",
        )


def test_r3_frozen_wrong_tenant_blocked():
    row = _r3_row(tenant_id="T_OTHER")
    with pytest.raises(LiveEvalSafetyError):
        validate_r3_frozen_live_run_contract(
            row,
            tenant_id="T_OTHER",
            operation=R3_MUTATION_PROCESS_DELIVERY,
            recipient_message_id="msg-1",
        )


def test_r3_scenario_outside_registry_blocked():
    row = _r3_row(scenario_id="PTB-UNKNOWN-9999")
    with pytest.raises(LiveEvalSafetyError, match="not in R3 frozen allowlist"):
        validate_r3_frozen_live_run_contract(
            row,
            tenant_id=LIVE_EVAL_TENANT_ID,
            operation=R3_MUTATION_PROCESS_DELIVERY,
            recipient_message_id="msg-1",
        )


def test_unknown_r3_mutation_operation_blocked(live_eval_env):
    row = _r3_row()
    with pytest.raises(LiveEvalSafetyError, match="unknown R3 mutation operation"):
        validate_r3_frozen_live_run_contract(
            row,
            tenant_id=LIVE_EVAL_TENANT_ID,
            operation="delete_everything",
            recipient_message_id="msg-1",
        )


def test_recipient_message_id_mismatch_blocked(db, live_eval_env):
    row = _r3_row(evaluation_run_id="run-bind-test")
    db.add(row)
    db.add(
        LiveEvalExternalEventRow(
            event_key="evt-1",
            operation_key="op-1",
            tenant_id=row.tenant_id,
            evaluation_run_id=row.evaluation_run_id,
            integration_type="google_mail",
            category="app_live_eval_delivery_observed",
            operation="verified-msg-id",
            outcome="succeeded",
            started_at=datetime.now(timezone.utc),
            redacted_metadata={"recipient_gmail_message_id": "verified-msg-id"},
        )
    )
    db.commit()
    with pytest.raises(LiveEvalSafetyError, match="does not match verified delivery candidate"):
        validate_r3_frozen_live_run_contract(
            row,
            tenant_id=LIVE_EVAL_TENANT_ID,
            operation=R3_MUTATION_PROCESS_DELIVERY,
            recipient_message_id="different-msg-id",
            db=db,
        )


def test_manifest_hash_mismatch_blocked():
    row = _r3_row()
    with pytest.raises(LiveEvalSafetyError, match="manifest hash mismatch"):
        validate_r3_frozen_live_run_contract(
            row,
            tenant_id=LIVE_EVAL_TENANT_ID,
            operation=R3_MUTATION_PROCESS_DELIVERY,
            recipient_message_id="msg-1",
            manifest_hash="0" * 64,
        )


def test_r3_reader_adapter_blocks_mark_as_read():
    client = MagicMock()
    client.get_profile_email.return_value = "recipient@eval.test"
    reader = GoogleMailClientDeliveryReader(client)
    adapter = ReaderMailboxAdapter(reader)
    with pytest.raises(LiveEvalSafetyError, match="mark_as_read"):
        adapter.execute_action(action="mark_as_read", payload={"message_id": "m1"})


def test_process_gmail_message_by_id_uses_injected_reader(db, monkeypatch):
    from app.evaluation.live.gmail_intake import process_gmail_message_by_id

    _seed_eval_tenant(db)
    client = MagicMock()
    client.get_profile_email.return_value = R3_RECIPIENT
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    client.get_message.return_value = {
        "from": f"Sender <{R3_SENDER}>",
        "to": R3_RECIPIENT,
        "subject": "Offert solceller",
        "body_text": "Hej, jag vill ha offert på solceller",
        "thread_id": "t1",
        "internal_date_ms": now_ms,
    }
    reader = GoogleMailClientDeliveryReader(client)
    resolution = DeliveryMailboxReaderResolution(
        reader=reader,
        credential_source=CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
        source_allowed=True,
        source_matches_readiness=True,
    )
    monkeypatch.setattr(
        "app.evaluation.live.gmail_intake.get_integration_connection_config",
        MagicMock(side_effect=AssertionError("tenant GOOGLE_MAIL must not be used")),
    )
    monkeypatch.setattr(
        "app.evaluation.live.gmail_intake.classify_email_type",
        lambda subject, body: "customer_inquiry",
    )
    result = process_gmail_message_by_id(
        db,
        LIVE_EVAL_TENANT_ID,
        "msg-1",
        dry_run=True,
        mailbox_resolution=resolution,
    )
    assert result["status"] == "dry_run"
    client.get_message.assert_called_once_with("msg-1")


def test_process_gmail_message_by_id_normal_tenant_path_unchanged(db, monkeypatch):
    from app.evaluation.live.gmail_intake import process_gmail_message_by_id

    _seed_eval_tenant(db)
    adapter = MagicMock()
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    adapter.execute_action.return_value = {
        "message": {
            "from": f"Sender <{R3_SENDER}>",
            "to": R3_RECIPIENT,
            "subject": "Offert solceller",
            "body_text": "Hej, jag vill ha offert",
            "thread_id": "t1",
            "internal_date_ms": now_ms,
        }
    }
    monkeypatch.setattr(
        "app.evaluation.live.gmail_intake.get_integration_connection_config",
        lambda **kwargs: {"metadata_json": {"mailbox_email": R3_RECIPIENT}},
    )
    monkeypatch.setattr(
        "app.evaluation.live.gmail_intake.get_integration_adapter",
        lambda **kwargs: adapter,
    )
    monkeypatch.setattr(
        "app.evaluation.live.gmail_intake.resolve_canonical_recipient_email",
        lambda *args, **kwargs: (R3_RECIPIENT, None),
    )
    monkeypatch.setattr(
        "app.evaluation.live.gmail_intake.classify_email_type",
        lambda subject, body: "customer_inquiry",
    )
    result = process_gmail_message_by_id(
        db,
        LIVE_EVAL_TENANT_ID,
        "msg-1",
        dry_run=True,
    )
    assert result["status"] == "dry_run"
    adapter.execute_action.assert_called()


def test_orphan_attempt_4_listed_and_not_approved_reply():
    orphan = next(o for o in ORPHANED_R3_INBOUND_TRIGGERS if o["orphan_id"] == "orphaned_attempt_4")
    assert orphan["evaluation_run_id"] == "ccd9916f-c4b7-4b1c-aabc-fb2da09f89cf"
    assert orphan["approved_reply_sent"] is False
    assert orphan["exclude_from_approved_reply_count"] is True


def test_live_eval_safety_rejected_error_structured_outcome():
    exc = LiveEvalSafetyRejectedError(
        {
            "safety_reason": "profile testbot quality live_gmail requires ai_mode live_llm",
            "failed_stage": "triggering_intake",
            "http_status": 400,
        }
    )
    formatted = _format_safety_rejected(exc)
    assert "intake_observation" in formatted or "triggering_intake" in formatted
    assert "live_llm" in formatted
    assert "ya29." not in formatted


def test_r3_contract_constants():
    assert is_r3_frozen_live_eval_run(_r3_row()) is True
    assert R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE == "coworker_r3_frozen_live_canary"
    assert COWORKER_LIVE_CANARY_MANIFEST_HASH
    assert "ccd9916f-c4b7-4b1c-aabc-fb2da09f89cf" in R3_ORPHAN_ATTEMPT_EVALUATION_RUN_IDS


def test_orphan_intake_probe_does_not_create_job(db, live_eval_env, monkeypatch):
    row = _r3_row(evaluation_run_id="ccd9916f-c4b7-4b1c-aabc-fb2da09f89cf")
    db.add(row)
    db.add(
        LiveEvalExternalEventRow(
            event_key="evt-orphan4",
            operation_key="op-orphan4",
            tenant_id=row.tenant_id,
            evaluation_run_id=row.evaluation_run_id,
            integration_type="google_mail",
            category="app_live_eval_delivery_observed",
            operation="19fcbf106af3cdb3",
            outcome="succeeded",
            started_at=datetime.now(timezone.utc),
            redacted_metadata={"recipient_gmail_message_id": "19fcbf106af3cdb3"},
        )
    )
    db.commit()

    message = {
        "from": f"Sender <{R3_SENDER}>",
        "to": R3_RECIPIENT,
        "subject": f"KROWOLF-EVAL/{row.evaluation_run_id}/{row.scenario_id}/1 | test",
        "body_text": "KROWOLF-BODY-MARKER/attempt-4",
        "thread_id": "t1",
    }

    client = MagicMock()
    client.get_profile_email.return_value = "recipient@eval.test"
    client.list_labels.return_value = [{"id": "LBL", "name": "krowolf-live-eval"}]
    client.get_message.return_value = message
    reader = GoogleMailClientDeliveryReader(client)

    with patch(
        "app.evaluation.live.delivery_mailbox_reader.resolve_delivery_mailbox_reader",
        return_value=DeliveryMailboxReaderResolution(
            reader=reader,
            credential_source=CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
            source_allowed=True,
            source_matches_readiness=True,
        ),
    ), patch(
        "app.evaluation.live.delivery.observe_delivery_candidates",
    ) as observe:
        from app.evaluation.live.delivery import DeliveryCandidate, DeliveryObservationResult

        observe.return_value = DeliveryObservationResult(
            candidate_count=1,
            valid_count=1,
            duplicate_detected=False,
            confirmed=DeliveryCandidate(
                message_id="19fcbf106af3cdb3",
                thread_id="t1",
                rfc_message_id="<rfc@test>",
                sender_email=R3_SENDER,
                recipient_email=R3_RECIPIENT,
            ),
            rejection_reasons=[],
        )
        result = probe_orphan_intake_observation(
            db,
            row=row,
            classification="orphaned_attempt_4_intake_probe_verified",
        )

    assert result.job_created is False
    assert result.run_status_changed is False
    assert result.gmail_mutations_performed is False
    db.refresh(row)
    assert row.root_job_id is None


def test_validate_r3_process_delivery_readiness_without_db_row_fields(db, live_eval_env):
    row = _r3_row()
    db.add(row)
    _seed_eval_tenant(db)
    with patch(
        "app.evaluation.profile_testbot.qualification.coworker_r3_mutation_contract.resolve_delivery_mailbox_reader",
        return_value=DeliveryMailboxReaderResolution(
            reader=MagicMock(),
            credential_source=CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
            source_allowed=True,
            source_matches_readiness=True,
        ),
    ):
        result = validate_r3_process_delivery_readiness(
            db,
            row=row,
            tenant_id=LIVE_EVAL_TENANT_ID,
        )
    assert result.mutation_contract_valid is True
    assert result.intake_credential_source == CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV


def test_bind_operation_requires_active_run(live_eval_env):
    row = _r3_row(status="registered")
    with pytest.raises(LiveEvalSafetyError, match="does not allow mutation"):
        validate_r3_frozen_live_run_contract(
            row,
            tenant_id=LIVE_EVAL_TENANT_ID,
            operation=R3_MUTATION_BIND_FROZEN_BODY,
            recipient_message_id="msg-1",
        )
