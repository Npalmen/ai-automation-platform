import json
import re
import time
from typing import Any

from pydantic import BaseModel, ValidationError

from app.ai.exceptions import LLMClientError
from app.ai.llm.client import get_llm_client
from app.ai.prompts.registry import render_prompt
from app.domain.workflows.models import Job


# ── shared extraction helpers ─────────────────────────────────────────────────

# Matches Swedish and international phone numbers; requires ≥7 digits.
_PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(\+46|0046)?"
    r"[\s\-]?"
    r"(0\d{1,3}|\d{2,3})"
    r"[\s\-]?"
    r"\d{2,4}"
    r"(?:[\s\-]?\d{2,4}){1,3}"
    r"(?!\d)",
)


def extract_phone(subject: str, body_text: str) -> str | None:
    """Return the first plausible phone number in subject or body, or None."""
    for text in (subject, body_text):
        m = _PHONE_RE.search(text or "")
        if m:
            raw = m.group(0).strip()
            return re.sub(r"[\s\-]+", "-", raw)
    return None


_INQUIRY_HIGH_KEYWORDS = {"akut", "snabbt", "problem"}


def classify_inquiry_priority(subject: str, message_text: str) -> str:
    """Return 'HIGH' or 'NORMAL' for a customer inquiry.

    Checks subject and message_text case-insensitively against a small set
    of urgency keywords. Returns 'HIGH' on any match, 'NORMAL' otherwise.
    """
    combined = f"{subject} {message_text}".lower()
    if any(kw in combined for kw in _INQUIRY_HIGH_KEYWORDS):
        return "HIGH"
    return "NORMAL"


# ── invoice extraction helpers ────────────────────────────────────────────────

# Amount: "12 500 kr", "12500 kr", "1 250,50 kr", "SEK 12500".
# The kr-suffix branch comes first; the SEK-prefix branch is the fallback.
_AMOUNT_RE = re.compile(
    r"(\d{1,3}(?:[\s]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*kr\b"
    r"|"
    r"\bSEK\s*(\d+(?:[.,]\d{1,2})?)",
    re.IGNORECASE,
)

# Invoice number: keyword marker then a reference of ≥2 chars starting with
# an alphanumeric and optionally followed by alphanumerics, hyphens, or slashes.
# Requires either explicit punctuation (#/:/-) or the reference starts with
# a digit, to avoid matching stray words after "fakturanummer".
_INVOICE_NO_RE = re.compile(
    r"(?:faktura(?:nummer)?|invoice(?:\s*no\.?)?|inv)"
    r"(?:"
    r"\s*[:#-]\s*([A-Za-z0-9][A-Za-z0-9_/\-]{1,19})"   # explicit punctuation path
    r"|"
    r"\s+(\d[A-Za-z0-9_/\-]{0,19})"                      # space + starts with digit
    r")",
    re.IGNORECASE,
)

# Due date: ISO-style YYYY-MM-DD, YYYY/MM/DD, or YYYY.MM.DD.
_DUE_DATE_RE = re.compile(r"\b(20\d{2}[-/.]\d{2}[-/.]\d{2})\b")


def extract_invoice_amount(subject: str, body_text: str) -> str | None:
    """Return the first plausible amount string from subject or body, or None."""
    for text in (subject, body_text):
        m = _AMOUNT_RE.search(text or "")
        if m:
            raw = m.group(0).strip()
            return re.sub(r"\s+", " ", raw)
    return None


def extract_invoice_number(subject: str, body_text: str) -> str | None:
    """Return the first plausible invoice reference from subject or body, or None."""
    for text in (subject, body_text):
        m = _INVOICE_NO_RE.search(text or "")
        if m:
            # group(1) = punctuation path, group(2) = digit-start path
            return (m.group(1) or m.group(2)).strip()
    return None


def extract_due_date(subject: str, body_text: str) -> str | None:
    """Return the first ISO-style due date (YYYY-MM-DD etc.) found, or None.

    Normalises separators to '-' so the returned string is always YYYY-MM-DD.
    """
    for text in (subject, body_text):
        m = _DUE_DATE_RE.search(text or "")
        if m:
            raw = m.group(1)
            return re.sub(r"[/.]", "-", raw)
    return None


