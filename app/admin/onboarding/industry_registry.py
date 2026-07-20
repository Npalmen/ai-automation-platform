"""Industry registry for onboarding identity step (Onboarding 2.0)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IndustryDefinition:
    key: str
    label_sv: str
    description_sv: str
    suggested_service_keys: tuple[str, ...]


INDUSTRIES: dict[str, IndustryDefinition] = {
    "electrical": IndustryDefinition(
        key="electrical",
        label_sv="Elektriker",
        description_sv="Installation, felsökning och elarbeten.",
        suggested_service_keys=(
            "ev_charger_installation",
            "electrical_fault",
            "electrical_panel",
            "inverter_support",
            "generic_lead",
        ),
    ),
    "carpentry": IndustryDefinition(
        key="carpentry",
        label_sv="Snickeri",
        description_sv="Bygg, renovering och inredning.",
        suggested_service_keys=("building_project", "generic_lead", "generic_support"),
    ),
    "plumbing": IndustryDefinition(
        key="plumbing",
        label_sv="VVS",
        description_sv="Värme, vatten och service.",
        suggested_service_keys=("vvs_service", "generic_support", "generic_lead"),
    ),
    "solar_and_storage": IndustryDefinition(
        key="solar_and_storage",
        label_sv="Sol & batteri",
        description_sv="Solceller, batterilager och energilösningar.",
        suggested_service_keys=(
            "solar_installation",
            "battery_storage",
            "inverter_support",
            "generic_lead",
        ),
    ),
    "construction": IndustryDefinition(
        key="construction",
        label_sv="Bygg",
        description_sv="Entreprenad och byggprojekt.",
        suggested_service_keys=("building_project", "generic_lead"),
    ),
    "ventilation": IndustryDefinition(
        key="ventilation",
        label_sv="Ventilation",
        description_sv="Ventilationssystem och luftbehandling.",
        suggested_service_keys=("generic_support", "generic_lead"),
    ),
    "property_service": IndustryDefinition(
        key="property_service",
        label_sv="Fastighetsservice",
        description_sv="Drift och felanmälan för fastigheter.",
        suggested_service_keys=("generic_support", "generic_lead"),
    ),
    "other": IndustryDefinition(
        key="other",
        label_sv="Övrigt",
        description_sv="Bransch utanför standardlistan.",
        suggested_service_keys=("generic_lead", "generic_support"),
    ),
}


def list_industries() -> list[dict]:
    return [
        {
            "key": ind.key,
            "label": ind.label_sv,
            "description": ind.description_sv,
            "suggested_service_keys": list(ind.suggested_service_keys),
        }
        for ind in sorted(INDUSTRIES.values(), key=lambda i: i.key)
    ]


def validate_industry_keys(keys: list[str]) -> list[str]:
    return [k for k in keys if k not in INDUSTRIES]
