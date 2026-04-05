from app.ai.exceptions import LLMResponseError
from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.processors.classification_processor import process_classification_job
from app.workflows.processors.customer_inquiry_processor import process_customer_inquiry_job
from app.workflows.processors.decisioning_processor import process_decisioning_job
from app.workflows.processors.entity_extraction_processor import process_entity_extraction_job
from app.workflows.processors.invoice_processor import process_invoice_job
from app.workflows.processors.lead_processor import process_lead_job


class StubLLMClient:
    def __init__(self, response):
        self.response = response

    def generate_json(self, prompt: str):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _build_lead_job() -> Job:
    return Job(
        tenant_id="TENANT_1001",
        job_type=JobType.LEAD,
        input_data={
            "subject": "Vill ha offert på laddbox och elcentral",
            "message_text": "Hej, vi vill ha pris på ny elcentral och laddbox. Ring gärna 0701234567.",
            "sender": {
                "name": "Niklas Palm",
                "email": "niklas@example.com",
            },
            "attachments": [],
        },
        status="pending",
    )


def _build_inquiry_job() -> Job:
    return Job(
        tenant_id="TENANT_1001",
        job_type=JobType.CUSTOMER_INQUIRY,
        input_data={
            "subject": "Problem med laddbox",
            "message_text": "Hej, vår laddbox fungerar inte och visar felkod. Kan ni hjälpa oss snabbt?",
            "sender": {
                "name": "Niklas Palm",
                "email": "niklas@example.com",
            },
            "attachments": [],
        },
        status="pending",
    )


def _build_invoice_job() -> Job:
    return Job(
        tenant_id="TENANT_1001",
        job_type=JobType.INVOICE,
        input_data={
            "subject": "Faktura 2026-104",
            "message_text": (
                "Leverantör: EL Grossisten AB. "
                "Fakturanummer: 2026-104. "
                "Förfallodatum: 2026-05-05. "
                "Belopp inkl moms: 12500 SEK."
            ),
            "sender": {
                "name": "Ekonomi",
                "email": "faktura@example.com",
            },
            "attachments": [],
        },
        status="pending",
    )


def test_classification_processor_success(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(
            {
                "detected_job_type": "lead",
                "confidence": 0.9,
                "reasons": ["request_for_price"],
            }
        ),
    )

    job = _build_lead_job()
    result = process_classification_job(job)

    payload = result.result["payload"]
    assert payload["detected_job_type"] == "lead"
    assert payload["confidence"] == 0.9
    assert result.result["requires_human_review"] is False


def test_classification_processor_fallback(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(LLMResponseError("bad response")),
    )

    job = _build_lead_job()
    result = process_classification_job(job)

    payload = result.result["payload"]
    assert payload["detected_job_type"] == "unknown"
    assert payload["confidence"] == 0.0
    assert result.result["requires_human_review"] is True
    assert "error" in payload


def test_classification_processor_marks_manual_review_on_low_confidence(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(
            {
                "detected_job_type": "lead",
                "confidence": 0.4,
                "reasons": ["weak_signal"],
            }
        ),
    )

    job = _build_lead_job()
    result = process_classification_job(job)

    assert result.result["requires_human_review"] is True
    assert result.result["payload"]["detected_job_type"] == "lead"


def test_entity_extraction_processor_success(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(
            {
                "entities": {
                    "customer_name": "Niklas Palm",
                    "company_name": None,
                    "email": "niklas@example.com",
                    "phone": "0701234567",
                    "organization_number": None,
                    "invoice_number": None,
                    "amount": None,
                    "currency": None,
                    "due_date": None,
                    "requested_service": "offert på laddbox och elcentral",
                    "address": None,
                    "city": None,
                    "notes": None,
                },
                "confidence": 0.9,
            }
        ),
    )

    job = _build_lead_job()
    job.processor_history.append(
        {
            "processor": "classification_processor",
            "result": {
                "payload": {
                    "detected_job_type": "lead",
                    "confidence": 0.9,
                    "reasons": ["request_for_price"],
                }
            },
        }
    )

    result = process_entity_extraction_job(job)

    payload = result.result["payload"]
    assert payload["entities"]["customer_name"] == "Niklas Palm"
    assert payload["entities"]["phone"] == "0701234567"
    assert result.result["requires_human_review"] is False


def test_entity_validation_marks_manual_review(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(
            {
                "entities": {
                    "customer_name": None,
                    "company_name": None,
                    "email": "not-an-email",
                    "phone": "12",
                    "organization_number": None,
                    "invoice_number": None,
                    "amount": None,
                    "currency": None,
                    "due_date": None,
                    "requested_service": None,
                    "address": None,
                    "city": None,
                    "notes": None,
                },
                "confidence": 0.9,
            }
        ),
    )

    job = _build_lead_job()
    job.processor_history.append(
        {
            "processor": "classification_processor",
            "result": {
                "payload": {
                    "detected_job_type": "lead",
                    "confidence": 0.9,
                    "reasons": ["request_for_price"],
                }
            },
        }
    )

    result = process_entity_extraction_job(job)
    payload = result.result["payload"]

    assert result.result["requires_human_review"] is True
    assert payload["validation"]["is_valid"] is False
    assert "invalid_email" in payload["validation"]["issues"]