# ── Swedish address / location extraction ─────────────────────────────────────

# Street suffix patterns common in Swedish addresses.
_STREET_SUFFIXES = (
    r"vägen|gatan|gränd|torget|allén|leden|stigen|backen|parken"
    r"|bron|torg|plan|plats|esplanaden|promenaden|boulevarden"
    r"|gata|väg|stig|backe"
)

# Match "Solvägen 12", "Norra Strandvägen 3A", "Industrivägen 5B" etc.
# Number part: digit(s) immediately followed by an optional single letter —
# no space allowed between number and letter, preventing "4 i" from matching.
_STREET_ADDRESS_RE = re.compile(
    rf"([A-ZÅÄÖ][a-zåäöA-ZÅÄÖ]{{1,20}}"
    rf"(?:\s+[A-ZÅÄÖ][a-zåäö]{{1,20}})?)"  # optional prefix word
    rf"(?:{_STREET_SUFFIXES})"
    rf"\s+(\d{{1,4}}[A-Za-z]?)",
    re.UNICODE,
)

# Swedish postal code — always written "NNN NN" (with a space).
_POSTAL_CODE_RE = re.compile(r"\b(\d{3}\s\d{2})\b")

# City name following the postal code.
_CITY_AFTER_POSTAL_RE = re.compile(
    r"\b\d{3}\s\d{2}\s+([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-ZÅÄÖ][a-zåäö]+)?)\b",
    re.UNICODE,
)

# City name after "i", "till", "från", "vid", "nära", "utanför".
_CITY_PREP_RE = re.compile(
    r"\b(?:i|till|från|vid|nära|utanför)\s+([A-ZÅÄÖ][a-zåäö]{2,}(?:\s+[A-ZÅÄÖ][a-zåäö]+)?)\b",
    re.UNICODE,
)

# Property designation: keyword + "Kommun Trakt 12:3" or inline "Namn Trakt 12:3".
_PROP_DESIGNATION_RE = re.compile(
    r"(?:fastighetsbeteckning|beteckning)\s+([A-ZÅÄÖ][a-zåäö]+(?:\s+[A-Za-zåäöÅÄÖ]+)*\s+\d+:\d+)",
    re.IGNORECASE | re.UNICODE,
)

# Property-type keyword → canonical type label.
_PROPERTY_TYPE_DETECT: list[tuple[str, list[str]]] = [
    ("lantbruk", ["gård", "lantbruk", "jordbruk", "lantgård", "bondgård"]),
    ("brf", ["brf", "bostadsrättsförening", "bostadsrätt"]),
    ("villa", ["villa", "villafastighet", "enfamiljshus", "radhus"]),
    ("lägenhet", ["lägenhet", " lgh "]),
    ("lokal", ["lokal", "kontor", "kontorslokal", "industrilokal", "butikslokal"]),
]


def extract_swedish_location(text: str) -> dict:
    """Return a dict with address components found in *text*.

    Keys (only present when found):
        street_address      e.g. "Solvägen 12"
        postal_code         e.g. "753 20"
        city                e.g. "Uppsala"
        property_type       e.g. "villa" | "brf" | "lantbruk" | "lägenhet" | "lokal"
        property_designation e.g. "Uppsala Nåntuna 12:3"
    """
    result: dict[str, str] = {}

    # Street address
    m = _STREET_ADDRESS_RE.search(text)
    if m:
        full = m.group(0).strip().rstrip("., ")
        result["street_address"] = full

    # Postal code
    m_pc = _POSTAL_CODE_RE.search(text)
    if m_pc:
        result["postal_code"] = m_pc.group(1)

    # City — prefer city after postal code, fall back to preposition marker
    m_city = _CITY_AFTER_POSTAL_RE.search(text)
    if m_city:
        result["city"] = m_city.group(1)
    else:
        m_prep = _CITY_PREP_RE.search(text)
        if m_prep:
            result["city"] = m_prep.group(1)

    # Property designation
    m_pd = _PROP_DESIGNATION_RE.search(text)
    if m_pd:
        result["property_designation"] = m_pd.group(1).strip()

    # Property type — first match wins (lantbruk before villa to avoid false villa)
    lower = text.lower()
    for ptype, keywords in _PROPERTY_TYPE_DETECT:
        if any(kw in lower for kw in keywords):
            result["property_type"] = ptype
            break

    return result


