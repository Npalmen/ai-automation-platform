"""Map internal registry definitions to presentation-safe API responses."""

from __future__ import annotations

from app.admin.onboarding.industry_registry import list_industries
from app.admin.onboarding.registries import (
    AUTOMATION_PRESETS,
    INTEGRATIONS,
    PRODUCT_CAPABILITIES,
    REGISTRY_REVISION,
    REGISTRY_SCHEMA_VERSION,
    RUNTIME_FEATURES,
)
from app.admin.onboarding.registry_schemas import (
    OnboardingRegistriesResponse,
    RegistryAutomationPresetOut,
    RegistryCapabilityOut,
    RegistryDataStartModeOut,
    RegistryExternalRoutingTargetOut,
    RegistryIndustryOut,
    RegistryIntegrationOut,
    RegistryLeadFieldOut,
    RegistryRoutingDestinationOut,
    RegistryRuntimeFeatureOut,
    RegistryServiceProfileOut,
)
from app.admin.onboarding.slice2a_registry import (
    DATA_START_MODES,
    INTERNAL_ROUTING_DESTINATIONS,
    ROUTING_DESTINATION_LABELS_SV,
    lead_field_registry,
    profiles_for_onboarding,
)
from app.admin.onboarding.slice2b_registry import EXTERNAL_ROUTING_TARGETS
from app.admin.onboarding.type_mapping import SERVICE_TYPE_LEAD_TYPE_MAP_VERSION
from app.admin.onboarding.integration_selection_draft import registry_meta_for_key

_RUNTIME_ACTIVATION_NOTES = {
    "scheduler": "Förblir paused vid aktivering i slice 1.",
    "gmail_live_scan": "Startas aldrig av onboarding.",
    "api_access": "Kräver separat admin-åtgärd; skapas inte vid create.",
}

_ROUTING_LABELS = {
    "sales": "Försäljning",
    "support": "Kundservice",
    "invoice": "Faktura",
    "manual_review": "Manuell granskning",
    "service": "Service",
    "finance": "Ekonomi",
    "emergency": "Akut/jour",
    "management": "Ledning",
    "other": "Övrigt",
}


def present_registries() -> OnboardingRegistriesResponse:
    capabilities = [
        RegistryCapabilityOut(
            key=cap.key,
            label=cap.label_sv,
            description=cap.description_sv,
            availability=cap.availability,
            supported_in_current_slice=cap.supported_in_current_slice,
            dependencies={
                "integrations": list(cap.required_integrations),
                "integration_groups": list(cap.required_integration_groups),
                "runtime": list(cap.required_runtime),
            },
            required_integration_groups=list(cap.required_integration_groups),
            recommended_integration_groups=list(cap.recommended_integration_groups),
            requires_api_key=cap.requires_api_key,
        )
        for cap in sorted(PRODUCT_CAPABILITIES.values(), key=lambda c: c.key)
    ]
    integrations = []
    for integ in sorted(INTEGRATIONS.values(), key=lambda i: i.key):
        meta = registry_meta_for_key(integ.key)
        integrations.append(
            RegistryIntegrationOut(
                key=integ.key,
                label=integ.label_sv,
                description=integ.description_sv,
                availability=integ.availability,
                supported_in_current_slice=integ.supported_in_current_slice,
                dependencies={},
                verification_capability=integ.verification_capability,
                lifecycle_cap=integ.lifecycle_cap,
                limitation_ids=list(integ.limitation_ids),
                canonical_integration_key=str(meta.get("canonical_integration_key") or "") or None,
                category=str(meta.get("category") or "") or None,
                alternatives_group=meta.get("alternatives_group"),  # type: ignore[arg-type]
                alternatives_group_label_sv=meta.get("alternatives_group_label_sv"),  # type: ignore[arg-type]
                support_status=str(meta.get("support_status") or "") or None,
                selectable=bool(meta.get("selectable")),
            )
        )
    external_routing_targets = [
        RegistryExternalRoutingTargetOut(
            key=t.key,
            label=t.label_sv,
            job_type=t.job_type,
            integration_key=t.integration_key,
            enforced=t.enforced,
            availability=t.availability,
            supported_in_current_slice=t.supported_in_current_slice,
        )
        for t in sorted(EXTERNAL_ROUTING_TARGETS.values(), key=lambda x: x.key)
    ]
    runtime_features = [
        RegistryRuntimeFeatureOut(
            key=rt.key,
            label=rt.label_sv,
            description=rt.description_sv,
            availability=rt.availability,
            supported_in_current_slice=rt.supported_in_current_slice,
            activation_note=_RUNTIME_ACTIVATION_NOTES.get(rt.key),
        )
        for rt in sorted(RUNTIME_FEATURES.values(), key=lambda r: r.key)
    ]
    presets = [
        RegistryAutomationPresetOut(
            key=preset.key,
            version=preset.version,
            label=preset.label_sv,
            description=preset.description_sv,
            availability=preset.availability,
            supported_in_current_slice=preset.supported_in_current_slice,
            activation_allows_scheduler=preset.activation_allows_scheduler,
            scheduler_run_mode=preset.scheduler_run_mode,
            limitation=(
                "Scheduler förblir paused vid aktivering."
                if not preset.activation_allows_scheduler
                else None
            ),
        )
        for preset in sorted(AUTOMATION_PRESETS.values(), key=lambda p: (p.key, p.version))
    ]
    service_profiles = [
        RegistryServiceProfileOut(**item) for item in profiles_for_onboarding()
    ]
    lead_fields = [
        RegistryLeadFieldOut(**item) for item in lead_field_registry()
    ]
    routing_destinations = [
        RegistryRoutingDestinationOut(
            key=k,
            label=ROUTING_DESTINATION_LABELS_SV.get(k, _ROUTING_LABELS.get(k, k)),
        )
        for k in INTERNAL_ROUTING_DESTINATIONS
    ]
    industries = [
        RegistryIndustryOut(
            key=item["key"],
            label=item["label"],
            description=item["description"],
            suggested_service_keys=item["suggested_service_keys"],
        )
        for item in list_industries()
    ]
    data_start_modes = [
        RegistryDataStartModeOut(
            key=m.key,
            label=m.label_sv,
            description=m.description_sv,
            availability=m.availability,
            supported_in_current_slice=m.supported_in_current_slice,
            recommended=m.recommended,
        )
        for m in DATA_START_MODES.values()
    ]
    return OnboardingRegistriesResponse(
        registry_schema_version=REGISTRY_SCHEMA_VERSION,
        registry_revision=REGISTRY_REVISION,
        service_type_lead_type_map_version=SERVICE_TYPE_LEAD_TYPE_MAP_VERSION,
        product_capabilities=capabilities,
        integrations=integrations,
        runtime_features=runtime_features,
        automation_presets=presets,
        service_profiles=service_profiles,
        lead_field_registry=lead_fields,
        routing_destinations=routing_destinations,
        data_start_modes=data_start_modes,
        external_routing_targets=external_routing_targets,
        industries=industries,
    )
