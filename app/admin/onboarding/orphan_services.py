"""Detect orphan/incompatible service profiles when modules change."""

from __future__ import annotations

from app.admin.onboarding.slice2a_registry import _CAPABILITY_PROFILE_HINTS
from app.service_profiles.catalog import get_catalog_entry


def detect_orphan_service_profiles(
    *,
    selected_profiles: list[str],
    capability_keys: list[str],
    industry_keys: list[str] | None = None,
) -> list[dict[str, str]]:
    """
    Return profiles that are selected but no longer compatible with modules/industries.

    Does not auto-remove — caller must require operator confirmation.
    """
    caps = set(capability_keys or [])
    industries = set(industry_keys or [])
    orphans: list[dict[str, str]] = []
    for profile_key in selected_profiles:
        reasons: list[str] = []
        entry = get_catalog_entry(profile_key)
        if entry and caps and not (set(entry.module_keys) & caps):
            reasons.append("modul")
        elif not entry:
            hinted = [
                cap
                for cap, hints in _CAPABILITY_PROFILE_HINTS.items()
                if profile_key in hints
            ]
            if caps and not (set(hinted) & caps):
                reasons.append("modul")
        if entry and industries and not (set(entry.industry_keys) & industries):
            if "other" not in industries:
                reasons.append("bransch")
        if reasons:
            label = entry.display_name_sv if entry else profile_key
            orphans.append(
                {
                    "profile_key": profile_key,
                    "label_sv": label,
                    "reason": " och ".join(reasons),
                }
            )
    return orphans
