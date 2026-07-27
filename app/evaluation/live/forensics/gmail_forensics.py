"""Gmail read-only forensics for a single semi-auto scenario execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.constants import SUBJECT_TOKEN_PREFIX
from app.evaluation.live.delivery import mask_email
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.forensics.readonly import (
    assert_readonly_forensics_budget,
    install_readonly_gmail_guard,
)
from app.evaluation.live.gmail_transport import (
    _normalize_rfc_message_id,
    _parse_from_email,
    _rfc822msgid_query,
    _sent_recipient_emails,
    build_recipient_client,
    build_sender_client,
)
from app.evaluation.live.subject_parser import parse_subject_token

_MAX_SEARCH_RESULTS = 5


@dataclass
class MailboxIdentityReport:
    role: str
    profile_email: str | None
    profile_email_masked: str
    expected_allowlist_role: str
    allowlist_match: bool
    read_scope_verified: bool
    issues: list[str] = field(default_factory=list)


@dataclass
class MessageForensics:
    message_id: str
    thread_id: str
    labels: list[str]
    from_masked: str
    to_masked: str
    reply_to_masked: str
    subject_truncated: str
    rfc_message_id: str | None
    in_reply_to: str | None
    references_truncated: str | None
    in_sent: bool
    correlation_match: bool
    body_has_run_id: bool
    body_has_scenario_id: bool


@dataclass
class RecipientSearchResult:
    query: str
    match_count: int
    placement: str | None
    message: MessageForensics | None


@dataclass
class LiveGmailForensicsReport:
    source_workflow_run: str | None
    evaluation_run_id: str
    scenario_id: str
    job_id: str | None
    campaign_run_id: str | None
    runtime_sha: str | None
    sender_identity: MailboxIdentityReport
    recipient_identity: MailboxIdentityReport
    credential_role_collision: bool
    inbound_message: MessageForensics | None
    provider_message_id: str | None
    provider_object: MessageForensics | None
    provider_sent_status: str
    adapter_recipient_masked: str | None
    recipient_searches: list[RecipientSearchResult]
    recipient_verification_status: str
    root_cause_classification: str
    root_cause_subcodes: list[str]
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_workflow_run": self.source_workflow_run,
            "evaluation_run_id": self.evaluation_run_id,
            "scenario_id": self.scenario_id,
            "job_id": self.job_id,
            "campaign_run_id": self.campaign_run_id,
            "runtime_sha": self.runtime_sha,
            "credential_role_collision": self.credential_role_collision,
            "provider_message_id": self.provider_message_id or "not_observed",
            "provider_sent_status": self.provider_sent_status,
            "adapter_recipient_masked": self.adapter_recipient_masked or "not_observed",
            "recipient_verification_status": self.recipient_verification_status,
            "root_cause_classification": self.root_cause_classification,
            "root_cause_subcodes": self.root_cause_subcodes,
            "issues": self.issues,
            "sender_identity": {
                "role": self.sender_identity.role,
                "profile_email_masked": self.sender_identity.profile_email_masked,
                "allowlist_match": self.sender_identity.allowlist_match,
                "read_scope_verified": self.sender_identity.read_scope_verified,
                "issues": self.sender_identity.issues,
            },
            "recipient_identity": {
                "role": self.recipient_identity.role,
                "profile_email_masked": self.recipient_identity.profile_email_masked,
                "allowlist_match": self.recipient_identity.allowlist_match,
                "read_scope_verified": self.recipient_identity.read_scope_verified,
                "issues": self.recipient_identity.issues,
            },
        }


def _mask_header_email(header: str) -> str:
    email = _parse_from_email(header)
    return mask_email(email) if email else "not_observed"


def _message_forensics(
    detail: dict[str, Any],
    *,
    evaluation_run_id: str,
    scenario_id: str,
) -> MessageForensics:
    subject = str(detail.get("subject") or "")
    body = str(detail.get("body_text") or "")
    parsed = parse_subject_token(subject)
    labels = [str(label) for label in (detail.get("label_ids") or [])]
    return MessageForensics(
        message_id=str(detail.get("message_id") or ""),
        thread_id=str(detail.get("thread_id") or ""),
        labels=labels,
        from_masked=_mask_header_email(str(detail.get("from") or "")),
        to_masked=_mask_header_email(str(detail.get("to") or "")),
        reply_to_masked=_mask_header_email(str(detail.get("reply_to") or "")),
        subject_truncated=subject[:120],
        rfc_message_id=_normalize_rfc_message_id(
            str(detail.get("internet_message_id") or "") or None
        ),
        in_reply_to=_normalize_rfc_message_id(
            str(detail.get("in_reply_to") or "") or None
        ),
        references_truncated=(str(detail.get("references") or "") or None),
        in_sent="SENT" in labels,
        correlation_match=(
            parsed is not None
            and parsed.evaluation_run_id == evaluation_run_id
            and parsed.scenario_id == scenario_id
        ),
        body_has_run_id=evaluation_run_id in body,
        body_has_scenario_id=scenario_id in body,
    )


def _verify_mailbox_identity(
    *,
    role: str,
    build_client,
    expected_email: str,
) -> MailboxIdentityReport:
    issues: list[str] = []
    profile_email: str | None = None
    read_scope_verified = False
    try:
        client = build_client()
        profile_email = client.get_profile_email()
        client.list_messages_page(max_results=1, query="in:anywhere")
        read_scope_verified = True
    except LiveEvalSafetyError as exc:
        issues.append(str(exc))
    except Exception as exc:
        issues.append(f"{role}_read_scope_failed: {type(exc).__name__}")

    expected = expected_email.strip().lower()
    profile = (profile_email or "").strip().lower()
    allowlist_match = profile == expected if profile else False
    if profile and not allowlist_match:
        issues.append(f"{role}_oauth_mailbox_mismatch")

    return MailboxIdentityReport(
        role=role,
        profile_email=profile_email,
        profile_email_masked=mask_email(profile_email or "") or "not_observed",
        expected_allowlist_role=role,
        allowlist_match=allowlist_match,
        read_scope_verified=read_scope_verified,
        issues=issues,
    )


def _search_messages(
    client,
    query: str,
    *,
    evaluation_run_id: str,
    scenario_id: str,
) -> list[MessageForensics]:
    try:
        ids = client.list_message_ids(max_results=_MAX_SEARCH_RESULTS, query=query)
    except Exception:
        return []
    matches: list[MessageForensics] = []
    for message_id in ids:
        try:
            detail = client.get_message(message_id)
        except Exception:
            continue
        matches.append(
            _message_forensics(
                detail,
                evaluation_run_id=evaluation_run_id,
                scenario_id=scenario_id,
            )
        )
    return matches


def _placement_from_labels(labels: list[str]) -> str:
    label_set = set(labels)
    if "SPAM" in label_set:
        return "recipient_verified_in_spam"
    if "TRASH" in label_set:
        return "recipient_verified_in_trash"
    if "INBOX" in label_set:
        return "recipient_verified_in_inbox"
    return "recipient_verified_in_all_mail"


def _classify_root_cause(report: LiveGmailForensicsReport) -> None:
    subcodes: list[str] = []
    adapter_masked = report.adapter_recipient_masked
    if report.credential_role_collision:
        subcodes.append("credential_role_collision")
    if not report.sender_identity.allowlist_match:
        subcodes.append("sender_oauth_mailbox_mismatch")
    if not report.recipient_identity.allowlist_match:
        subcodes.append("recipient_oauth_mailbox_mismatch")

    if report.credential_role_collision or (
        not report.sender_identity.allowlist_match
        or not report.recipient_identity.allowlist_match
    ):
        report.root_cause_classification = "H2"
    elif report.provider_sent_status == "provider_message_id_missing":
        report.root_cause_classification = "H5"
        subcodes.append("provider_metadata_not_persisted")
    elif report.provider_sent_status == "sender_read_scope_missing":
        report.root_cause_classification = "blocked"
        subcodes.append("sender_read_scope_missing")
    elif report.provider_sent_status == "provider_sent_object_verified":
        provider = report.provider_object
        if provider and adapter_masked and provider.to_masked != adapter_masked:
            report.root_cause_classification = "H1"
            subcodes.append("provider_to_mismatch")
        elif report.recipient_verification_status.startswith("recipient_verified"):
            report.root_cause_classification = "H3"
            subcodes.append("correct_recipient_verification_query_failed")
        else:
            report.root_cause_classification = "H4"
            subcodes.append("provider_sent_recipient_not_delivered")
    elif report.recipient_verification_status.startswith("recipient_verified"):
        report.root_cause_classification = "H3"
        subcodes.append("correct_recipient_verification_query_failed")
    else:
        report.root_cause_classification = "H3"
        subcodes.append("correct_recipient_verification_query_failed")

    report.root_cause_subcodes = subcodes


def run_live_gmail_forensics(
    *,
    evaluation_run_id: str,
    scenario_id: str,
    job_id: str | None = None,
    campaign_run_id: str | None = None,
    source_workflow_run: str | None = None,
    provider_message_id: str | None = None,
    inbound_rfc_message_id: str | None = None,
    adapter_recipient: str | None = None,
    runtime_sha: str | None = None,
) -> LiveGmailForensicsReport:
    assert_readonly_forensics_budget()
    install_readonly_gmail_guard()

    config = get_live_eval_config()
    senders = sorted(config.sender_emails)
    recipients = sorted(config.recipient_emails)
    if len(senders) != 1 or len(recipients) != 1:
        raise LiveEvalSafetyError("exactly one allowlisted sender and recipient required")

    expected_sender = senders[0]
    expected_recipient = recipients[0]
    token = f"{SUBJECT_TOKEN_PREFIX}/{evaluation_run_id}"

    sender_identity = _verify_mailbox_identity(
        role="testbot_sender",
        build_client=build_sender_client,
        expected_email=expected_sender,
    )
    recipient_identity = _verify_mailbox_identity(
        role="app_recipient_mailbox",
        build_client=build_recipient_client,
        expected_email=expected_recipient,
    )
    collision = (
        sender_identity.profile_email is not None
        and recipient_identity.profile_email is not None
        and sender_identity.profile_email.strip().lower()
        == recipient_identity.profile_email.strip().lower()
    )

    sender_client = build_sender_client()
    recipient_client = build_recipient_client()

    inbound_matches = _search_messages(
        recipient_client,
        f'in:anywhere subject:"{token}"',
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario_id,
    )
    inbound_message = next((m for m in inbound_matches if m.correlation_match), None)

    provider_object: MessageForensics | None = None
    provider_status = "provider_message_id_missing"
    resolved_provider_id = (provider_message_id or "").strip()

    if not resolved_provider_id:
        sent_matches = _search_messages(
            recipient_client,
            f'in:sent to:{expected_sender} subject:"{token}"',
            evaluation_run_id=evaluation_run_id,
            scenario_id=scenario_id,
        )
        for candidate in sent_matches:
            if candidate.correlation_match or candidate.in_sent:
                resolved_provider_id = candidate.message_id
                provider_object = candidate
                break

    if resolved_provider_id:
        try:
            detail = recipient_client.get_message(resolved_provider_id)
            provider_object = _message_forensics(
                detail,
                evaluation_run_id=evaluation_run_id,
                scenario_id=scenario_id,
            )
            if provider_object.in_sent and expected_sender in _sent_recipient_emails(detail):
                provider_status = "provider_sent_object_verified"
            elif provider_object.in_sent:
                provider_status = "provider_to_mismatch"
            else:
                provider_status = "provider_object_not_in_sent"
        except LiveEvalSafetyError:
            provider_status = "sender_read_scope_missing"
        except Exception:
            provider_status = "provider_object_not_found"

    recipient_searches: list[RecipientSearchResult] = []
    recipient_status = "provider_sent_recipient_not_found"
    provider_rfc = provider_object.rfc_message_id if provider_object else None
    inbound_rfc = inbound_rfc_message_id or (
        inbound_message.rfc_message_id if inbound_message else None
    )

    search_plan: list[tuple[str, str]] = []
    provider_query = _rfc822msgid_query(provider_rfc)
    if provider_query:
        search_plan.append((f"in:anywhere {provider_query}", "rfc_provider_message_id"))
    inbound_query = _rfc822msgid_query(inbound_rfc)
    if inbound_query:
        search_plan.append((f"in:anywhere {inbound_query}", "rfc_in_reply_to"))
    if campaign_run_id:
        search_plan.append((f'in:anywhere "{campaign_run_id}"', "campaign_run_id"))
    search_plan.append((f'in:anywhere "{evaluation_run_id}"', "scenario_execution_id"))
    search_plan.append(
        (
            f"in:anywhere from:{expected_recipient} to:{expected_sender}",
            "exact_from_to",
        )
    )

    for query, _label in search_plan:
        matches = _search_messages(
            sender_client,
            query,
            evaluation_run_id=evaluation_run_id,
            scenario_id=scenario_id,
        )
        exact = [m for m in matches if m.correlation_match or m.in_reply_to == inbound_rfc]
        if not exact and matches and _label == "rfc_provider_message_id":
            exact = matches
        placement = None
        selected = exact[0] if exact else None
        if selected:
            placement = _placement_from_labels(selected.labels)
            recipient_status = placement
        recipient_searches.append(
            RecipientSearchResult(
                query=query,
                match_count=len(exact) or len(matches),
                placement=placement,
                message=selected,
            )
        )
        if selected and placement:
            break

    adapter_masked = mask_email(adapter_recipient or "") if adapter_recipient else None
    report = LiveGmailForensicsReport(
        source_workflow_run=source_workflow_run,
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario_id,
        job_id=job_id,
        campaign_run_id=campaign_run_id,
        runtime_sha=runtime_sha,
        sender_identity=sender_identity,
        recipient_identity=recipient_identity,
        credential_role_collision=collision,
        inbound_message=inbound_message,
        provider_message_id=resolved_provider_id or None,
        provider_object=provider_object,
        provider_sent_status=provider_status,
        adapter_recipient_masked=adapter_masked,
        recipient_searches=recipient_searches,
        recipient_verification_status=recipient_status,
        root_cause_classification="pending",
        root_cause_subcodes=[],
    )
    _classify_root_cause(report)
    return report
