"""Server-allowlisted fixture bundles for live eval fixture_ai mode."""

from __future__ import annotations

from typing import Any

from app.evaluation.live.errors import LiveEvalSafetyError

# scenario_id -> bundle_id (server resolved at registration; not client supplied)
SCENARIO_BUNDLE_MAP: dict[str, str] = {
    "S01_lead_laddbox_quality": "k2f_bundle_s01",
    "TBS01_lead_observe": "k2f_bundle_tbs01",
    "TBS02_support_observe": "k2f_bundle_tbs02",
    "TBS03_invoice_observe": "k2f_bundle_tbs03",
    "TBS04_unknown_observe": "k2f_bundle_tbs04",
    "TBS05_noisy_observe": "k2f_bundle_tbs05",
    "TBSM01_lead_approve_reply": "k2f_bundle_tbs01",
    "TBSM02_support_approve_reply": "k2f_bundle_tbs02",
    "TBSM03_noisy_approve_reply": "k2f_bundle_tbs05",
    "TBSM04_lead_reject": "k2f_bundle_tbs01",
    "TBSM05_support_reject": "k2f_bundle_tbs02",
    "TBSM06_duplicate_approve": "k2f_bundle_tbsm06_dup",
    "TBSM07_stale_approve": "k2f_bundle_tbs01",
    "TBSM08_unknown_negative_hold": "k2f_bundle_tbs04",
    "TBA01_safe_lead_auto_reply": "k2f_bundle_tba01",
    "TBA02_unknown_auto_hold": "k2f_bundle_tba02",
    "TBA03_safe_general_inquiry_auto_reply": "k2f_bundle_tba03",
    "TBA04_noisy_lead_auto_reply": "k2f_bundle_tba04",
    "TBA05_invoice_auto_hold": "k2f_bundle_tba05",
    "TBA06_support_complaint_auto_hold": "k2f_bundle_tba06",
    "TBA07_price_booking_commitment_hold": "k2f_bundle_tba07",
    "TBA08_sensitive_safety_hold": "k2f_bundle_tba08",
}

ALLOWLISTED_BUNDLE_IDS = frozenset(SCENARIO_BUNDLE_MAP.values())

