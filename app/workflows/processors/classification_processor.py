from app.ai.schemas import ClassificationResponse
from app.domain.workflows.models import Job
from app.workflows.business_intent import build_business_intent_from_classification
from app.workflows.intelligence_safety import assess_content_risk
from app.workflows.processors.ai_processor_utils import get_latest_processor_payload, run_ai_step
from app.workflows.threat_assessment import ThreatAssessment


PROCESSOR_NAME = "classification_processor"
PROMPT_NAME = "classification"

# Priority order (highest -> lowest):
# spam > wrong_recipient/unclear > newsletter > internal > invoice > supplier
# > partnership > support/customer_inquiry > lead > customer_inquiry.
# The deterministic path returns "unknown" for empty/unclear/wrong-recipient
# content so the system does not confidently automate ambiguous input.

_SPAM_KEYWORDS = {
    "you won", "click here to claim", "lottery", "nigerian prince",
    "free money", "make money fast", "enlarge", "casino bonus",
    "phishing", "wire transfer urgent", "verify your account immediately",
    "spam", "säljutskick", "seo erbjudande", "köp länkar", "billiga länkar",
    "massmail", "cold outreach", "leadlista",
}

_WRONG_RECIPIENT_KEYWORDS = {
    "fel person", "fel bolag", "fel företag", "inte avsett för er",
    "wrong person", "wrong company", "wrong recipient",
}

_NEWSLETTER_KEYWORDS = {
    "nyhetsbrev", "newsletter", "unsubscribe", "avregistrera",
    "monthly update", "campaign", "product update", "webinar invite",
    "event invite", "promotional", "our latest offers", "denna veckas erbjudanden",
    "denna månads kampanjer", "kampanjer", "prenumerera",
}

_INTERNAL_KEYWORDS = {
    "intern notering", "internt", "internal note", "team update",
    "staff notice", "internal memo", "admin notice", "system notification",
}

_INVOICE_KEYWORDS = {"faktura", "invoice", "payment request", "billing document"}

_SUPPLIER_KEYWORDS = {
    "orderbekräftelse", "order confirmation", "leveransbekräftelse",
    "delivery confirmation", "shipment notification", "din beställning",
    "your order", "purchase confirmation", "order status", "material order",
    "kvitto för", "purchase receipt", "payment receipt", "order receipt",
}

_PARTNERSHIP_KEYWORDS = {
    "samarbete", "partnership", "collaboration", "affiliate",
    "business proposal", "b2b", "subcontractor", "partner opportunity",
    "samarbetsförslag", "vi vill diskutera", "potentiellt samarbete",
    "joint venture", "strategic alliance",
}

_LEAD_KEYWORDS = {
    "offert", "pris", "köpa", "intresserad", "installera", "installation av",
    "boka installation", "montering", "besiktning", "kostnadsförslag",
    "förfrågan", "vill ha",
    "quote", "pricing", "buy", "purchase", "interested",
    "demo", "trial", "inspection", "repair",
}

_SUPPORT_KEYWORDS = {
    "fungerar inte", "producerar inget", "trasig", "felkod", "larm",
    "driftstopp", "helt nere", "problem med", "support",
    "boka om", "omboka", "flytta min bokade tid", "avboka",
    "reklamation", "missnöjd", "häva avtalet", "avtalsfråga",
    "inkasso", "betalningskrav", "garanti", "klagomål",
    "mitt ärende", "hur går det", "status på",
}


def _classify_deterministic(subject: str, body: str) -> str:
    """Return a classification type based on keyword priority order.

    Priority: spam > newsletter > internal > invoice > supplier > partnership > lead > customer_inquiry
    Never returns 'unknown' — that is reserved for the LLM.
    """
    return classify_email_type(subject, body)


def classify_email_type(subject: str, body: str) -> str:
    """Public deterministic classifier for inbox taxonomy v2.

    Reusable by any intake path (inbox, webhook, manual POST).
    Priority order: spam > newsletter > internal > invoice > supplier > partnership > lead > customer_inquiry
    """
    combined = f"{subject} {body}".lower()
    if not combined.strip():
        return "unknown"

    if any(kw in combined for kw in _SPAM_KEYWORDS):
        return "spam"
    if any(kw in combined for kw in _WRONG_RECIPIENT_KEYWORDS):
        return "unknown"
    if any(kw in combined for kw in _NEWSLETTER_KEYWORDS):
        return "newsletter"
    if any(kw in combined for kw in _INTERNAL_KEYWORDS):
        return "internal"
    if any(kw in combined for kw in _INVOICE_KEYWORDS):
        return "invoice"
    if any(kw in combined for kw in _SUPPLIER_KEYWORDS):
        return "supplier"
    if any(kw in combined for kw in _PARTNERSHIP_KEYWORDS):
        return "partnership"
    if any(kw in combined for kw in _SUPPORT_KEYWORDS):
        return "customer_inquiry"
    if any(kw in combined for kw in _LEAD_KEYWORDS):
        return "lead"
    return "customer_inquiry"


