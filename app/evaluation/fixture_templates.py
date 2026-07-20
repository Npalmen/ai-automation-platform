"""Shared AI fixture blocks for evaluation scenarios (copied into normative YAML)."""

LEAD_FIXTURES = {
    "classification_v1": {
        "detected_job_type": "lead",
        "confidence": 0.9,
        "reasons": ["keyword_match"],
    },
    "entity_extraction_v1": {
        "entities": {
            "customer_name": "Anna Lindqvist",
            "email": "anna@example.com",
        },
        "confidence": 0.85,
    },
    "lead_scoring_v1": {
        "lead_score": 70,
        "priority": "medium",
        "routing": "crm_update",
        "reasons": [],
        "confidence": 0.85,
    },
    "decisioning_v1": {
        "decision": "auto_route",
        "target_queue": "sales_queue",
        "action_flags": {
            "create_crm_lead": False,
            "notify_human": False,
            "request_missing_data": True,
        },
        "reasons": [],
        "confidence": 0.85,
    },
}

INQUIRY_FIXTURES = {
    "classification_v1": {
        "detected_job_type": "customer_inquiry",
        "confidence": 0.9,
        "reasons": ["support"],
    },
    "entity_extraction_v1": {
        "entities": {
            "customer_name": "Sara Nilsson",
            "email": "sara@example.com",
        },
        "confidence": 0.85,
    },
    "customer_inquiry_analysis_v1": {
        "inquiry_type": "support",
        "priority": "high",
        "routing": "support_queue",
        "reasons": [],
        "confidence": 0.85,
    },
    "decisioning_v1": {
        "decision": "manual_review",
        "target_queue": "manual_review",
        "action_flags": {
            "create_crm_lead": False,
            "notify_human": True,
            "request_missing_data": False,
        },
        "reasons": ["safety"],
        "confidence": 0.85,
    },
}

INVOICE_FIXTURES = {
    "classification_v1": {
        "detected_job_type": "invoice",
        "confidence": 0.9,
        "reasons": ["invoice_keyword"],
    },
    "entity_extraction_v1": {
        "entities": {
            "invoice_number": "INV-1001",
            "amount": 12500.0,
            "currency": "SEK",
        },
        "confidence": 0.85,
    },
    "invoice_analysis_v1": {
        "invoice_data": {
            "supplier_name": "Leverantör AB",
            "invoice_number": "INV-1001",
            "amount_inc_vat": 12500.0,
            "currency": "SEK",
        },
        "validation_status": "validated",
        "duplicate_suspected": False,
        "missing_critical": [],
        "approval_route": "approval_required",
        "reasons": [],
        "confidence": 0.9,
    },
}
