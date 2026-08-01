"""Tests for thread replay context and message partition (Todo G)."""

from __future__ import annotations

from app.workflows.message_partition import (
    is_forwarded_subject,
    normalize_rfc_message_id,
    partition_message_text,
)
from app.workflows.thread_replay_context import build_thread_replay_context


class TestMessagePartition:
    def test_strips_quoted_history(self):
        body = "Hej, här är mitt svar.\n\nDen 1 aug 2026 skrev Support:\n> tidigare text"
        current, quoted = partition_message_text(body)
        assert "mitt svar" in current
        assert "tidigare text" in quoted
        assert "mitt svar" not in quoted

    def test_forwarded_subject_detected(self):
        assert is_forwarded_subject("Fwd: Viktigt meddelande")

    def test_rfc_message_id_normalized(self):
        assert normalize_rfc_message_id("abc@mail.test") == "<abc@mail.test>"


class TestThreadReplayContext:
    def test_builds_dedupe_keys(self):
        ctx = build_thread_replay_context(
            tenant_id="TENANT_LIVE_EVAL",
            gmail_message_id="gmail-123",
            gmail_thread_id="thread-abc",
            internet_message_id="<rfc@eval.test>",
            subject="Hej",
            body_text="Ny förfrågan",
        )
        assert any(k.startswith("gmail:") for k in ctx.dedupe_keys)
        assert any(k.startswith("rfc:") for k in ctx.dedupe_keys)

    def test_quoted_history_separated(self):
        body = "Ny text\n\nFrån: någon@example.com\n> gammal"
        ctx = build_thread_replay_context(
            tenant_id="TENANT_LIVE_EVAL",
            gmail_message_id="gmail-456",
            subject="Re: ärende",
            body_text=body,
        )
        assert ctx.current_message_text.startswith("Ny text")
        assert ctx.quoted_history

    def test_serialization_roundtrip(self):
        from app.workflows.thread_replay_context import ThreadReplayContext

        ctx = build_thread_replay_context(
            tenant_id="TENANT_LIVE_EVAL",
            gmail_message_id="gmail-789",
            internet_message_id="<id@eval.test>",
            subject="Test",
            body_text="Hej",
        )
        restored = ThreadReplayContext.from_dict(ctx.to_dict())
        assert restored is not None
        assert restored.gmail_message_id == "gmail-789"