def _build_source_context(job: Job) -> dict:
    input_data = job.input_data or {}
    sender = input_data.get("sender") or {}
    attachments = input_data.get("attachments") or []

    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "input_data": {
            "subject": input_data.get("subject"),
            "message_text": input_data.get("message_text"),
            "sender": {
                "name": sender.get("name"),
                "email": sender.get("email"),
                "phone": sender.get("phone"),
            },
            "attachments": attachments,
        },
    }


def _threat_from_intake(job: Job) -> ThreatAssessment | None:
    intake_payload = get_latest_processor_payload(job, "universal_intake_processor")
    threat_data = intake_payload.get("threat_assessment")
    return ThreatAssessment.from_dict(threat_data)


def _apply_threat_override(
    payload: dict,
    threat: ThreatAssessment | None,
) -> dict:
    """Enforce deterministic threat blockers on classification output."""
    if threat is None or not threat.hard_blockers:
        return payload

    if threat.threat_class in (
        "phishing",
        "prompt_injection",
        "spam",
        "credential_request",
        "payment_detail_change",
    ):
        payload = dict(payload)
        payload["detected_job_type"] = "spam" if threat.threat_class == "spam" else "unknown"
        payload["confidence"] = max(float(payload.get("confidence") or 0), threat.confidence)
        reasons = list(payload.get("reasons") or [])
        reasons.extend(["threat_blocked", threat.threat_class])
        payload["reasons"] = reasons
        payload["recommended_next_step"] = threat.required_routing
        payload["threat_override"] = True

    return payload


def _apply_deterministic_classification_guard(
    payload: dict,
    *,
    subject: str,
    body: str,
) -> dict:
    """Prefer deterministic taxonomy when LLM over-routes obvious support/status mail to lead."""
    deterministic = classify_email_type(subject, body)
    llm_type = str(payload.get("detected_job_type") or "")
    if llm_type == "lead" and deterministic == "customer_inquiry":
        guarded = dict(payload)
        guarded["detected_job_type"] = deterministic
        reasons = list(guarded.get("reasons") or [])
        reasons.append("deterministic_guard_customer_inquiry")
        guarded["reasons"] = reasons
        guarded["confidence"] = min(float(guarded.get("confidence") or 0.5), 0.55)
        guarded["recommended_next_step"] = deterministic
        return guarded
    return payload


def process_classification_job(job: Job, trace=None) -> Job:
    context = _build_source_context(job)

    input_data = job.input_data or {}
    threat = _threat_from_intake(job)
    subject = str(input_data.get("subject") or "")
    body = str(input_data.get("message_text") or "")

    def _guard(payload: dict) -> dict:
        return _apply_deterministic_classification_guard(
            _apply_threat_override(payload, threat),
            subject=subject,
            body=body,
        )

    def _deterministic_fallback(error_message: str) -> dict:
        detected = _classify_deterministic(subject=subject, body=body)
        risk = assess_content_risk(input_data)
        reasons = ["deterministic_fallback", "llm_unavailable"] + risk["reasons"]
        confidence = 0.35 if detected == "unknown" or risk["risk_detected"] else 0.5
        return {
            "detected_job_type": detected,
            "confidence": confidence,
            "reasons": reasons,
            "error": error_message,
            "recommended_next_step": "manual_review" if risk["risk_detected"] else detected,
            "risk": risk,
        }

    job = run_ai_step(
        job=job,
        processor_name=PROCESSOR_NAME,
        prompt_name="classification_v1",
        context=context,
        response_model=ClassificationResponse,
        success_summary="Ärendet klassificerat med AI.",
        success_payload_builder=lambda parsed: _guard(
            {
                "detected_job_type": parsed.detected_job_type,
                "confidence": parsed.confidence,
                "reasons": parsed.reasons,
                "recommended_next_step": parsed.detected_job_type,
            }
        ),
        fallback_payload_builder=lambda err: _guard(_deterministic_fallback(err)),
    )

    # Post-process: threat override on LLM success path too.
    from app.workflows.processors.ai_processor_utils import get_latest_processor_payload as _glp

    latest = _glp(job, PROCESSOR_NAME) or {}
    if threat and threat.hard_blockers:
        overridden = _guard(latest)
        if overridden != latest:
            job.processor_history[-1]["result"]["payload"] = overridden
            latest = overridden

    business_intent = build_business_intent_from_classification(
        detected_job_type=str(latest.get("detected_job_type") or "unknown"),
        confidence=float(latest.get("confidence") or 0),
        reasons=list(latest.get("reasons") or []),
        threat_blocks_business=bool(threat and threat.hard_blockers),
        subject=subject,
        body=body,
    )
    job.processor_history[-1]["result"]["payload"]["business_intent"] = business_intent.to_dict()
    if threat:
        job.processor_history[-1]["result"]["payload"]["threat_assessment"] = threat.to_dict()

    if trace is not None and trace.db is not None:
        from app.workflows.decision_record import DecisionRecordType
        from app.workflows.decision_record_service import record_processor_decision
        from app.workflows.processors.ai_processor_utils import get_latest_processor_payload

        payload = get_latest_processor_payload(job, PROCESSOR_NAME)
        record_processor_decision(
            trace.db,
            trace,
            job,
            record_type=DecisionRecordType.CLASSIFICATION,
            processor_name=PROCESSOR_NAME,
            payload=payload,
        )
    return job