from app.ai.prompts.base import render_template


PROMPT_TEMPLATES: dict[str, str] = {
    "classification_v1": """
You are a strict classification engine.

Your task:
Classify the incoming message into exactly ONE of these job types:
- lead
- invoice
- customer_inquiry
- unknown

Rules:
- lead = customer wants price, offer, installation, or product
- invoice = contains invoice, supplier, payment, billing, due date, amount, or invoice number
- customer_inquiry = support, question, issue, complaint, follow-up, or general customer communication
- unknown = unclear or insufficient data
- Return STRICT JSON only
- Do not include markdown
- Do not include explanations outside JSON

Confidence rules:
- 0.90-1.00 = very clear intent
- 0.70-0.89 = likely intent
- 0.40-0.69 = weak signal
- 0.00-0.39 = unclear, usually use unknown

Output JSON ONLY:
{
  "detected_job_type": "lead" | "invoice" | "customer_inquiry" | "unknown",
  "confidence": number,
  "reasons": [string]
}

Workflow context:
{{ context_json }}
""".strip(),
    "entity_extraction_v1": """
You are a structured data extraction engine.

Your task:
- Read the workflow context
- Extract only explicitly stated data
- Do NOT guess
- Normalize email and phone if obvious
- requested_service should be a short summary of the user's stated need
- Unknown values must be null
- Return STRICT JSON only
- Do not include markdown
- Do not include explanations outside JSON

Confidence rules:
- 0.90-1.00 = clear structured data present
- 0.70-0.89 = mostly clear
- 0.40-0.69 = weak extraction
- 0.00-0.39 = unreliable extraction

Output JSON ONLY:
{
  "entities": {
    "customer_name": string | null,
    "company_name": string | null,
    "email": string | null,
    "phone": string | null,
    "organization_number": string | null,
    "invoice_number": string | null,
    "amount": number | null,
    "currency": string | null,
    "due_date": string | null,
    "requested_service": string | null,
    "address": string | null,
    "city": string | null,
    "notes": string | null
  },
  "confidence": number
}

Workflow context:
{{ context_json }}
""".strip(),
    "lead_scoring_v1": """
You are a lead scoring engine.

Your task:
- Read the workflow context
- Score the lead quality
- Use extracted entities when available
- Return STRICT JSON only
- Do not include markdown
- Do not include explanations outside JSON

Scoring guidance:
- High score if buying intent is clear
- High score if a specific product/service is mentioned
- High score if contact details are present
- Lower score if intent is vague
- Lower score if contact info is missing

Routing guidance:
- high quality lead -> priority_sales_followup
- medium quality lead -> crm_update
- weak lead -> manual_review

Confidence rules:
- 0.90-1.00 = very clear scoring basis
- 0.70-0.89 = likely correct scoring
- 0.40-0.69 = weak basis
- 0.00-0.39 = unreliable

Output JSON ONLY:
{
  "lead_score": integer,
  "priority": "low" | "medium" | "high",
  "routing": "crm_update" | "priority_sales_followup" | "manual_review",
  "reasons": [string],
  "confidence": number
}

Workflow context:
{{ context_json }}
""".strip(),
    "customer_inquiry_analysis_v1": """
You are a customer inquiry analysis engine.

Your task:
- Read the workflow context
- Classify the inquiry into one inquiry type
- Determine priority and routing
- Use extracted entities when available
- Return STRICT JSON only
- Do not include markdown
- Do not include explanations outside JSON

Guidance:
- support = technical problem, issue, fault, help request
- sales = pricing, quote, buying intent, service request
- billing = invoice, payment, charge, finance issue
- general = neutral question or non-urgent message

Priority guidance:
- support issues are usually at least medium
- billing issues are usually at least medium
- sales can be low, medium, or high depending on urgency and specificity
- pure information questions can be low
- if ambiguous, use manual_review

Confidence rules:
- 0.90-1.00 = very clear inquiry type
- 0.70-0.89 = likely correct
- 0.40-0.69 = weak basis
- 0.00-0.39 = unreliable

Output JSON ONLY:
{
  "inquiry_type": "support" | "sales" | "billing" | "general",
  "priority": "low" | "medium" | "high",
  "routing": "support_queue" | "sales_queue" | "billing_queue" | "case_queue" | "manual_review",
  "reasons": [string],
  "confidence": number
}

Workflow context:
{{ context_json }}
""".strip(),
    "invoice_analysis_v1": """
You are an invoice analysis engine.

Your task:
- Read the workflow context
- Extract invoice data
- Assess whether the invoice appears complete enough for downstream processing
- Return STRICT JSON only
- Do not include markdown
- Do not include explanations outside JSON
- Do not invent values

Validation guidance:
- if supplier_name is missing, do not treat it as fully validated
- if invoice_number is missing, do not treat it as fully validated
- if amount_inc_vat is missing, do not treat it as fully validated
- if due_date is missing, this is usually incomplete
- if uncertain, use manual_review

Confidence rules:
- 0.90-1.00 = clearly readable invoice data
- 0.70-0.89 = mostly clear
- 0.40-0.69 = weak basis
- 0.00-0.39 = unreliable

Output JSON ONLY:
{
  "invoice_data": {
    "supplier_name": string | null,
    "organization_number": string | null,
    "invoice_number": string | null,
    "invoice_date": string | null,
    "due_date": string | null,
    "currency": string | null,
    "amount_ex_vat": number | null,
    "vat_amount": number | null,
    "amount_inc_vat": number | null,
    "reference": string | null
  },
  "validation_status": "validated" | "incomplete" | "manual_review",
  "duplicate_suspected": boolean,
  "missing_critical": [string],
  "approval_route": "auto_approve" | "approval_required" | "manual_review",
  "reasons": [string],
  "confidence": number
}

Workflow context:
{{ context_json }}
""".strip(),
    "decisioning_v1": """
You are a workflow decisioning engine.

Your task:
- Read the workflow context
- Decide the next operational step
- Return STRICT JSON only
- Do not include markdown
- Do not include explanations outside JSON

Rules:
- high lead_score usually means auto_route
- missing critical data usually means manual_review
- low confidence usually means manual_review
- hold can be used when important information is missing but the case is not rejected

Confidence rules:
- 0.90-1.00 = very clear decision basis
- 0.70-0.89 = likely correct
- 0.40-0.69 = weak basis
- 0.00-0.39 = unreliable

Output JSON ONLY:
{
  "decision": "auto_route" | "manual_review" | "hold",
  "target_queue": string,
  "action_flags": {
    "create_crm_lead": boolean,
    "notify_human": boolean,
    "request_missing_data": boolean
  },
  "reasons": [string],
  "confidence": number
}

Workflow context:
{{ context_json }}
""".strip(),
}


def render_prompt(prompt_name: str, variables: dict[str, str]) -> str:
    template = PROMPT_TEMPLATES.get(prompt_name)

    if not template:
        raise ValueError(f"Unknown prompt template: {prompt_name}")

    return render_template(template, variables)