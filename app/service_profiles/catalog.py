"""Service catalog metadata — owned by service_profiles (Onboarding 2.0)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceCatalogEntry:
    service_type: str
    display_name_sv: str
    description_sv: str
    industry_keys: tuple[str, ...]
    module_keys: tuple[str, ...]


# Internal service_type keys unchanged; Swedish presentation + filter metadata.
SERVICE_CATALOG: dict[str, ServiceCatalogEntry] = {
    "ev_charger_installation": ServiceCatalogEntry(
        service_type="ev_charger_installation",
        display_name_sv="Laddboxinstallation",
        description_sv="Installation av laddbox och elbilsladdning.",
        industry_keys=("electrical", "solar_and_storage"),
        module_keys=("lead_management", "quote_drafts"),
    ),
    "solar_installation": ServiceCatalogEntry(
        service_type="solar_installation",
        display_name_sv="Solcellsinstallation",
        description_sv="Solceller och solenergi.",
        industry_keys=("solar_and_storage", "electrical"),
        module_keys=("lead_management", "quote_drafts"),
    ),
    "battery_storage": ServiceCatalogEntry(
        service_type="battery_storage",
        display_name_sv="Batterilager",
        description_sv="Hembatterier och energilager.",
        industry_keys=("solar_and_storage", "electrical"),
        module_keys=("lead_management",),
    ),
    "electrical_fault": ServiceCatalogEntry(
        service_type="electrical_fault",
        display_name_sv="Elfel / felsökning",
        description_sv="Akuta och planerade elfel.",
        industry_keys=("electrical",),
        module_keys=("customer_inquiries",),
    ),
    "inverter_support": ServiceCatalogEntry(
        service_type="inverter_support",
        display_name_sv="Växelriktarsupport",
        description_sv="Support kring växelriktare och solsystem.",
        industry_keys=("solar_and_storage", "electrical"),
        module_keys=("customer_inquiries", "lead_management"),
    ),
    "electrical_panel": ServiceCatalogEntry(
        service_type="electrical_panel",
        display_name_sv="Elskåp / elcentral",
        description_sv="Byte och uppgradering av elcentral.",
        industry_keys=("electrical", "construction"),
        module_keys=("lead_management", "quote_drafts"),
    ),
    "building_project": ServiceCatalogEntry(
        service_type="building_project",
        display_name_sv="Byggprojekt",
        description_sv="Större bygg- och renoveringsprojekt.",
        industry_keys=("construction", "carpentry"),
        module_keys=("lead_management", "quote_drafts"),
    ),
    "vvs_service": ServiceCatalogEntry(
        service_type="vvs_service",
        display_name_sv="VVS-service",
        description_sv="VVS-arbeten och servicebesök.",
        industry_keys=("plumbing",),
        module_keys=("customer_inquiries", "lead_management"),
    ),
    "generic_lead": ServiceCatalogEntry(
        service_type="generic_lead",
        display_name_sv="Allmän förfrågan",
        description_sv="Generisk lead utan specifik tjänst.",
        industry_keys=("other", "property_service", "ventilation", "carpentry"),
        module_keys=("lead_management",),
    ),
    "generic_support": ServiceCatalogEntry(
        service_type="generic_support",
        display_name_sv="Allmän support",
        description_sv="Generella kundärenden och support.",
        industry_keys=("other", "property_service", "ventilation"),
        module_keys=("customer_inquiries",),
    ),
    "invoice_generic": ServiceCatalogEntry(
        service_type="invoice_generic",
        display_name_sv="Fakturaärende",
        description_sv="Ekonomi- och fakturaärenden.",
        industry_keys=("other",),
        module_keys=("invoice_handling",),
    ),
    "debt_collection_risk": ServiceCatalogEntry(
        service_type="debt_collection_risk",
        display_name_sv="Inkasso / betalningsrisk",
        description_sv="Högrisk betalningsärenden.",
        industry_keys=("other",),
        module_keys=("invoice_handling",),
    ),
}


def get_catalog_entry(service_type: str) -> ServiceCatalogEntry | None:
    return SERVICE_CATALOG.get(service_type)


def list_services_for_tenant(
    *,
    capability_keys: list[str],
    industry_keys: list[str] | None = None,
) -> list[dict]:
    """Presenter/filter over service_profiles registry."""
    from app.service_profiles.registry import list_profiles

    caps = set(capability_keys or [])
    industries = set(industry_keys or [])
    result: list[dict] = []
    for profile in list_profiles():
        entry = SERVICE_CATALOG.get(profile.service_type)
        if entry is None:
            continue
        if caps and not (set(entry.module_keys) & caps):
            continue
        if industries and not (set(entry.industry_keys) & industries):
            if "other" not in industries:
                continue
        result.append(
            {
                "key": profile.service_type,
                "display_name_sv": entry.display_name_sv,
                "description_sv": entry.description_sv,
                "industry_keys": list(entry.industry_keys),
                "module_keys": list(entry.module_keys),
                "family": profile.family,
                "default_route": profile.default_route,
            }
        )
    return sorted(result, key=lambda r: r["display_name_sv"])
