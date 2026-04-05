from app.domain.workflows.models import Job


HIGH_VALUE_THRESHOLD = 80


def get_extracted_entities(job: Job) -> dict:
    for item in reversed(job.processor_history):
        if item.get("processor") == "entity_extraction_processor":
            result = item.get("result") or {}
            payload = result.get("payload") or {}
            return payload.get("extracted_entities") or {}
    return {}


def process_lead_job(job: Job) -> Job:
    payload = job.input_data or {}
    sender = payload.get("sender") or {}

    extracted = get_extracted_entities(job)

    subject = extracted.get("subject") or (payload.get("subject") or "").strip()
    message_text = extracted.get("message_text") or (payload.get("message_text") or "").strip()

    customer_name = extracted.get("customer_name") or (sender.get("name") or "").strip()
    email = extracted.get("email") or (sender.get("email") or "").strip().lower()
    phone = extracted.get("phone") or (sender.get("phone") or "").strip()

    combined = f"{subject} {message_text}".lower()

    lead_signals = []
    if any(word in combined for word in ["offert", "quote"]):
        lead_signals.append("quote_request")
    if any(word in combined for word in ["pris", "price"]):
        lead_signals.append("price_request")
    if any(word in combined for word in ["boka", "book"]):
        lead_signals.append("booking_intent")
    if any(word in combined for word in ["ring", "call"]):
        lead_signals.append("callback_request")

    lead_score = 0
    if customer_name:
        lead_score += 20
    if email:
        lead_score += 30
    if phone:
        lead_score += 30
    lead_score += min(len(lead_signals) * 10, 20)

    priority = "low"
    if lead_score >= 80:
        priority = "high"
    elif lead_score >= 50:
        priority = "medium"

    is_high_value = lead_score >= HIGH_VALUE_THRESHOLD

    requires_human_review = False
    reasons = []

    if not any([customer_name, email, phone]):
        requires_human_review = True
        reasons.append("missing_contact_details")

    routing = "crm_update"
    if is_high_value:
        routing = "priority_sales_followup"

    result = {
        "status": "completed",
        "summary": "Lead analyserad.",
        "requires_human_review": requires_human_review,
        "payload": {
            "processor_name": "lead_processor",
            "lead_data": {
                "customer_name": customer_name,
                "email": email,
                "phone": phone,
                "subject": subject,
                "message_text": message_text,
            },
            "lead_signals": lead_signals,
            "lead_score": min(lead_score, 100),
            "priority": priority,
            "is_high_value": is_high_value,
            "routing": routing,
            "qualification": (
                "sales_followup" if priority in {"high", "medium"} else "needs_triage"
            ),
            "reasons": reasons,
            "recommended_next_step": (
                "manual_review" if requires_human_review else routing
            ),
        },
    }

    job.processor_history.append({
        "processor": "lead_processor",
        "result": result,
    })
    job.result = result
    return job