"""Versioned registries for onboarding capabilities, integrations, and presets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

Availability = Literal["available", "read_only", "deferred"]

# Bump when GET /admin/onboarding/registries response shape changes.
REGISTRY_SCHEMA_VERSION: int = 4


@dataclass(frozen=True)
class ProductCapabilityDefinition:
    key: str
    label_sv: str
    description_sv: str
    enabled_job_types: tuple[str, ...]
    required_integrations: tuple[str, ...] = ()
    required_integration_groups: tuple[str, ...] = ()
    recommended_integration_groups: tuple[str, ...] = ()
    required_runtime: tuple[str, ...] = ()
    availability: Availability = "available"
    supported_in_current_slice: bool = True

    @property
    def requires_api_key(self) -> bool:
        return "api_access" in self.required_runtime


@dataclass(frozen=True)
class IntegrationDefinition:
    key: str
    label_sv: str
    description_sv: str
    allowed_integration_key: str
    credential_model: str  # internal only — stripped by presenter
    availability: Availability = "read_only"
    supported_in_current_slice: bool = False
    verification_capability: str = "none"  # read_only_metadata | oauth_connect | label_config | none
    lifecycle_cap: str | None = None  # e.g. configured_not_running for gmail
    limitation_ids: tuple[str, ...] = ()
    freshness_max_hours: int | None = None


@dataclass(frozen=True)
class RuntimeFeatureDefinition:
    key: str
    label_sv: str
    description_sv: str
    config_paths: tuple[str, ...]
    availability: Availability = "available"
    supported_in_current_slice: bool = True


@dataclass(frozen=True)
class AutomationPresetDefinition:
    key: str
    version: int
    label_sv: str
    description_sv: str
    auto_actions: dict[str, str]
    scheduler_run_mode: str
    automation_flags: dict[str, bool]
    activation_allows_scheduler: bool
    availability: Availability = "available"
    supported_in_current_slice: bool = True


PRODUCT_CAPABILITIES: dict[str, ProductCapabilityDefinition] = {
    "lead_management": ProductCapabilityDefinition(
        key="lead_management",
        label_sv="Leadhantering",
        description_sv="Hantera inkommande leads via Monday-integration.",
        enabled_job_types=("lead",),
        required_integration_groups=("work_management",),
    ),
    "customer_inquiries": ProductCapabilityDefinition(
        key="customer_inquiries",
        label_sv="Kundärenden",
        description_sv="Hantera kundärenden via Gmail-intag.",
        enabled_job_types=("customer_inquiry",),
        required_integration_groups=("email_system",),
    ),
    "invoice_handling": ProductCapabilityDefinition(
        key="invoice_handling",
        label_sv="Faktura-/ekonomihantering",
        description_sv="Fakturaflöden med ekonomidestination (Visma, Fortnox, Bokio eller manuell ekonomirouting).",
        enabled_job_types=("invoice",),
        required_integration_groups=("finance_destination",),
    ),
    "quote_drafts": ProductCapabilityDefinition(
        key="quote_drafts",
        label_sv="Offertutkast",
        description_sv="Offertutkast med godkännandeförst-policy.",
        enabled_job_types=("quote",),
    ),
    "followups": ProductCapabilityDefinition(
        key="followups",
        label_sv="Uppföljningar",
        description_sv="Uppföljningar kräver scheduler-runtime (pausad vid aktivering).",
        enabled_job_types=("sales_followup",),
        required_runtime=("scheduler",),
    ),
}

INTEGRATIONS: dict[str, IntegrationDefinition] = {
    "gmail": IntegrationDefinition(
        key="gmail",
        label_sv="Gmail",
        description_sv="E-postintag via plattformens Gmail-koppling.",
        allowed_integration_key="google_mail",
        credential_model="platform_env",
        availability="available",
        supported_in_current_slice=True,
        verification_capability="label_config",
        lifecycle_cap="configured_not_running",
        limitation_ids=("gmail_live_intake_not_verifiable", "platform_credential_platform_level"),
    ),
    "monday": IntegrationDefinition(
        key="monday",
        label_sv="Monday",
        description_sv="CRM-export via plattformens Monday-koppling.",
        allowed_integration_key="monday",
        credential_model="platform_env",
        availability="available",
        supported_in_current_slice=True,
        verification_capability="read_only_metadata",
        limitation_ids=("platform_credential_platform_level", "ownership_not_verifiable"),
        freshness_max_hours=168,
    ),
    "visma": IntegrationDefinition(
        key="visma",
        label_sv="Visma",
        description_sv="Ekonomi via per-tenant OAuth.",
        allowed_integration_key="visma",
        credential_model="per_tenant_oauth",
        availability="available",
        supported_in_current_slice=True,
        verification_capability="oauth_connect",
        freshness_max_hours=24,
    ),
    "google_sheets": IntegrationDefinition(
        key="google_sheets",
        label_sv="Google Sheets",
        description_sv="Kalkylblad via tenant-inställningar.",
        allowed_integration_key="google_sheets",
        credential_model="tenant_settings",
        availability="available",
        supported_in_current_slice=True,
        verification_capability="read_only_metadata",
        limitation_ids=("ownership_not_verifiable",),
        freshness_max_hours=168,
    ),
    "fortnox": IntegrationDefinition(
        key="fortnox",
        label_sv="Fortnox",
        description_sv="Ekonomi via plattformens Fortnox-koppling.",
        allowed_integration_key="fortnox",
        credential_model="platform_env",
        availability="deferred",
        supported_in_current_slice=False,
        limitation_ids=("deferred_not_supported",),
    ),
}

RUNTIME_FEATURES: dict[str, RuntimeFeatureDefinition] = {
    "scheduler": RuntimeFeatureDefinition(
        key="scheduler",
        label_sv="Scheduler",
        description_sv="Schemalagd inkorgssynk; förblir pausad vid aktivering i slice 1.",
        config_paths=("settings.scheduler.run_mode",),
    ),
    "automation_master": RuntimeFeatureDefinition(
        key="automation_master",
        label_sv="Automation",
        description_sv="Övergripande automatiseringsflaggor från preset.",
        config_paths=("settings.automation",),
    ),
    "gmail_live_scan": RuntimeFeatureDefinition(
        key="gmail_live_scan",
        label_sv="Gmail live-skanning",
        description_sv="Live-skanning startas inte av onboarding.",
        config_paths=("settings.workflow_scan",),
        availability="deferred",
        supported_in_current_slice=False,
    ),
    "api_access": RuntimeFeatureDefinition(
        key="api_access",
        label_sv="API-åtkomst",
        description_sv="Tenant API-nyckel; skapas endast via separat admin-åtgärd.",
        config_paths=(),
    ),
}

_AUTOMATION_PRESET_ENTRIES: tuple[AutomationPresetDefinition, ...] = (
    AutomationPresetDefinition(
        key="observe_only",
        version=1,
        label_sv="Endast observera",
        description_sv="Alla jobb manuella; scheduler pausad.",
        auto_actions={
            "lead": "manual",
            "customer_inquiry": "manual",
            "invoice": "manual",
            "quote": "manual",
            "sales_followup": "manual",
        },
        scheduler_run_mode="paused",
        automation_flags={
            "leads_enabled": False,
            "support_enabled": False,
            "invoices_enabled": False,
            "followups_enabled": False,
            "demo_mode": True,
        },
        activation_allows_scheduler=False,
    ),
    AutomationPresetDefinition(
        key="prepare_only",
        version=1,
        label_sv="Endast förbered",
        description_sv="Semi-automation för leads och ärenden; scheduler pausad.",
        auto_actions={
            "lead": "semi",
            "customer_inquiry": "semi",
            "invoice": "manual",
            "quote": "semi",
            "sales_followup": "manual",
        },
        scheduler_run_mode="paused",
        automation_flags={
            "leads_enabled": True,
            "support_enabled": True,
            "invoices_enabled": False,
            "followups_enabled": False,
            "demo_mode": True,
        },
        activation_allows_scheduler=False,
    ),
    AutomationPresetDefinition(
        key="approval_first",
        version=1,
        label_sv="Godkännande först",
        description_sv="Semi-automation med godkännande; scheduler manuell.",
        auto_actions={
            "lead": "semi",
            "customer_inquiry": "semi",
            "invoice": "semi",
            "quote": "semi",
            "sales_followup": "semi",
        },
        scheduler_run_mode="manual",
        automation_flags={
            "leads_enabled": True,
            "support_enabled": True,
            "invoices_enabled": True,
            "followups_enabled": False,
            "demo_mode": False,
        },
        activation_allows_scheduler=False,
    ),
    AutomationPresetDefinition(
        key="controlled_automation",
        version=1,
        label_sv="Kontrollerad automation",
        description_sv="Begränsad auto för leads; scheduler manuell.",
        auto_actions={
            "lead": "auto",
            "customer_inquiry": "semi",
            "invoice": "semi",
            "quote": "semi",
            "sales_followup": "manual",
        },
        scheduler_run_mode="manual",
        automation_flags={
            "leads_enabled": True,
            "support_enabled": True,
            "invoices_enabled": True,
            "followups_enabled": False,
            "demo_mode": False,
        },
        activation_allows_scheduler=False,
    ),
)

AUTOMATION_PRESETS: dict[tuple[str, int], AutomationPresetDefinition] = {
    (preset.key, preset.version): preset for preset in _AUTOMATION_PRESET_ENTRIES
}


def resolve_preset(key: str, version: int) -> AutomationPresetDefinition | None:
    return AUTOMATION_PRESETS.get((key, version))


def list_preset_versions(key: str) -> list[int]:
    return sorted(v for (k, v) in AUTOMATION_PRESETS if k == key)


def collect_required_runtime(capability_keys: list[str]) -> set[str]:
    required: set[str] = set()
    for key in capability_keys:
        cap = PRODUCT_CAPABILITIES.get(key)
        if cap:
            required.update(cap.required_runtime)
    return required


def capability_requires_api_key(capability_keys: list[str]) -> bool:
    return any(
        PRODUCT_CAPABILITIES[k].requires_api_key
        for k in capability_keys
        if k in PRODUCT_CAPABILITIES
    )


def _canonical_business_payload() -> dict:
    caps = {
        k: {
            "enabled_job_types": list(v.enabled_job_types),
            "required_integrations": list(v.required_integrations),
            "required_integration_groups": list(v.required_integration_groups),
            "recommended_integration_groups": list(v.recommended_integration_groups),
            "required_runtime": list(v.required_runtime),
            "availability": v.availability,
        }
        for k, v in sorted(PRODUCT_CAPABILITIES.items())
    }
    integrations = {
        k: {
            "allowed_integration_key": v.allowed_integration_key,
            "availability": v.availability,
        }
        for k, v in sorted(INTEGRATIONS.items())
    }
    runtime = {
        k: {"availability": v.availability}
        for k, v in sorted(RUNTIME_FEATURES.items())
    }
    presets = [
        {
            "key": p.key,
            "version": p.version,
            "scheduler_run_mode": p.scheduler_run_mode,
            "activation_allows_scheduler": p.activation_allows_scheduler,
        }
        for p in sorted(_AUTOMATION_PRESET_ENTRIES, key=lambda x: (x.key, x.version))
    ]
    return {
        "capabilities": caps,
        "integrations": integrations,
        "runtime_features": runtime,
        "automation_presets": presets,
    }


def compute_registry_revision() -> str:
    payload = json.dumps(_canonical_business_payload(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


REGISTRY_REVISION: str = compute_registry_revision()


def preset_snapshot(preset: AutomationPresetDefinition) -> dict:
    return {
        "preset_key": preset.key,
        "preset_version": preset.version,
        "auto_actions": dict(preset.auto_actions),
        "scheduler_run_mode": preset.scheduler_run_mode,
        "automation_flags": dict(preset.automation_flags),
        "activation_allows_scheduler": preset.activation_allows_scheduler,
    }


def resolve_modules_to_tenant_config(
    capability_keys: list[str],
    integration_keys: list[str],
) -> tuple[list[str], list[str]]:
    job_types: set[str] = set()
    integrations: set[str] = set()
    for key in capability_keys:
        cap = PRODUCT_CAPABILITIES.get(key)
        if cap:
            job_types.update(cap.enabled_job_types)
    for key in integration_keys:
        integ = INTEGRATIONS.get(key)
        if integ:
            integrations.add(integ.allowed_integration_key)
    return sorted(job_types), sorted(integrations)


class RegistryIntegrityError(Exception):
    """Registry definitions failed integrity validation."""


def validate_registry_integrity() -> None:
    cap_keys = set(PRODUCT_CAPABILITIES.keys())
    integ_keys = set(INTEGRATIONS.keys())
    runtime_keys = set(RUNTIME_FEATURES.keys())

    if len(cap_keys) != len(PRODUCT_CAPABILITIES):
        raise RegistryIntegrityError("Duplicate product capability keys.")
    if len(integ_keys) != len(INTEGRATIONS):
        raise RegistryIntegrityError("Duplicate integration keys.")
    if len(runtime_keys) != len(RUNTIME_FEATURES):
        raise RegistryIntegrityError("Duplicate runtime feature keys.")

    preset_pairs = list(AUTOMATION_PRESETS.keys())
    if len(preset_pairs) != len(set(preset_pairs)):
        raise RegistryIntegrityError("Duplicate automation preset key/version pairs.")

    known_groups = {
        "email_system",
        "finance_destination",
        "work_management",
        "spreadsheet_export",
        "calendar_system",
    }

    for cap in PRODUCT_CAPABILITIES.values():
        for dep in cap.required_integrations:
            if dep not in integ_keys:
                raise RegistryIntegrityError(
                    f"Capability '{cap.key}' references unknown integration '{dep}'."
                )
        for group in cap.required_integration_groups:
            if group not in known_groups:
                raise RegistryIntegrityError(
                    f"Capability '{cap.key}' references unknown integration group '{group}'."
                )
        for group in cap.recommended_integration_groups:
            if group not in known_groups:
                raise RegistryIntegrityError(
                    f"Capability '{cap.key}' references unknown recommended group '{group}'."
                )
        for dep in cap.required_runtime:
            if dep not in runtime_keys:
                raise RegistryIntegrityError(
                    f"Capability '{cap.key}' references unknown runtime '{dep}'."
                )

    for preset in AUTOMATION_PRESETS.values():
        if preset.version < 1:
            raise RegistryIntegrityError(f"Invalid preset version for '{preset.key}'.")