# ── Swedish organisation number ───────────────────────────────────────────────

# Format: 6 digits, hyphen or en-dash, 4 digits.  e.g. "556123-4567".
_ORG_NO_RE = re.compile(r"\b(\d{6}[-\u2013]\d{4})\b")


def extract_org_number(subject: str, body_text: str) -> str | None:
    """Return the first Swedish organisation number found, or None."""
    for text in (subject, body_text):
        m = _ORG_NO_RE.search(text or "")
        if m:
            return m.group(1)
    return None


# ── OCR / payment reference ───────────────────────────────────────────────────

# OCR number on Swedish bank giro / plus giro — various label styles.
# Two branches:
#   (1) Full label keyword before number (e.g. "OCR-nummer: 1234567890").
#   (2) Standalone "OCR" with any mix of delimiters, e.g. "(OCR): 1234 5678 90".
_OCR_RE = re.compile(
    r"\b(?:ocr[-\s]?nummer|ocr[-\s]?ref\.?|betalningsref(?:erens)?)\s*[:\-]?\s*(\d[\d\s]{4,25}\d)"
    r"|\bocr\b[)\-:\s]*(\d[\d\s]{4,25}\d)",
    re.IGNORECASE,
)


def extract_ocr_number(subject: str, body_text: str) -> str | None:
    """Return the first OCR / payment reference number found, or None."""
    for text in (subject, body_text):
        m = _OCR_RE.search(text or "")
        if m:
            raw = m.group(1) or m.group(2) or ""
            return re.sub(r"\s+", "", raw) or None
    return None


# ── Invoice risk level ────────────────────────────────────────────────────────

_HIGH_RISK_INVOICE_KW = [
    "inkasso", "betalningskrav", "kravbrev", "kronofogden",
    "förfallen skuld", "skuldsaldo", "betalningsanmärkning",
]
_MEDIUM_RISK_INVOICE_KW = [
    "betalningspåminnelse", "påminnelse om betalning",
    "påminnelseavgift", "förfallodatum passerat", "obetald faktura",
]


def detect_invoice_risk_level(subject: str, body_text: str) -> str:
    """Return "high_risk", "medium_risk", or "normal" for an invoice message.

    "high_risk"   — debt collection, bailiff, legal enforcement in progress.
    "medium_risk" — payment reminder, overdue notice.
    "normal"      — standard invoice or receipt.
    """
    combined = f"{subject} {body_text}".lower()
    if any(kw in combined for kw in _HIGH_RISK_INVOICE_KW):
        return "high_risk"
    if any(kw in combined for kw in _MEDIUM_RISK_INVOICE_KW):
        return "medium_risk"
    return "normal"


def extract_invoice_data(input_data: dict[str, Any]) -> dict[str, Any]:
    """Return a structured invoice payload extracted deterministically from input_data.

    Fields returned (omitted when not found):
        supplier_name, amount, invoice_number, due_date, raw_text
    """
    sender = normalize_sender(input_data)
    supplier_name = sender.get("name") or sender.get("email") or ""

    subject = input_data.get("subject") or ""
    message_text = input_data.get("message_text") or ""
    raw_text = f"{subject}\n{message_text}".strip()

    payload: dict[str, Any] = {}
    if supplier_name:
        payload["supplier_name"] = supplier_name

    amount = extract_invoice_amount(subject, message_text)
    if amount:
        payload["amount"] = amount

    invoice_number = extract_invoice_number(subject, message_text)
    if invoice_number:
        payload["invoice_number"] = invoice_number

    due_date = extract_due_date(subject, message_text)
    if due_date:
        payload["due_date"] = due_date

    if raw_text:
        payload["raw_text"] = raw_text

    return payload


