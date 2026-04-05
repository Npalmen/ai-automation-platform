from datetime import datetime, timezone

from app.domain.workflows.models import Job


PROCESSOR_NAME = "universal_intake_processor"


def process_universal_intake_job(job: Job) -> Job:
    input_data = job.input_data or {}
    sender = input_data.get("sender") or {}
    attachments = input_data.get("attachments") or []

    result = {
        "status": "completed",
        "summary": "Intake normaliserad.",
        "requires_human_review": False,
        "payload": {
            "processor_name": PROCESSOR_NAME,
            "status": "completed",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "source": {
                "system": input_data.get("source_system", "") or "",
                "channel": input_data.get("source_channel", "") or "",
            },
            "origin": {
                "sender_name": sender.get("name", "") or "",
                "sender_email": sender.get("email", "") or "",
                "sender_phone": sender.get("phone", "") or "",
            },
            "content": {
                "subject": input_data.get("subject", "") or "",
                "plain_text": input_data.get("message_text", "") or "",
                "attachment_count": len(attachments),
            },
            "attachments": attachments,
            "requires_human_review": False,
            "recommended_next_step": "classification",
        },
    }

    job.processor_history.append(
        {
            "processor": PROCESSOR_NAME,
            "result": result,
        }
    )
    job.result = result
    return job