"""
Regression tests: Swedish characters (ä, å, ö) must survive the full
integration execute path without corruption.

Covers:
  - Request payload with Swedish chars is passed verbatim to the adapter
  - IntegrationEvent.payload stores Swedish chars correctly
  - API response (IntegrationEventResponse) preserves Swedish chars
  - JSON serialisation of the response preserves Swedish chars (no ? substitution)

The bug context: after a live Gmail send, the response JSON showed
  'är' → '?r', 'från' → 'fr?n'
Root cause: Windows terminal (GBK code page) was mis-rendering valid UTF-8
bytes as '?', not a data corruption in the platform. These tests verify the
platform side is correct end-to-end.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.domain.integrations.models import IntegrationEvent
from app.domain.integrations.response_schemas import IntegrationEventResponse
from app.integrations.schemas import IntegrationActionRequest

# ── shared Swedish test strings ──────────────────────────────────────────────

SWEDISH_BODY = "Detta är ett meddelande från avsändaren. Hälsningar från oss."
SWEDISH_SUBJECT = "Ärende: Offert för Björkvägen 5"
SWEDISH_MESSAGE = "Skickat. Tack för ditt ärende."

SWEDISH_CHARS = ["ä", "å", "ö", "Ä", "Å", "Ö"]


def _assert_preserved(value: str, expected: str, label: str) -> None:
    """Assert that 'value' equals 'expected' — no char substitution anywhere."""
    assert value == expected, (
        f"{label}: Swedish characters corrupted.\n"
        f"  expected: {expected!r}\n"
        f"  got:      {value!r}"
    )


def _assert_contains_swedish(text: str, label: str) -> None:
    """Assert that text contains at least one Swedish character."""
    assert any(ch in text for ch in SWEDISH_CHARS), (
        f"{label}: no Swedish characters found — got {text!r}"
    )


# ── 1. Request payload schema preserves Swedish chars ────────────────────────

class TestRequestPayloadEncoding:
    def test_action_request_preserves_swedish_body(self):
        req = IntegrationActionRequest(
            action="send_email",
            payload={"to": "x@x.com", "subject": SWEDISH_SUBJECT, "body": SWEDISH_BODY},
        )
        _assert_preserved(req.payload["body"], SWEDISH_BODY, "req.payload['body']")
        _assert_preserved(req.payload["subject"], SWEDISH_SUBJECT, "req.payload['subject']")

    def test_action_request_json_roundtrip_preserves_swedish(self):
        req = IntegrationActionRequest(
            action="send_email",
            payload={"to": "x@x.com", "subject": SWEDISH_SUBJECT, "body": SWEDISH_BODY},
        )
        serialised = req.model_dump_json()
        restored = IntegrationActionRequest.model_validate_json(serialised)
        _assert_preserved(restored.payload["body"], SWEDISH_BODY, "json roundtrip body")
        _assert_preserved(restored.payload["subject"], SWEDISH_SUBJECT, "json roundtrip subject")


# ── 2. Adapter receives Swedish chars unchanged ───────────────────────────────

class TestAdapterReceivesSwedishChars:
    def test_execute_action_called_with_swedish_payload(self):
        from app.main import execute_integration_action
        from app.integrations.enums import IntegrationType

        swedish_payload = {
            "to": "recipient@example.com",
            "subject": SWEDISH_SUBJECT,
            "body": SWEDISH_BODY,
        }

        mock_adapter = MagicMock()
        mock_adapter.execute_action.return_value = {
            "status": "success",
            "provider": "google_mail",
            "message": SWEDISH_MESSAGE,
            "external_id": "msg-001",
            "payload": {},
        }

        saved_event = _make_event(swedish_payload)

        with patch("app.main.is_integration_enabled_for_tenant", return_value=True), \
             patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter", return_value=mock_adapter), \
             patch("app.repositories.postgres.integration_repository.IntegrationRepository.create", return_value=saved_event), \
             patch("app.domain.integrations.response_schemas.IntegrationEventResponse.model_validate", return_value=MagicMock()):
            execute_integration_action(
                integration_type=IntegrationType.GOOGLE_MAIL,
                request=IntegrationActionRequest(action="send_email", payload=swedish_payload),
                db=MagicMock(),
                tenant_id="TENANT_TEST",
            )

        called_payload = mock_adapter.execute_action.call_args.kwargs["payload"]
        _assert_preserved(called_payload["body"], SWEDISH_BODY, "adapter call body")
        _assert_preserved(called_payload["subject"], SWEDISH_SUBJECT, "adapter call subject")


# ── 3. IntegrationEvent.payload preserves Swedish chars ──────────────────────

class TestIntegrationEventPayloadEncoding:
    def test_payload_field_preserves_swedish_body(self):
        ev = _make_event({"body": SWEDISH_BODY, "subject": SWEDISH_SUBJECT})
        _assert_preserved(ev.payload["request"]["body"], SWEDISH_BODY, "ev.payload request body")

    def test_payload_field_preserves_swedish_subject(self):
        ev = _make_event({"body": SWEDISH_BODY, "subject": SWEDISH_SUBJECT})
        _assert_preserved(ev.payload["request"]["subject"], SWEDISH_SUBJECT, "ev.payload request subject")

    def test_result_field_in_payload_preserves_swedish_message(self):
        ev = _make_event({"body": SWEDISH_BODY})
        _assert_preserved(ev.payload["result"]["message"], SWEDISH_MESSAGE, "ev.payload result message")


# ── 4. Response schema preserves Swedish chars ───────────────────────────────

class TestResponseSchemaEncoding:
    def test_model_validate_preserves_swedish_body(self):
        ev = _make_event({"body": SWEDISH_BODY, "subject": SWEDISH_SUBJECT})
        response = IntegrationEventResponse.model_validate(ev)
        _assert_preserved(response.payload["request"]["body"], SWEDISH_BODY, "response body")

    def test_model_validate_preserves_swedish_subject(self):
        ev = _make_event({"body": SWEDISH_BODY, "subject": SWEDISH_SUBJECT})
        response = IntegrationEventResponse.model_validate(ev)
        _assert_preserved(response.payload["request"]["subject"], SWEDISH_SUBJECT, "response subject")

    def test_model_dump_json_no_question_mark_substitution(self):
        ev = _make_event({"body": SWEDISH_BODY, "subject": SWEDISH_SUBJECT})
        response = IntegrationEventResponse.model_validate(ev)
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)
        _assert_preserved(parsed["payload"]["request"]["body"], SWEDISH_BODY, "parsed json body")
        _assert_preserved(parsed["payload"]["request"]["subject"], SWEDISH_SUBJECT, "parsed json subject")

    def test_starlette_json_response_bytes_are_valid_utf8(self):
        """The bytes FastAPI sends to the client must be valid UTF-8 and contain Swedish chars."""
        from starlette.responses import JSONResponse

        ev = _make_event({"body": SWEDISH_BODY})
        response = IntegrationEventResponse.model_validate(ev)
        data = response.model_dump()
        data["created_at"] = data["created_at"].isoformat() if data.get("created_at") else None
        data["updated_at"] = None

        rendered = JSONResponse(content=data)
        body_bytes = rendered.body

        # Must decode cleanly as UTF-8
        decoded = body_bytes.decode("utf-8")
        _assert_contains_swedish(decoded, "starlette response body")

        # Round-trip must be lossless
        reparsed = json.loads(body_bytes)
        _assert_preserved(reparsed["payload"]["request"]["body"], SWEDISH_BODY, "reparsed starlette body")

    def test_json_dumps_ensure_ascii_false_preserves_swedish(self):
        """The serialization path Starlette uses (ensure_ascii=False) preserves chars literally."""
        data = {"payload": {"request": {"body": SWEDISH_BODY, "subject": SWEDISH_SUBJECT}}}
        rendered = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        assert SWEDISH_BODY in rendered
        assert SWEDISH_SUBJECT in rendered

    def test_json_dumps_ensure_ascii_true_roundtrip_is_clean(self):
        """With ensure_ascii=True the chars are escaped but the round-trip is still lossless."""
        data = {"body": SWEDISH_BODY}
        rendered = json.dumps(data, ensure_ascii=True)
        restored = json.loads(rendered)
        assert restored["body"] == SWEDISH_BODY


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_event(request_payload: dict) -> IntegrationEvent:
    ev = IntegrationEvent(
        tenant_id="TENANT_TEST",
        job_id="direct",
        integration_type="google_mail",
        payload={
            "action": "send_email",
            "request": request_payload,
            "result": {"message": SWEDISH_MESSAGE},
        },
        status="success",
        attempts=1,
        idempotency_key="swedish-test-key",
    )
    ev.id = 1
    ev.created_at = datetime.now(timezone.utc)
    ev.updated_at = None
    return ev