def test_lead_processor_success(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(
            {
                "lead_score": 80,
                "priority": "high",
                "routing": "priority_sales_followup",
                "reasons": ["request_for_price", "contact_phone_provided"],
                "confidence": 0.9,
            }
        ),
    )

    job = _build_lead_job()
    job.processor_history.extend(
        [
            {
                "processor": "classification_processor",
                "result": {
                    "payload": {
                        "detected_job_type": "lead",
                        "confidence": 0.9,
                        "reasons": ["request_for_price"],
                    }
                },
            },
            {
                "processor": "entity_extraction_processor",
                "result": {
                    "payload": {
                        "entities": {
                            "customer_name": "Niklas Palm",
                            "company_name": None,
                            "email": "niklas@example.com",
                            "phone": "0701234567",
                            "organization_number": None,
                            "invoice_number": None,
                            "amount": None,
                            "currency": None,
                            "due_date": None,
                            "requested_service": "offert på laddbox och elcentral",
                            "address": None,
                            "city": None,
                            "notes": None,
                        },
                        "confidence": 0.9,
                    }
                },
            },
        ]
    )

    result = process_lead_job(job)

    payload = result.result["payload"]
    assert payload["lead_score"] == 80
    assert payload["priority"] == "high"
    assert payload["routing"] == "priority_sales_followup"
    assert result.result["requires_human_review"] is False


def test_decisioning_processor_fallback(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(LLMResponseError("decision failure")),
    )

    job = _build_lead_job()
    job.processor_history.extend(
        [
            {
                "processor": "classification_processor",
                "result": {
                    "payload": {
                        "detected_job_type": "lead",
                        "confidence": 0.9,
                        "reasons": ["request_for_price"],
                    }
                },
            },
            {
                "processor": "entity_extraction_processor",
                "result": {
                    "payload": {
                        "entities": {
                            "customer_name": "Niklas Palm",
                            "company_name": None,
                            "email": "niklas@example.com",
                            "phone": "0701234567",
                            "organization_number": None,
                            "invoice_number": None,
                            "amount": None,
                            "currency": None,
                            "due_date": None,
                            "requested_service": "offert på laddbox och elcentral",
                            "address": None,
                            "city": None,
                            "notes": None,
                        },
                        "confidence": 0.9,
                    }
                },
            },
            {
                "processor": "lead_processor",
                "result": {
                    "payload": {
                        "lead_score": 80,
                        "priority": "high",
                        "routing": "priority_sales_followup",
                        "reasons": ["request_for_price"],
                        "confidence": 0.9,
                    }
                },
            },
        ]
    )

    result = process_decisioning_job(job)

    payload = result.result["payload"]
    assert payload["decision"] == "manual_review"
    assert payload["target_queue"] == "manual_review"
    assert payload["action_flags"]["notify_human"] is True
    assert result.result["requires_human_review"] is True


def test_customer_inquiry_processor_success(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(
            {
                "inquiry_type": "support",
                "priority": "medium",
                "routing": "support_queue",
                "reasons": ["technical_issue", "clear_problem_description"],
                "confidence": 0.9,
            }
        ),
    )

    job = _build_inquiry_job()
    job.processor_history.extend(
        [
            {
                "processor": "classification_processor",
                "result": {
                    "payload": {
                        "detected_job_type": "customer_inquiry",
                        "confidence": 0.9,
                        "reasons": ["support_request"],
                    }
                },
            },
            {
                "processor": "entity_extraction_processor",
                "result": {
                    "payload": {
                        "entities": {
                            "customer_name": "Niklas Palm",
                            "company_name": None,
                            "email": "niklas@example.com",
                            "phone": None,
                            "organization_number": None,
                            "invoice_number": None,
                            "amount": None,
                            "currency": None,
                            "due_date": None,
                            "requested_service": "hjälp med laddbox",
                            "address": None,
                            "city": None,
                            "notes": None,
                        },
                        "confidence": 0.9,
                    }
                },
            },
        ]
    )

    result = process_customer_inquiry_job(job)
    payload = result.result["payload"]

    assert payload["inquiry_type"] == "support"
    assert payload["priority"] == "medium"
    assert payload["routing"] == "support_queue"
    assert result.result["requires_human_review"] is False


def test_customer_inquiry_processor_fallback(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(LLMResponseError("bad inquiry response")),
    )

    job = Job(
        tenant_id="TENANT_1001",
        job_type=JobType.CUSTOMER_INQUIRY,
        input_data={
            "subject": "Fråga",
            "message_text": "Hej",
            "sender": {
                "name": "Niklas Palm",
                "email": "niklas@example.com",
            },
            "attachments": [],
        },
        status="pending",
    )

    result = process_customer_inquiry_job(job)
    payload = result.result["payload"]

    assert payload["routing"] == "manual_review"
    assert payload["confidence"] == 0.0
    assert result.result["requires_human_review"] is True


