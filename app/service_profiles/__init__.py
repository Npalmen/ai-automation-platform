"""Service Profiles package.

Provides service-type-aware qualification schemas, follow-up questions, and
routing hints for installation/service company jobs.

Public surface:
    from app.service_profiles import get_profile, list_profiles, select_profile
    from app.service_profiles import compute_profile_missing_info
    from app.service_profiles import build_profile_question_message
    from app.service_profiles import apply_tenant_overrides
"""
from app.service_profiles.registry import get_profile, list_profiles
from app.service_profiles.qualification import (
    select_profile,
    compute_profile_missing_info,
    build_profile_question_message,
    apply_tenant_overrides,
)

__all__ = [
    "get_profile",
    "list_profiles",
    "select_profile",
    "compute_profile_missing_info",
    "build_profile_question_message",
    "apply_tenant_overrides",
]
