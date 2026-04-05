from app.domain.workflows.models import Job


def get_extracted_entities(job: Job) -> dict:
    for item in reversed(job.processor_history):
        if item.get("processor") == "entity_extraction_processor":
            result = item.get("result") or {}
            payload = result.get("payload") or {}
            return payload.get("extracted_entities") or {}
    return {}


def process_customer_inquiry_job(job: Job) -> Job:
    payload = job.input_data or {}
    sender = payload.get("sender") or {}

    extracted = get_extracted_entities(job)

    subject = extracted.get("subject") or (payload.get("subject") or "").strip()
    message_text = extracted.get("message_text") or (payload.get("message_text") or "").strip()

    customer_name = extracted.get("customer_name") or (sender.get("name") or "").strip()
    email = extracted.get("email") or (sender.get("email") or "").strip().lower()
    phone = extracted.get("phone") or (sender.get("phone") or "").strip()

    combined = f"{subject} {message_text}".lower()

    inquiry_type = "general"
    if any(word in combined for word in ["pris", "offert", "quote", "price"]):
        inquiry_type = "sales"
    elif any(word in combined for word in ["support", "fel", "problem", "hjälp"]):
        inquiry_type = "support"
    elif any(word in combined for word in ["faktura", "invoice", "betalning", "payment"]):
        inquiry_type = "billing"

    priority = "low"
    if inquiry_type in {"support", "billing"}:
        priority = "medium"

    requires_human_review = False
    reasons = []

    if not subject and not message_text:
        requires_human_review = True
        reasons.append("missing_message_content")

    routing = "case_queue"
    if inquiry_type == "support":
        routing = "support_queue"
    elif inquiry_type == "billing":
        routing = "billing_queue"
    elif inquiry_type == "sales":
        routing = "sales_queue"

    result = {
        "status": "completed",
        "summary": "Kundförfrågan analyserad.",
        "requires_human_review": requires_human_review,
        "payload": {
            "processor_name": "customer_inquiry_processor",
            "inquiry_data": {
                "customer_name": customer_name,
                "email": email,
                "phone": phone,
                "subject": subject,
                "message_text": message_text,
            },
            "inquiry_type": inquiry_type,
            "priority": priority,
            "routing": routing,
            "reasons": reasons,
            "recommended_next_step": (
                "manual_review" if requires_human_review else routing
            ),
        },
    }

    job.processor_history.append({
        "processor": "customer_inquiry_processor",
        "result": result,
    })
    job.result = result
    return job