# Minimal deterministic fixtures for foundation tests and future 2F.2 S01.
BUNDLE_FIXTURES: dict[str, dict[str, dict[str, Any]]] = {
    "k2f_bundle_s01": {
        "classification_v1": {
            "detected_job_type": "lead",
            "confidence": 0.9,
            "reasons": ["keyword_match"],
        },
        "entity_extraction_v1": {
            "entities": {"customer_name": "Anna Lindqvist", "email": "eval@example.com"},
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
    },
    "k2f_bundle_tbs01": {
        "classification_v1": {"detected_job_type": "lead", "confidence": 0.9, "reasons": ["campaign"]},
        "entity_extraction_v1": {"entities": {"customer_name": "Testbot Anna"}, "confidence": 0.85},
        "lead_scoring_v1": {"lead_score": 70, "priority": "medium", "routing": "crm_update", "reasons": [], "confidence": 0.85},
        "decisioning_v1": {"decision": "auto_route", "target_queue": "sales_queue", "action_flags": {"create_crm_lead": False, "notify_human": False, "request_missing_data": True}, "reasons": [], "confidence": 0.85},
    },
    "k2f_bundle_tbsm06_dup": {
        "classification_v1": {"detected_job_type": "lead", "confidence": 0.9, "reasons": ["campaign", "duplicate_approve"]},
        "entity_extraction_v1": {"entities": {"customer_name": "Testbot Anna Dup"}, "confidence": 0.85},
        "lead_scoring_v1": {"lead_score": 70, "priority": "medium", "routing": "crm_update", "reasons": [], "confidence": 0.85},
        "decisioning_v1": {"decision": "auto_route", "target_queue": "sales_queue", "action_flags": {"create_crm_lead": False, "notify_human": False, "request_missing_data": True}, "reasons": [], "confidence": 0.85},
    },
    "k2f_bundle_tbs02": {
        "classification_v1": {"detected_job_type": "customer_inquiry", "confidence": 0.88, "reasons": ["campaign"]},
        "entity_extraction_v1": {"entities": {"customer_name": "Testbot Erik"}, "confidence": 0.85},
        "lead_scoring_v1": {"lead_score": 40, "priority": "low", "routing": "support_queue", "reasons": [], "confidence": 0.8},
        "decisioning_v1": {"decision": "auto_route", "target_queue": "support_queue", "action_flags": {"create_crm_lead": False, "notify_human": True, "request_missing_data": False}, "reasons": [], "confidence": 0.85},
    },
    "k2f_bundle_tbs03": {
        "classification_v1": {"detected_job_type": "invoice", "confidence": 0.9, "reasons": ["campaign"]},
        "entity_extraction_v1": {"entities": {"customer_name": "Testbot Maria"}, "confidence": 0.85},
        "lead_scoring_v1": {"lead_score": 30, "priority": "low", "routing": "accounting_queue", "reasons": [], "confidence": 0.8},
        "decisioning_v1": {"decision": "auto_route", "target_queue": "accounting_queue", "action_flags": {"create_crm_lead": False, "notify_human": True, "request_missing_data": False}, "reasons": [], "confidence": 0.85},
    },
    "k2f_bundle_tbs04": {
        "classification_v1": {"detected_job_type": "unknown", "confidence": 0.5, "reasons": ["campaign"]},
        "entity_extraction_v1": {"entities": {}, "confidence": 0.4},
        "lead_scoring_v1": {"lead_score": 10, "priority": "low", "routing": "manual_review", "reasons": [], "confidence": 0.5},
        "decisioning_v1": {"decision": "send_for_approval", "target_queue": "manual_review", "action_flags": {"create_crm_lead": False, "notify_human": True, "request_missing_data": True}, "reasons": [], "confidence": 0.5},
    },
    "k2f_bundle_tbs05": {
        "classification_v1": {"detected_job_type": "lead", "confidence": 0.75, "reasons": ["campaign", "noisy"]},
        "entity_extraction_v1": {"entities": {"customer_name": "Testbot Noisy", "phone": "070-9998877"}, "confidence": 0.7},
        "lead_scoring_v1": {"lead_score": 55, "priority": "medium", "routing": "sales_queue", "reasons": [], "confidence": 0.75},
        "decisioning_v1": {"decision": "auto_route", "target_queue": "sales_queue", "action_flags": {"create_crm_lead": False, "notify_human": False, "request_missing_data": True}, "reasons": [], "confidence": 0.75},
    },
    "k2f_bundle_tba01": {
        "classification_v1": {
            "detected_job_type": "lead",
            "confidence": 0.9,
            "reasons": ["automatic_canary", "tba01_lead"],
        },
        "entity_extraction_v1": {
            "entities": {
                "customer_name": "Testbot Anna",
                "phone": "070-1234567",
                "address": "Testgatan 1, 12345 Teststad",
            },
            "confidence": 0.85,
        },
        "lead_scoring_v1": {
            "lead_score": 70,
            "priority": "medium",
            "routing": "crm_update",
            "reasons": ["automatic_canary"],
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
            "reasons": ["automatic_canary"],
            "confidence": 0.85,
        },
    },
    "k2f_bundle_tba02": {
        "classification_v1": {
            "detected_job_type": "unknown",
            "confidence": 0.45,
            "reasons": ["automatic_canary", "tba02_unknown"],
        },
        "entity_extraction_v1": {"entities": {}, "confidence": 0.35},
        "lead_scoring_v1": {
            "lead_score": 10,
            "priority": "low",
            "routing": "manual_review",
            "reasons": ["automatic_canary"],
            "confidence": 0.45,
        },
        "decisioning_v1": {
            "decision": "send_for_approval",
            "target_queue": "manual_review",
            "action_flags": {
                "create_crm_lead": False,
                "notify_human": True,
                "request_missing_data": True,
            },
            "reasons": ["automatic_canary"],
            "confidence": 0.45,
        },
    },
    "k2f_bundle_tba03": {
        "classification_v1": {
            "detected_job_type": "customer_inquiry",
            "confidence": 0.88,
            "reasons": ["automatic_core", "tba03_general_inquiry"],
        },
        "entity_extraction_v1": {
            "entities": {"customer_name": "Testbot Lisa"},
            "confidence": 0.85,
        },
        "lead_scoring_v1": {
            "lead_score": 35,
            "priority": "low",
            "routing": "support_queue",
            "reasons": ["automatic_core"],
            "confidence": 0.8,
        },
        "decisioning_v1": {
            "decision": "auto_route",
            "target_queue": "support_queue",
            "action_flags": {
                "create_crm_lead": False,
                "notify_human": False,
                "request_missing_data": True,
            },
            "reasons": ["automatic_core"],
            "confidence": 0.85,
        },
    },
    "k2f_bundle_tba04": {
        "classification_v1": {
            "detected_job_type": "lead",
            "confidence": 0.78,
            "reasons": ["automatic_core", "tba04_noisy_lead"],
        },
        "entity_extraction_v1": {
            "entities": {
                "customer_name": "Testbot Noisy Lead",
                "phone": "0709988776",
                "address": "Testgatan 9, 12345 Teststad",
            },
            "confidence": 0.72,
        },
        "lead_scoring_v1": {
            "lead_score": 58,
            "priority": "medium",
            "routing": "sales_queue",
            "reasons": ["automatic_core"],
            "confidence": 0.75,
        },
        "decisioning_v1": {
            "decision": "auto_route",
            "target_queue": "sales_queue",
            "action_flags": {
                "create_crm_lead": False,
                "notify_human": False,
                "request_missing_data": True,
            },
            "reasons": ["automatic_core"],
            "confidence": 0.75,
        },
    },
    "k2f_bundle_tba05": {
        "classification_v1": {
            "detected_job_type": "invoice",
            "confidence": 0.9,
            "reasons": ["automatic_core", "tba05_invoice"],
        },
        "entity_extraction_v1": {
            "entities": {"customer_name": "Testbot Maria Invoice"},
            "confidence": 0.85,
        },
        "lead_scoring_v1": {
            "lead_score": 25,
            "priority": "low",
            "routing": "accounting_queue",
            "reasons": ["automatic_core"],
            "confidence": 0.8,
        },
        "decisioning_v1": {
            "decision": "auto_route",
            "target_queue": "accounting_queue",
            "action_flags": {
                "create_crm_lead": False,
                "notify_human": True,
                "request_missing_data": False,
            },
            "reasons": ["automatic_core"],
            "confidence": 0.85,
        },
    },
    "k2f_bundle_tba06": {
        "classification_v1": {
            "detected_job_type": "customer_inquiry",
            "confidence": 0.86,
            "reasons": ["automatic_core", "tba06_support"],
        },
        "entity_extraction_v1": {
            "entities": {"customer_name": "Testbot Erik Complaint"},
            "confidence": 0.8,
        },
        "lead_scoring_v1": {
            "lead_score": 30,
            "priority": "medium",
            "routing": "support_queue",
            "reasons": ["automatic_core"],
            "confidence": 0.8,
        },
        "decisioning_v1": {
            "decision": "auto_route",
            "target_queue": "support_queue",
            "action_flags": {
                "create_crm_lead": False,
                "notify_human": True,
                "request_missing_data": False,
            },
            "reasons": ["automatic_core"],
            "confidence": 0.85,
        },
    },
    "k2f_bundle_tba07": {
        "classification_v1": {
            "detected_job_type": "lead",
            "confidence": 0.88,
            "reasons": ["automatic_core", "tba07_lead"],
        },
        "entity_extraction_v1": {
            "entities": {
                "customer_name": "Testbot Price Booking",
                "phone": "070-1122334",
                "address": "Testvägen 3, 12345 Teststad",
            },
            "confidence": 0.85,
        },
        "lead_scoring_v1": {
            "lead_score": 65,
            "priority": "medium",
            "routing": "sales_queue",
            "reasons": ["automatic_core"],
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
            "reasons": ["automatic_core"],
            "confidence": 0.85,
        },
    },
    "k2f_bundle_tba08": {
        "classification_v1": {
            "detected_job_type": "customer_inquiry",
            "confidence": 0.84,
            "reasons": ["automatic_core", "tba08_sensitive"],
        },
        "entity_extraction_v1": {
            "entities": {"customer_name": "Testbot Safety Synthetic"},
            "confidence": 0.8,
        },
        "lead_scoring_v1": {
            "lead_score": 20,
            "priority": "high",
            "routing": "support_queue",
            "reasons": ["automatic_core"],
            "confidence": 0.85,
        },
        "decisioning_v1": {
            "decision": "auto_route",
            "target_queue": "support_queue",
            "action_flags": {
                "create_crm_lead": False,
                "notify_human": True,
                "request_missing_data": False,
            },
            "reasons": ["automatic_core"],
            "confidence": 0.85,
        },
    },
}


def resolve_fixture_bundle_id(*, scenario_id: str, ai_mode: str) -> str | None:
    if ai_mode != "fixture_ai":
        return None
    bundle_id = SCENARIO_BUNDLE_MAP.get(scenario_id)
    if bundle_id is None:
        raise LiveEvalSafetyError(f"No allowlisted fixture bundle for scenario {scenario_id!r}")
    if bundle_id not in ALLOWLISTED_BUNDLE_IDS:
        raise LiveEvalSafetyError(f"fixture bundle {bundle_id!r} is not allowlisted")
    return bundle_id


def load_bundle_fixtures(bundle_id: str) -> dict[str, dict[str, Any]]:
    if bundle_id not in ALLOWLISTED_BUNDLE_IDS:
        raise LiveEvalSafetyError(f"Unknown fixture bundle {bundle_id!r}")
    fixtures = BUNDLE_FIXTURES.get(bundle_id)
    if fixtures is None:
        raise LiveEvalSafetyError(f"Fixture bundle {bundle_id!r} has no content")
    return fixtures