def normalize_sender(input_data: dict[str, Any]) -> dict[str, str]:
    """Return a clean sender dict from nested or flat input_data fields.

    Reads nested ``input_data["sender"]`` first; falls back to flat
    ``sender_name`` / ``sender_email`` / ``sender_phone`` keys.
    All values are stripped strings; missing fields are omitted.
    """
    nested = input_data.get("sender") or {}
    name = (nested.get("name") or input_data.get("sender_name") or "").strip()
    email = (nested.get("email") or input_data.get("sender_email") or "").strip().lower()
    phone = (nested.get("phone") or input_data.get("sender_phone") or "").strip()
    sender: dict[str, str] = {}
    if name:
        sender["name"] = name
    if email:
        sender["email"] = email
    if phone:
        sender["phone"] = phone
    return sender


def evaluate_information_completeness(
    job_type: str,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic completeness check for lead, customer_inquiry, and invoice.

    Returns:
        is_complete: bool
        missing_fields: list[str]  — machine-readable field names
        follow_up_questions: list[str]  — Swedish customer-facing sentences
        recommended_status: "ready_for_action" | "needs_customer_info" | "needs_internal_review"
    """
    sender = normalize_sender(input_data)
    sender_email = sender.get("email", "")
    sender_phone = sender.get("phone", "")
    message_text = (input_data.get("message_text") or "").strip()
    subject = (input_data.get("subject") or "").strip()

    missing: list[str] = []
    questions: list[str] = []

    if job_type == "lead":
        if not sender_email:
            missing.append("email")
            questions.append("Vilket e-postadress kan vi nå dig på?")

        has_details = len(message_text) >= 10 or (
            subject and subject.lower() not in {"(no subject)", "no subject", ""}
            and len(subject) >= 5
        )
        if not has_details:
            missing.append("request_details")
            questions.append("Vad vill du ha hjälp med? Beskriv gärna ditt ärende.")

        if not sender_phone:
            phone_in_text = extract_phone(subject, message_text)
            if not phone_in_text:
                missing.append("phone")
                questions.append("Vilket telefonnummer kan vi nå dig på?")

        is_complete = "email" not in missing and "request_details" not in missing
        status = "ready_for_action" if is_complete else "needs_customer_info"

    elif job_type == "customer_inquiry":
        if not sender_email:
            missing.append("email")
            questions.append("Vilket e-postadress kan vi nå dig på?")

        if len(message_text) < 15:
            missing.append("problem_description")
            questions.append("Beskriv gärna problemet lite mer.")
            questions.append("När uppstod problemet?")
            questions.append("Finns det någon bild, felkod eller produktmodell?")

        is_complete = "email" not in missing and "problem_description" not in missing
        status = "ready_for_action" if is_complete else "needs_customer_info"

    elif job_type == "invoice":
        invoice = extract_invoice_data(input_data)
        has_supplier = bool(invoice.get("supplier_name"))
        has_any_detail = any(
            invoice.get(f) for f in ("amount", "invoice_number", "due_date")
        )

        if not has_supplier:
            missing.append("supplier_name")
        if not has_any_detail:
            missing.append("invoice_details")

        is_complete = has_supplier and has_any_detail
        status = "ready_for_action" if is_complete else "needs_internal_review"
        questions = []  # no customer-facing questions for invoice

    else:
        is_complete = True
        status = "ready_for_action"

    return {
        "is_complete": is_complete,
        "missing_fields": missing,
        "follow_up_questions": questions,
        "recommended_status": status,
    }


def get_latest_processor_payload(job: Job, processor_name: str) -> dict[str, Any]:
    for item in reversed(job.processor_history):
        if item.get("processor") != processor_name:
            continue

        result = item.get("result") or {}
        payload = result.get("payload") or {}

        if isinstance(payload, dict):
            return payload

    return {}


def append_processor_result(
    job: Job,
    processor_name: str,
    result: dict[str, Any],
) -> Job:
    job.processor_history.append(
        {
            "processor": processor_name,
            "result": result,
        }
    )
    job.result = result
    return job


def apply_confidence_guardrail(payload: dict[str, Any], threshold: float = 0.6) -> dict[str, Any]:
    confidence = payload.get("confidence")

    if isinstance(confidence, (int, float)) and float(confidence) < threshold:
        payload["low_confidence"] = True
    else:
        payload["low_confidence"] = False

    return payload


def add_observability_fields(
    payload: dict[str, Any],
    *,
    processor_name: str,
    prompt_name: str,
    used_fallback: bool,
    duration_ms: int,
) -> dict[str, Any]:
    payload["processor_name"] = processor_name
    payload["prompt_name"] = prompt_name
    payload["used_fallback"] = used_fallback
    payload["duration_ms"] = duration_ms

    if "confidence" not in payload:
        payload["confidence"] = 0.0

    return payload


def run_ai_step(
    *,
    job: Job,
    processor_name: str,
    prompt_name: str,
    context: dict[str, Any],
    response_model: type[BaseModel],
    success_summary: str,
    success_payload_builder,
    fallback_payload_builder,
) -> Job:
    started = time.perf_counter()
    live_eval_raw = (job.input_data or {}).get("live_eval")
    use_live_eval_llm = isinstance(live_eval_raw, dict) and bool(live_eval_raw.get("trusted"))

    try:
        prompt = render_prompt(
            prompt_name,
            {
                "context_json": json.dumps(context, ensure_ascii=False, indent=2),
            },
        )

        if use_live_eval_llm:
            from app.evaluation.fixture_ai import reset_active_prompt_name, set_active_prompt_name
            from app.evaluation.live.llm_provider import resolve_llm_client

            llm_client = resolve_llm_client(job=job)
            prompt_token = set_active_prompt_name(prompt_name)
            try:
                raw_output = llm_client.generate_json(prompt)
            finally:
                reset_active_prompt_name(prompt_token)
        else:
            llm_client = get_llm_client()
            raw_output = llm_client.generate_json(prompt)
        parsed = response_model.model_validate(raw_output)

        duration_ms = int((time.perf_counter() - started) * 1000)

        payload = success_payload_builder(parsed)
        payload = add_observability_fields(
            payload,
            processor_name=processor_name,
            prompt_name=prompt_name,
            used_fallback=False,
            duration_ms=duration_ms,
        )
        payload = apply_confidence_guardrail(payload)

        result = {
            "status": "completed",
            "summary": success_summary,
            "requires_human_review": getattr(parsed, "confidence", 0.0) < 0.70,
            "payload": payload,
        }

        if payload.get("low_confidence"):
            result["requires_human_review"] = True
            payload["recommended_next_step"] = "manual_review"

        return append_processor_result(job, processor_name, result)

    except Exception as exc:
        if use_live_eval_llm:
            from app.evaluation.live.errors import LiveEvalSafetyError

            if isinstance(exc, LiveEvalSafetyError):
                duration_ms = int((time.perf_counter() - started) * 1000)
                payload = fallback_payload_builder(str(exc))
                payload = add_observability_fields(
                    payload,
                    processor_name=processor_name,
                    prompt_name=prompt_name,
                    used_fallback=False,
                    duration_ms=duration_ms,
                )
                result = {
                    "status": "completed",
                    "summary": f"{success_summary} Live-eval safety stop.",
                    "requires_human_review": True,
                    "payload": payload,
                }
                return append_processor_result(job, processor_name, result)

        if not isinstance(exc, (LLMClientError, ValidationError, ValueError, TypeError)):
            raise

        duration_ms = int((time.perf_counter() - started) * 1000)

        payload = fallback_payload_builder(str(exc))
        payload = add_observability_fields(
            payload,
            processor_name=processor_name,
            prompt_name=prompt_name,
            used_fallback=True,
            duration_ms=duration_ms,
        )

        result = {
            "status": "completed",
            "summary": f"{success_summary} Fallback till manuell granskning.",
            "requires_human_review": True,
            "payload": payload,
        }
        return append_processor_result(job, processor_name, result)