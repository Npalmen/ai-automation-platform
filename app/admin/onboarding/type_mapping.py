"""Central service_type ↔ lead_type mapping (versioned)."""

from __future__ import annotations

SERVICE_TYPE_LEAD_TYPE_MAP_VERSION: int = 1

# Canonical onboarding uses service_type keys only.
# Legacy missing_info.py paths may resolve lead_type via this table.
SERVICE_TYPE_TO_LEAD_TYPE: dict[str, str] = {
    "ev_charger_installation": "ev_charger",
    "ev_charger_fault": "ev_charger",
    "solar_installation": "solar_installation",
    "solar_service": "solar_installation",
    "battery_storage": "battery_storage",
    "electrical_fault": "electrical_work",
    "inverter_support": "electrical_work",
    "electrical_panel": "electrical_work",
    "vvs_service": "vvs_service",
    "building_project": "building_project",
    "generic_lead": "unknown",
    "generic_support": "unknown",
    "invoice_generic": "unknown",
    "debt_collection_risk": "unknown",
}


def lead_type_for_service_type(service_type: str) -> str | None:
    return SERVICE_TYPE_TO_LEAD_TYPE.get(service_type)


def service_types_for_lead_type(lead_type: str) -> list[str]:
    return sorted(st for st, lt in SERVICE_TYPE_TO_LEAD_TYPE.items() if lt == lead_type)
