from datetime import datetime, timezone


class UniversalIntakeProcessor:
    def process(self, payload: dict) -> dict:
        subject = (payload.get("subject") or "").strip()
        message_text = (payload.get("message_text") or "").strip()
        source_system = (payload.get("source_system") or "").strip()
        source_channel = (payload.get("source_channel") or "").strip()

        attachments = payload.get("attachments") or []
        sender = payload.get("sender") or {}

        has_content = bool(subject or message_text or attachments)

        if not has_content:
            return {
                "status": "failed",
                "summary": "Payload saknar innehåll.",
                "requires_human_review": True,
                "payload": {},
            }

        normalized_payload = {
            "processor_name": "universal_intake_processor",
            "status": "completed",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "system": source_system,
                "channel": source_channel,
            },
            "origin": {
                "sender_name": (sender.get("name") or "").strip(),
                "sender_email": (sender.get("email") or "").strip().lower(),
                "sender_phone": (sender.get("phone") or "").strip(),
            },
            "content": {
                "subject": subject,
                "plain_text": message_text,
                "attachment_count": len(attachments),
            },
            "attachments": attachments,
            "requires_human_review": False,
            "recommended_next_step": "classification",
        }

        return {
            "status": "completed",
            "summary": "Intake normaliserad.",
            "requires_human_review": False,
            "payload": normalized_payload,
        }