def test_invoice_processor_success(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(
            {
                "invoice_data": {
                    "supplier_name": "EL Grossisten AB",
                    "organization_number": None,
                    "invoice_number": "2026-104",
                    "invoice_date": None,
                    "due_date": "2026-05-05",
                    "currency": "SEK",
                    "amount_ex_vat": None,
                    "vat_amount": None,
                    "amount_inc_vat": 12500.0,
                    "reference": None,
                },
                "validation_status": "validated",
                "duplicate_suspected": False,
                "missing_critical": [],
                "approval_route": "approval_required",
                "reasons": ["invoice_number_present", "amount_present", "supplier_present"],
                "confidence": 0.9,
            }
        ),
    )

    job = _build_invoice_job()
    job.processor_history.extend(
        [
            {
                "processor": "classification_processor",
                "result": {
                    "payload": {
                        "detected_job_type": "invoice",
                        "confidence": 0.9,
                        "reasons": ["invoice_detected"],
                    }
                },
            },
            {
                "processor": "entity_extraction_processor",
                "result": {
                    "payload": {
                        "entities": {
                            "customer_name": None,
                            "company_name": "EL Grossisten AB",
                            "email": "faktura@example.com",
                            "phone": None,
                            "organization_number": None,
                            "invoice_number": "2026-104",
                            "amount": 12500.0,
                            "currency": "SEK",
                            "due_date": "2026-05-05",
                            "requested_service": None,
                            "address": None,
                            "city": None,
                            "notes": None,
                        },
                        "confidence": 0.9,
                    }
                },
            },
        ]
    )

    result = process_invoice_job(job)
    payload = result.result["payload"]

    assert payload["invoice_data"]["supplier_name"] == "EL Grossisten AB"
    assert payload["invoice_data"]["invoice_number"] == "2026-104"
    assert payload["validation_status"] == "validated"
    assert payload["approval_route"] == "approval_required"
    assert result.result["requires_human_review"] is False


def test_invoice_processor_fallback(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(LLMResponseError("bad invoice response")),
    )

    job = _build_invoice_job()
    result = process_invoice_job(job)
    payload = result.result["payload"]

    assert payload["validation_status"] == "manual_review"
    assert payload["approval_route"] == "manual_review"
    assert result.result["requires_human_review"] is True


def test_invoice_validation_marks_manual_review(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(
            {
                "invoice_data": {
                    "supplier_name": None,
                    "organization_number": None,
                    "invoice_number": None,
                    "invoice_date": None,
                    "due_date": None,
                    "currency": "SEK",
                    "amount_ex_vat": None,
                    "vat_amount": None,
                    "amount_inc_vat": -100.0,
                    "reference": None,
                },
                "validation_status": "validated",
                "duplicate_suspected": False,
                "missing_critical": [],
                "approval_route": "auto_approve",
                "reasons": ["bad_ai_output"],
                "confidence": 0.9,
            }
        ),
    )

    job = _build_invoice_job()
    result = process_invoice_job(job)
    payload = result.result["payload"]

    assert result.result["requires_human_review"] is True
    assert payload["validation"]["is_valid"] is False
    assert payload["approval_route"] == "manual_review"
    assert payload["validation_status"] == "manual_review"


def test_invoice_duplicate_detection(monkeypatch):
    from app.workflows.processors import ai_processor_utils as utils

    llm_response = {
        "invoice_data": {
            "supplier_name": "EL Grossisten AB",
            "organization_number": None,
            "invoice_number": "2026-104",
            "invoice_date": None,
            "due_date": "2026-05-05",
            "currency": "SEK",
            "amount_ex_vat": None,
            "vat_amount": None,
            "amount_inc_vat": 12500.0,
            "reference": None,
        },
        "validation_status": "validated",
        "duplicate_suspected": False,
        "missing_critical": [],
        "approval_route": "auto_approve",
        "reasons": [],
        "confidence": 0.9,
    }

    previous_history_payload = {
        "processor_name": "invoice_processor",
        "invoice_data": {
            "supplier_name": "EL Grossisten AB",
            "organization_number": None,
            "invoice_number": "2026-104",
            "invoice_date": None,
            "due_date": "2026-05-05",
            "currency": "SEK",
            "amount_ex_vat": None,
            "vat_amount": None,
            "amount_inc_vat": 12500.0,
            "reference": None,
        },
        "validation_status": "validated",
        "duplicate_suspected": False,
        "missing_critical": [],
        "approval_route": "auto_approve",
        "reasons": [],
        "confidence": 0.9,
    }

    monkeypatch.setattr(
        utils,
        "get_llm_client",
        lambda: StubLLMClient(llm_response),
    )

    job = _build_invoice_job()

    job.processor_history.append(
        {
            "processor": "invoice_processor",
            "result": {
                "payload": previous_history_payload
            },
        }
    )

    result = process_invoice_job(job)
    payload = result.result["payload"]

    assert payload["duplicate_suspected"] is True
    assert payload["approval_route"] == "manual_review"
    assert result.result["requires_human_review"] is True



    result = process_invoice_job(job)
    payload = result.result["payload"]

    assert payload["duplicate_suspected"] is True
    assert payload["approval_route"] == "manual_review"
    assert result.result["requires_human_review"] is True