"""Thread, duplicate and replay context contract (Todo G)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.workflows.message_partition import (
    is_forwarded_subject,
    normalize_rfc_message_id,
    partition_message_text,
)

CONTRACT_VERSION = "thread_replay_context_v1"


@dataclass(frozen=True)
class ThreadReplayContext:
    gmail_message_id: str
    internet_message_id: str
    gmail_thread_id: str
    tenant_id: str
    mailbox_id: str | None = None
    reply_to: str | None = None
    alias_recipient: str | None = None
    is_duplicate_gmail_id: bool = False
    is_duplicate_rfc_message_id: bool = False
    is_thread_continuation: bool = False
    is_forwarded: bool = False
    quoted_history: str = ""
    current_message_text: str = ""
    current_subject: str = ""
    transport_metadata: dict[str, Any] = field(default_factory=dict)
    dedupe_keys: tuple[str, ...] = ()
    contract_version: str = CONTRACT_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "gmail_message_id": self.gmail_message_id,
            "internet_message_id": self.internet_message_id,
            "gmail_thread_id": self.gmail_thread_id,
            "tenant_id": self.tenant_id,
            "mailbox_id": self.mailbox_id,
            "reply_to": self.reply_to,
            "alias_recipient": self.alias_recipient,
            "is_duplicate_gmail_id": self.is_duplicate_gmail_id,
            "is_duplicate_rfc_message_id": self.is_duplicate_rfc_message_id,
            "is_thread_continuation": self.is_thread_continuation,
            "is_forwarded": self.is_forwarded,
            "quoted_history": self.quoted_history,
            "current_message_text": self.current_message_text,
            "current_subject": self.current_subject,
            "transport_metadata": dict(self.transport_metadata),
            "dedupe_keys": list(self.dedupe_keys),
            "contract_version": self.contract_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ThreadReplayContext | None:
        if not data:
            return None
        return cls(
            gmail_message_id=str(data.get("gmail_message_id") or ""),
            internet_message_id=str(data.get("internet_message_id") or ""),
            gmail_thread_id=str(data.get("gmail_thread_id") or ""),
            tenant_id=str(data.get("tenant_id") or ""),
            mailbox_id=data.get("mailbox_id"),
            reply_to=data.get("reply_to"),
            alias_recipient=data.get("alias_recipient"),
            is_duplicate_gmail_id=bool(data.get("is_duplicate_gmail_id")),
            is_duplicate_rfc_message_id=bool(data.get("is_duplicate_rfc_message_id")),
            is_thread_continuation=bool(data.get("is_thread_continuation")),
            is_forwarded=bool(data.get("is_forwarded")),
            quoted_history=str(data.get("quoted_history") or ""),
            current_message_text=str(data.get("current_message_text") or ""),
            current_subject=str(data.get("current_subject") or ""),
            transport_metadata=dict(data.get("transport_metadata") or {}),
            dedupe_keys=tuple(data.get("dedupe_keys") or ()),
            contract_version=str(data.get("contract_version") or CONTRACT_VERSION),
        )


def build_thread_replay_context(
    *,
    tenant_id: str,
    gmail_message_id: str,
    gmail_thread_id: str = "",
    internet_message_id: str = "",
    subject: str = "",
    body_text: str = "",
    mailbox_id: str | None = None,
    reply_to: str | None = None,
    alias_recipient: str | None = None,
    is_duplicate_gmail_id: bool = False,
    is_duplicate_rfc_message_id: bool = False,
    is_thread_continuation: bool = False,
    transport_metadata: dict[str, Any] | None = None,
) -> ThreadReplayContext:
    current, quoted = partition_message_text(body_text)
    normalized_rfc = normalize_rfc_message_id(internet_message_id)
    dedupe_keys: list[str] = []
    if gmail_message_id:
        dedupe_keys.append(f"gmail:{tenant_id}:{gmail_message_id}")
    if normalized_rfc:
        dedupe_keys.append(f"rfc:{tenant_id}:{normalized_rfc}")

    return ThreadReplayContext(
        gmail_message_id=gmail_message_id,
        internet_message_id=normalized_rfc,
        gmail_thread_id=gmail_thread_id,
        tenant_id=tenant_id,
        mailbox_id=mailbox_id,
        reply_to=reply_to,
        alias_recipient=alias_recipient,
        is_duplicate_gmail_id=is_duplicate_gmail_id,
        is_duplicate_rfc_message_id=is_duplicate_rfc_message_id,
        is_thread_continuation=is_thread_continuation,
        is_forwarded=is_forwarded_subject(subject),
        quoted_history=quoted,
        current_message_text=current,
        current_subject=subject,
        transport_metadata=dict(transport_metadata or {}),
        dedupe_keys=tuple(dedupe_keys),
    )
