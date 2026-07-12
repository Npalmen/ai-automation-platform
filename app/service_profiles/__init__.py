"""Service Profiles package.

Provides service-type-aware qualification schemas, follow-up questions, and
routing hints for installation/service company jobs.

Public surface:
    from app.service_profiles import get_profile, list_profiles, select_profile
    from app.service_profiles import compute_profile_missing_info
    from app.service_profiles import compute_playbook_questions
    from app.service_profiles import build_profile_question_message
    from app.service_profiles import apply_tenant_overrides
    from app.service_profiles import detect_service_context
    from app.service_profiles import get_playbook, list_playbooks, get_complaint_override
    from app.service_profiles import detect_fact_state, detect_all_facts, FactState
    from app.service_profiles import resolve_customer_name, extract_body_signature_name
"""
from app.service_profiles.context import detect_service_context
from app.service_profiles.facts import FactState, detect_fact_state, detect_all_facts
from app.service_profiles.name_extraction import resolve_customer_name, extract_body_signature_name
from app.service_profiles.playbook import get_playbook, list_playbooks, get_complaint_override, is_complaint
from app.service_profiles.registry import get_profile, list_profiles
from app.service_profiles.qualification import (
    select_profile,
    compute_profile_missing_info,
    compute_playbook_questions,
    build_profile_question_message,
    apply_tenant_overrides,
)

__all__ = [
    "detect_service_context",
    "FactState",
    "detect_fact_state",
    "detect_all_facts",
    "resolve_customer_name",
    "extract_body_signature_name",
    "get_playbook",
    "list_playbooks",
    "get_complaint_override",
    "is_complaint",
    "get_profile",
    "list_profiles",
    "select_profile",
    "compute_profile_missing_info",
    "compute_playbook_questions",
    "build_profile_question_message",
    "apply_tenant_overrides",
]
