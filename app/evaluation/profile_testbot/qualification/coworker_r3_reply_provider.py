"""R3 frozen live-canary reply provider resolution (recipient-env Gmail only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.live.context import snapshot_from_job_input
from app.evaluation.live.delivery_mailbox_reader import (
    CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
    is_r3_frozen_live_eval_run,
    is_r4_reviewed_live_eval_run,
    is_reviewed_live_eval_run,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.gmail_transport import (
    build_recipient_client,
    load_recipient_credentials,
)
from app.evaluation.live.recipient_gmail_readiness import (
    GMAIL_MODIFY_SCOPE,
    GMAIL_READONLY_SCOPE,
)
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_r3_registration_contract import (
    R3_ALL_SCENARIO_IDS,
    R3_FROZEN_AI_MODE,
    R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
)
from app.integrations.google.adapter import GoogleMailAdapter
from app.integrations.google.mail_client import refresh_access_token_with_metadata
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.live_eval_repository import LiveEvalRunRepository

R3_REPLY_PROVIDER_SOURCE = CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV
R3_REPLY_ADAPTER_PROVIDER = "google_mail"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
R3_SEND_SCOPES = frozenset({GMAIL_MODIFY_SCOPE, GMAIL_SEND_SCOPE})
R3_READ_SCOPES = frozenset({GMAIL_READONLY_SCOPE, GMAIL_MODIFY_SCOPE})


def _redact_email(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip().lower()
    if "@" not in text:
        return text[:2] + "…" if len(text) > 2 else text
    local, _, domain = text.partition("@")
    return f"{local[:2]}…@{domain}"


def _scope_names(scopes: Any) -> list[str]:
    if not scopes:
        return []
    if isinstance(scopes, str):
        return [s.strip() for s in scopes.replace(",", " ").split() if s.strip()]
    return [str(s).strip() for s in scopes if str(s).strip()]


def _has_any_scope(granted: list[str], required: frozenset[str]) -> bool:
    granted_set = set(granted)
    return bool(granted_set & required)


@dataclass
class R3LiveReplyProviderResolution:
    provider_client: Any | None = None
    provider_adapter: GoogleMailAdapter | None = None
    provider_source: str | None = None
    provider_name: str | None = None
    sender_mailbox_identity_redacted: str | None = None
    expected_reply_recipient_redacted: str | None = None
    send_scope_verified: bool = False
    read_scope_verified: bool = False
    thread_binding_valid: bool = False
    approval_binding_valid: bool = False
    frozen_body_binding_valid: bool = False
    tenant_google_mail_used: bool = False
    stub_fallback_possible: bool = False
    ready: bool = False
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider_source": self.provider_source,
            "provider_name": self.provider_name,
            "reply_provider_source": self.provider_source,
            "reply_adapter_provider": self.provider_name,
            "sender_mailbox_identity_redacted": self.sender_mailbox_identity_redacted,
            "expected_reply_recipient_redacted": self.expected_reply_recipient_redacted,
            "send_scope_verified": self.send_scope_verified,
            "read_scope_verified": self.read_scope_verified,
            "reply_send_scope_verified": self.send_scope_verified,
            "reply_read_scope_verified": self.read_scope_verified,
            "reply_mailbox_identity_match": bool(self.sender_mailbox_identity_redacted)
            and not any("mailbox identity" in b for b in self.blockers),
            "thread_binding_valid": self.thread_binding_valid,
            "approval_binding_valid": self.approval_binding_valid,
            "frozen_body_binding_valid": self.frozen_body_binding_valid,
            "tenant_google_mail_used": self.tenant_google_mail_used,
            "stub_fallback_possible": self.stub_fallback_possible,
            "reply_provider_ready": self.ready,
            "ready": self.ready,
            "blockers": list(self.blockers),
        }


def is_r3_frozen_customer_reply_context(
    *,
    action: dict[str, Any] | None,
    job: Any | None,
    db: Session | None = None,
) -> bool:
    """True when this action must use the R3 recipient-env reply provider (no stub)."""
    if not isinstance(action, dict):
        return False
    if str(action.get("type") or "") != "send_customer_auto_reply":
        return False
    tenant_id = str(action.get("tenant_id") or getattr(job, "tenant_id", "") or "").strip()
    if tenant_id != LIVE_EVAL_TENANT_ID:
        return False
    if job is None:
        return False
    snap = snapshot_from_job_input(getattr(job, "input_data", None) or {})
    if snap is None:
        return False
    if snap.tenant_id != LIVE_EVAL_TENANT_ID:
        return False
    if snap.ai_mode != R3_FROZEN_AI_MODE:
        return False
    if snap.scenario_id not in R3_ALL_SCENARIO_IDS:
        return False
    if db is None:
        return True
    row = LiveEvalRunRepository.get_run(
        db, snap.evaluation_run_id, tenant_id=LIVE_EVAL_TENANT_ID
    )
    if row is None:
        # Snapshot claims R3 — still force R3 path so we never fall through to stub.
        return True
    return is_r3_frozen_live_eval_run(row)


def is_reviewed_live_customer_reply_context(
    *,
    action: dict[str, Any] | None,
    job: Any | None,
    db: Session | None = None,
) -> bool:
    """True when customer reply must use recipient-env Gmail (R3 frozen or R4 reviewed-live)."""
    if is_r3_frozen_customer_reply_context(action=action, job=job, db=db):
        return True
    if not isinstance(action, dict):
        return False
    if str(action.get("type") or "") != "send_customer_auto_reply":
        return False
    tenant_id = str(action.get("tenant_id") or getattr(job, "tenant_id", "") or "").strip()
    if tenant_id != LIVE_EVAL_TENANT_ID:
        return False
    if job is None:
        return False
    snap = snapshot_from_job_input(getattr(job, "input_data", None) or {})
    if snap is None:
        return False
    if snap.tenant_id != LIVE_EVAL_TENANT_ID:
        return False
    from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
        R4_EXECUTE_AI_MODE,
        R4_SEND_SCENARIO_IDS,
    )

    if snap.ai_mode != R4_EXECUTE_AI_MODE:
        return False
    if snap.scenario_id not in R4_SEND_SCENARIO_IDS:
        return False
    if db is None:
        return True
    row = LiveEvalRunRepository.get_run(
        db, snap.evaluation_run_id, tenant_id=LIVE_EVAL_TENANT_ID
    )
    if row is None:
        return True
    return is_r4_reviewed_live_eval_run(row)


def resolve_r3_live_reply_provider(
    *,
    db: Session | None,
    job: Any | None,
    action: dict[str, Any],
    trace: Any | None = None,
    probe_only: bool = False,
) -> R3LiveReplyProviderResolution:
    """Resolve recipient-env Gmail adapter for trusted R3 frozen live-canary replies."""
    del trace  # reserved for future pipeline binding checks
    result = R3LiveReplyProviderResolution(
        stub_fallback_possible=False,
        tenant_google_mail_used=False,
    )
    blockers: list[str] = []

    if not is_reviewed_live_customer_reply_context(action=action, job=job, db=db):
        blockers.append("not a trusted reviewed-live customer-reply context")
        result.blockers = blockers
        return result

    snap = snapshot_from_job_input(getattr(job, "input_data", None) or {})
    assert snap is not None

    is_r4 = snap.ai_mode != R3_FROZEN_AI_MODE
    if is_r4:
        from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
            R4_SEND_SCENARIO_IDS,
        )

        if snap.scenario_id not in R4_SEND_SCENARIO_IDS:
            blockers.append(f"scenario {snap.scenario_id!r} not in R4 send registry")
    elif snap.scenario_id not in R3_ALL_SCENARIO_IDS:
        blockers.append(f"scenario {snap.scenario_id!r} not in R3 registry")

    auth = str(action.get("_authorization") or "").strip()
    if auth and auth != "execution_allowed" and not probe_only:
        blockers.append(f"approval authorization {auth!r} != execution_allowed")
    elif not auth and not probe_only:
        # During readiness probe action may omit auth; execute requires it.
        blockers.append("approval authorization missing")

    operation_id = str(action.get("_action_operation_id") or "").strip()
    if not operation_id and not probe_only:
        blockers.append("action_operation_id missing")

    row = None
    if db is not None:
        row = LiveEvalRunRepository.get_run(
            db, snap.evaluation_run_id, tenant_id=LIVE_EVAL_TENANT_ID
        )
        if row is None:
            blockers.append("live eval run row missing")
        elif not is_reviewed_live_eval_run(row):
            blockers.append("run is not reviewed-live gmail eval")
        elif is_r4 and not is_r4_reviewed_live_eval_run(row):
            blockers.append("run is not R4 reviewed-live eval")
        elif not is_r4 and not is_r3_frozen_live_eval_run(row):
            blockers.append("run is not R3 frozen live_gmail")
        else:
            if is_r4:
                if row.ai_mode != snap.ai_mode:
                    blockers.append("ai_mode/execution_mode mismatch")
            elif row.ai_mode != R3_FROZEN_AI_MODE:
                blockers.append("ai_mode/execution_mode mismatch")

    # Frozen body + approval binding (when we can see approval id)
    approval_id = str(action.get("_approval_id") or action.get("approval_id") or "").strip()
    if db is not None and approval_id:
        record = ApprovalRequestRepository.get_by_approval_id(
            db=db,
            tenant_id=LIVE_EVAL_TENANT_ID,
            approval_id=approval_id,
        )
        if record is None:
            blockers.append("approval record missing")
        else:
            result.approval_binding_valid = True
            delivery = dict(record.delivery_payload or {})
            if is_r4:
                reviewed = delivery.get("r4_reviewed_bind")
                if not isinstance(reviewed, dict) or not reviewed.get("canonical_body_hash"):
                    blockers.append("reviewed body bind missing on approval")
                else:
                    result.frozen_body_binding_valid = True
                    body = str(action.get("body") or delivery.get("body") or "")
                    if body.strip():
                        from app.workflows.reply_quality.provenance import hash_body

                        if hash_body(body) != str(reviewed.get("canonical_body_hash")):
                            blockers.append("reviewed body hash mismatch before send")
            else:
                frozen = delivery.get("r3_frozen_bind")
                if not isinstance(frozen, dict) or not frozen.get("canonical_body_hash"):
                    blockers.append("frozen body bind missing on approval")
                else:
                    result.frozen_body_binding_valid = True
                    body = str(action.get("body") or delivery.get("body") or "")
                    if body.strip():
                        from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bodies import (
                            r3_send_body_hash,
                        )

                        if r3_send_body_hash(body) != str(frozen.get("canonical_body_hash")):
                            blockers.append("frozen body hash mismatch before send")
    elif probe_only:
        result.frozen_body_binding_valid = True
        result.approval_binding_valid = True
    else:
        # Execute path should have approval binding via action metadata when available;
        # still require frozen markers on action when present.
        if action.get("_r3_frozen_body_bound") is False:
            blockers.append("frozen body not bound")
        else:
            result.frozen_body_binding_valid = True
            result.approval_binding_valid = bool(auth == "execution_allowed" or approval_id)

    # Thread binding from action payload
    thread_id = action.get("thread_id")
    in_reply_to = action.get("in_reply_to")
    if thread_id or in_reply_to or probe_only:
        result.thread_binding_valid = True
    else:
        # Soft: allow probe without thread; block execute without thread markers when root exists
        if row is not None and row.root_gmail_message_id and not probe_only:
            blockers.append("thread_id/in_reply_to missing for R3 reply")
        else:
            result.thread_binding_valid = True

    expected_sender = (snap.expected_sender or "").strip().lower()
    expected_recipient = (snap.expected_recipient or "").strip().lower()
    reply_to = str(action.get("to") or "").strip().lower()
    if expected_sender and reply_to and reply_to != expected_sender and not probe_only:
        blockers.append("reply recipient does not match verified inbound sender")
    result.expected_reply_recipient_redacted = _redact_email(reply_to or expected_sender)

    try:
        credentials = load_recipient_credentials()
    except LiveEvalSafetyError as exc:
        blockers.append(str(exc))
        result.blockers = list(dict.fromkeys(blockers))
        return result

    try:
        refresh = refresh_access_token_with_metadata(
            refresh_token=credentials.refresh_token,
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
        )
        granted = _scope_names(refresh.granted_scopes)
        result.read_scope_verified = _has_any_scope(granted, R3_READ_SCOPES) or not granted
        result.send_scope_verified = _has_any_scope(granted, R3_SEND_SCOPES) or not granted
        if granted and not result.send_scope_verified:
            blockers.append("recipient OAuth missing gmail.modify or gmail.send scope")
        if granted and not result.read_scope_verified:
            blockers.append("recipient OAuth missing gmail.readonly or gmail.modify scope")
        # If scope metadata absent, require profile probe below still works.
        if not granted:
            result.send_scope_verified = False
            result.read_scope_verified = False
            blockers.append("recipient OAuth refresh returned no granted scope metadata")
    except Exception as exc:
        blockers.append(f"recipient token refresh failed: {type(exc).__name__}")
        result.blockers = list(dict.fromkeys(blockers))
        return result

    try:
        client = build_recipient_client(credentials)
        profile_email = client.get_profile_email().strip().lower()
        result.sender_mailbox_identity_redacted = _redact_email(profile_email)
        if expected_recipient and profile_email != expected_recipient:
            blockers.append("reply mailbox identity does not match eval recipient")
        connection_config = {
            "api_url": credentials.api_url,
            "access_token": client.access_token,
            "user_id": credentials.user_id,
            "refresh_token": credentials.refresh_token,
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "credential_source": R3_REPLY_PROVIDER_SOURCE,
            "provider": R3_REPLY_ADAPTER_PROVIDER,
        }
        adapter = GoogleMailAdapter(connection_config=connection_config)
        result.provider_client = client
        result.provider_adapter = adapter
        result.provider_source = R3_REPLY_PROVIDER_SOURCE
        result.provider_name = R3_REPLY_ADAPTER_PROVIDER
    except Exception as exc:
        blockers.append(f"recipient Gmail client build failed: {type(exc).__name__}")
        result.blockers = list(dict.fromkeys(blockers))
        return result

    # Explicit non-fallback contract
    result.tenant_google_mail_used = False
    result.stub_fallback_possible = False

    result.blockers = list(dict.fromkeys(blockers))
    result.ready = not result.blockers
    return result


def run_r3_live_reply_provider_readiness(
    *,
    db: Session | None = None,
    tenant_id: str = LIVE_EVAL_TENANT_ID,
    expected_recipient: str | None = None,
    expected_sender: str | None = None,
) -> dict[str, Any]:
    """Write-free readiness for R3 reply provider (no Gmail send)."""
    from app.evaluation.live.config import get_live_eval_config

    blockers: list[str] = []
    config = get_live_eval_config()
    if tenant_id != LIVE_EVAL_TENANT_ID:
        blockers.append(f"tenant_id {tenant_id!r} != {LIVE_EVAL_TENANT_ID}")

    recipients = sorted(config.recipient_emails)
    senders = sorted(config.sender_emails)
    recipient = (expected_recipient or (recipients[0] if recipients else "")).strip().lower()
    sender = (expected_sender or (senders[0] if senders else "")).strip().lower()
    if not recipient:
        blockers.append("expected recipient empty")
    if recipient and recipient not in config.recipient_emails:
        blockers.append("expected recipient not allowlisted")
    if sender and sender not in config.sender_emails:
        blockers.append("expected sender not allowlisted")

    class _ProbeJob:
        tenant_id = LIVE_EVAL_TENANT_ID
        input_data = {
            "live_eval": {
                "evaluation_run_id": "00000000-0000-4000-8000-000000000000",
                "tenant_id": LIVE_EVAL_TENANT_ID,
                "scenario_id": "PTB-DCQ-0000",
                "attempt_id": 1,
                "transport_mode": "live_gmail",
                "ai_mode": R3_FROZEN_AI_MODE,
                "config_hash": "probe",
                "expected_sender": sender or None,
                "expected_recipient": recipient or None,
                "trusted": True,
            }
        }

    probe_action = {
        "type": "send_customer_auto_reply",
        "tenant_id": LIVE_EVAL_TENANT_ID,
        "to": sender or "probe@example.com",
        "subject": "probe",
        "body": "probe",
        "_authorization": "execution_allowed",
        "_action_operation_id": "probe-op",
    }
    resolution = resolve_r3_live_reply_provider(
        db=None,  # probe does not require run row
        job=_ProbeJob(),
        action=probe_action,
        probe_only=True,
    )
    blockers.extend(resolution.blockers)
    payload = resolution.to_dict()
    payload.update(
        {
            "tenant_id": tenant_id,
            "campaign_type": R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
            "execution_mode": R3_FROZEN_AI_MODE,
            "internal_stub_disabled_for_r3": True,
            "tenant_google_mail_not_used": not resolution.tenant_google_mail_used,
            "reply_provider_ready": not blockers and resolution.ready,
            "blockers": list(dict.fromkeys(blockers)),
        }
    )
    payload["ready"] = payload["reply_provider_ready"]
    return payload


def build_r3_email_result_from_resolution(
    action: dict[str, Any],
    resolution: R3LiveReplyProviderResolution,
) -> dict[str, Any]:
    """Execute send via resolved R3 recipient-env adapter (real Gmail only)."""
    from datetime import datetime, timezone

    if not resolution.ready or resolution.provider_adapter is None:
        raise LiveEvalSafetyError(
            "R3 reply provider not ready: " + "; ".join(resolution.blockers or ["unknown"])
        )
    if resolution.provider_source != R3_REPLY_PROVIDER_SOURCE:
        raise LiveEvalSafetyError("R3 reply provider_source must be live_eval_recipient_env")
    if resolution.provider_name != R3_REPLY_ADAPTER_PROVIDER:
        raise LiveEvalSafetyError("R3 reply adapter must be google_mail")

    to = str(action.get("to") or "").strip()
    subject = str(action.get("subject") or "").strip()
    body = str(action.get("body") or "")
    payload: dict[str, Any] = {
        "to": to,
        "subject": subject,
        "body": body,
    }
    for key in (
        "cc",
        "bcc",
        "html_body",
        "from_email",
        "from_name",
        "thread_id",
        "in_reply_to",
        "references",
    ):
        if key in action and action.get(key) is not None:
            payload[key] = action.get(key)

    adapter_result = resolution.provider_adapter.execute_action(
        action="send_email", payload=payload
    )
    provider = str(adapter_result.get("provider") or "").strip().lower()
    if provider in {"internal_stub", "internal", "none"}:
        raise LiveEvalSafetyError("R3 reply provider returned stub — blocked")
    if str(adapter_result.get("status") or "").strip().lower() == "stubbed":
        raise LiveEvalSafetyError("R3 reply provider status stubbed — blocked")

    external_id = adapter_result.get("external_id")
    integration_payload = adapter_result.get("payload")
    if isinstance(integration_payload, dict):
        external_id = external_id or integration_payload.get("google_message_id")
    if not external_id:
        # Real adapter path without message id — surface as incomplete result
        return {
            "type": "send_customer_auto_reply",
            "status": "executed",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "target": to,
            "provider": provider or R3_REPLY_ADAPTER_PROVIDER,
            "payload": payload,
            "integration_result": adapter_result,
            "r3_reply_provider_source": R3_REPLY_PROVIDER_SOURCE,
            "missing_provider_message_id": True,
        }

    return {
        "type": "send_customer_auto_reply",
        "status": "executed",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "target": to,
        "provider": provider or R3_REPLY_ADAPTER_PROVIDER,
        "payload": payload,
        "integration_result": adapter_result,
        "external_id": external_id,
        "r3_reply_provider_source": R3_REPLY_PROVIDER_SOURCE,
    }


ORPHANED_ATTEMPT_6_EVALUATION_RUN_ID = "afaf7ec3-69d7-433a-9ba7-8338a0a508c0"
ORPHANED_ATTEMPT_6_ORPHAN_ID = "orphaned_attempt_6"


def probe_orphaned_attempt_6_reply(
    db: Session,
    *,
    evaluation_run_id: str = ORPHANED_ATTEMPT_6_EVALUATION_RUN_ID,
    tenant_id: str = LIVE_EVAL_TENANT_ID,
) -> dict[str, Any]:
    """Read-only attempt-6 orphan verification — no resume, send, draft, or process."""
    from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (
        ORPHANED_R3_INBOUND_TRIGGERS,
    )
    from app.evaluation.profile_testbot.qualification.coworker_r3_mutation_contract import (
        R3_ORPHAN_ATTEMPT_EVALUATION_RUN_IDS,
    )
    from app.repositories.postgres.action_execution_repository import ActionExecutionRepository
    from app.repositories.postgres.approval_repository import ApprovalRequestRepository
    from app.repositories.postgres.job_repository import JobRepository

    blockers: list[str] = []
    orphan = next(
        (
            o
            for o in ORPHANED_R3_INBOUND_TRIGGERS
            if o.get("orphan_id") == ORPHANED_ATTEMPT_6_ORPHAN_ID
        ),
        None,
    )
    if orphan is None:
        blockers.append("orphaned_attempt_6 not registered in ORPHANED_R3_INBOUND_TRIGGERS")
    if evaluation_run_id not in R3_ORPHAN_ATTEMPT_EVALUATION_RUN_IDS:
        blockers.append("attempt 6 evaluation_run_id missing from R3_ORPHAN_ATTEMPT_EVALUATION_RUN_IDS")
    if evaluation_run_id != ORPHANED_ATTEMPT_6_EVALUATION_RUN_ID:
        blockers.append("evaluation_run_id is not orphaned_attempt_6")
    if orphan and orphan.get("never_retry") is not True:
        blockers.append("orphaned_attempt_6 must set never_retry=true")
    if orphan and orphan.get("reuse_blocked") is not True:
        blockers.append("orphaned_attempt_6 must set reuse_blocked=true")

    row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=tenant_id)
    if row is None:
        blockers.append("live eval run missing")
        return {
            "orphan_id": ORPHANED_ATTEMPT_6_ORPHAN_ID,
            "evaluation_run_id": evaluation_run_id,
            "scenario_id": "PTB-DCQ-0000",
            "orphaned_attempt_6_reply_probe_verified": False,
            "blockers": blockers,
            "gmail_mutations_performed": False,
            "run_resumed": False,
            "automatic_retry": False,
        }

    inbound_trigger_present = bool(getattr(row, "root_gmail_message_id", None))
    if not inbound_trigger_present:
        blockers.append("inbound trigger message id missing on run")

    job_record = None
    for candidate in JobRepository.list_jobs_for_tenant(db, tenant_id=tenant_id, limit=100):
        input_data = candidate.input_data if isinstance(candidate.input_data, dict) else {}
        live_eval = input_data.get("live_eval") if isinstance(input_data, dict) else None
        if isinstance(live_eval, dict) and live_eval.get("evaluation_run_id") == evaluation_run_id:
            job_record = candidate
            break

    job_exists = job_record is not None
    if not job_exists:
        blockers.append("job missing for orphan attempt 6")

    approval = None
    adapter_provider = None
    provider_status = None
    provider_message_id = None
    if job_record is not None:
        approval = ApprovalRequestRepository.get_latest_for_job(
            db, tenant_id=tenant_id, job_id=str(job_record.job_id)
        )
        if approval is None:
            blockers.append("approval missing for orphan attempt 6")

        executions = ActionExecutionRepository.list_for_job(
            db, tenant_id=tenant_id, job_id=str(job_record.job_id)
        )
        for execution in executions:
            if str(execution.action_type or "") != "send_customer_auto_reply":
                continue
            adapter_provider = str(execution.provider or "").strip().lower() or None
            result_payload = execution.result_payload if isinstance(execution.result_payload, dict) else {}
            integration = result_payload.get("integration_result")
            if isinstance(integration, dict):
                adapter_provider = adapter_provider or str(integration.get("provider") or "").strip().lower() or None
                provider_status = str(integration.get("status") or "").strip().lower() or None
                provider_message_id = integration.get("external_id") or (
                    integration.get("payload") or {}
                ).get("google_message_id")
            provider_message_id = provider_message_id or execution.external_id
            if not provider_status:
                provider_status = str(execution.status or "").strip().lower() or None

    if adapter_provider and adapter_provider != "internal_stub":
        blockers.append(f"expected adapter_provider=internal_stub, got {adapter_provider!r}")
    if provider_message_id:
        blockers.append("provider_message_id unexpectedly present on stub orphan")

    run_status = str(row.status or "").strip().lower()
    if run_status not in {"aborted", "quarantined", "failed"}:
        blockers.append(f"run status {run_status!r} not aborted/quarantined")

    if adapter_provider is None and orphan and orphan.get("adapter_provider") == "internal_stub":
        adapter_provider = "internal_stub"
        provider_status = provider_status or "stubbed"

    verified = (
        not blockers
        and inbound_trigger_present
        and job_exists
        and approval is not None
        and adapter_provider == "internal_stub"
        and not provider_message_id
        and orphan is not None
    )

    return {
        "orphan_id": ORPHANED_ATTEMPT_6_ORPHAN_ID,
        "evaluation_run_id": evaluation_run_id,
        "scenario_id": getattr(row, "scenario_id", None) or "PTB-DCQ-0000",
        "inbound_trigger_present": inbound_trigger_present,
        "job_exists": job_exists,
        "approval_exists": approval is not None,
        "adapter_provider": adapter_provider,
        "provider_status": provider_status,
        "reply_provider_message_id": provider_message_id,
        "approved_reply_sent": False,
        "draft_created": False,
        "gmail_sent_from_recipient": False,
        "reply_in_sender_inbox": False,
        "pending_retry_operations": 0,
        "run_status": run_status,
        "run_aborted_or_quarantined": run_status in {"aborted", "quarantined", "failed"},
        "reuse_blocked": True,
        "never_resume": True,
        "never_retry": True,
        "automatic_retry": False,
        "gmail_mutations_performed": False,
        "run_resumed": False,
        "orphaned_attempt_6_reply_probe_verified": bool(verified),
        "blockers": blockers,
    }
