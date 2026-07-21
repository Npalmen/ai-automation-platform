"""Integration group requirement resolution for onboarding Slice B."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from app.admin.onboarding.effective_config import build_effective_routing
from app.admin.onboarding.integration_draft_schemas import (
    GroupImplementationDraft,
    IntegrationsDraftPayload,
)
from app.admin.onboarding.integration_selection_draft import effective_selection_status
from app.admin.onboarding.registries import INTEGRATIONS, PRODUCT_CAPABILITIES
from app.admin.onboarding.slice2a_registry import _CAPABILITY_PROFILE_HINTS
from app.integrations.keys import ALTERNATIVES_GROUPS, INTEGRATION_REGISTRY

GroupImplementationType = Literal["manual_accounting_routing", "integration"]

ACCOUNTING_ROUTE_DESTINATIONS = frozenset({"finance", "invoice"})


@dataclass(frozen=True)
class IntegrationGroupEvaluation:
    group_key: str
    satisfied: bool
    implementation: str
    reason: str


def known_integration_groups() -> frozenset[str]:
    return frozenset(ALTERNATIVES_GROUPS.keys())


def canonical_keys_for_group(group_key: str) -> list[str]:
    members: list[str] = []
    for canonical, meta in INTEGRATION_REGISTRY.items():
        if str(meta.get("alternatives_group") or "") == group_key:
            members.append(canonical)
    return sorted(members)


def registry_keys_for_group(group_key: str) -> list[str]:
    keys: list[str] = []
    for canonical in canonical_keys_for_group(group_key):
        meta = INTEGRATION_REGISTRY.get(canonical, {})
        keys.append(str(meta.get("registry_key", canonical)))
    return sorted(set(keys))


def required_integration_groups_for_capabilities(capability_keys: list[str]) -> set[str]:
    groups: set[str] = set()
    for key in capability_keys:
        cap = PRODUCT_CAPABILITIES.get(key)
        if cap:
            groups.update(cap.required_integration_groups)
    return groups


def module_required_canonical_keys(
    capability_keys: list[str],
    *,
    allowed: set[str] | None = None,
) -> set[str]:
    required: set[str] = set()
    for cap_key in capability_keys:
        cap = PRODUCT_CAPABILITIES.get(cap_key)
        if not cap:
            continue
        for registry_key in cap.required_integrations:
            from app.integrations.keys import registry_key_to_canonical

            canonical = registry_key_to_canonical(registry_key)
            if canonical:
                required.add(canonical)
        for group in cap.required_integration_groups:
            for canonical in canonical_keys_for_group(group):
                if allowed is None or canonical in allowed:
                    required.add(canonical)
    return required


def has_valid_accounting_routing(
    *,
    modules_draft: dict[str, Any],
    service_profile_draft: dict[str, Any] | None,
    routing_draft: dict[str, Any] | None,
) -> bool:
    capability_keys = list(modules_draft.get("capabilities") or [])
    if "invoice_handling" not in capability_keys:
        return False
    effective = build_effective_routing(service_profile_draft, routing_draft)
    profile_hints = set(_CAPABILITY_PROFILE_HINTS.get("invoice_handling", ()))
    for route in effective.get("routes") or []:
        if route.get("service_type") not in profile_hints:
            continue
        if route.get("effective") in ACCOUNTING_ROUTE_DESTINATIONS:
            return True
    return False


def _integration_group_satisfied(
    group_key: str,
    *,
    draft: IntegrationsDraftPayload,
    modules_draft: dict[str, Any],
    service_profile_draft: dict[str, Any] | None,
    routing_draft: dict[str, Any] | None,
    required_by_module: bool,
) -> IntegrationGroupEvaluation:
    implementation = draft.group_implementations.get(group_key)
    if implementation and implementation.type == "manual_accounting_routing":
        if group_key == "finance_destination" and has_valid_accounting_routing(
            modules_draft=modules_draft,
            service_profile_draft=service_profile_draft,
            routing_draft=routing_draft,
        ):
            return IntegrationGroupEvaluation(
                group_key=group_key,
                satisfied=True,
                implementation="manual_accounting_routing",
                reason="valid_accounting_routing",
            )
        return IntegrationGroupEvaluation(
            group_key=group_key,
            satisfied=False,
            implementation="manual_accounting_routing",
            reason="manual_accounting_routing_missing_routing",
        )

    for registry_key in registry_keys_for_group(group_key):
        integ = INTEGRATIONS.get(registry_key)
        if not integ or not integ.supported_in_current_slice:
            continue
        selection_status, _ = effective_selection_status(
            draft,
            registry_key,
            required_by_module=required_by_module,
        )
        if selection_status == "not_selected":
            continue
        if selection_status == "selected_optional":
            return IntegrationGroupEvaluation(
                group_key=group_key,
                satisfied=True,
                implementation=registry_key,
                reason="optional_integration_selected",
            )
        if selection_status == "selected_required":
            return IntegrationGroupEvaluation(
                group_key=group_key,
                satisfied=True,
                implementation=registry_key,
                reason="required_integration_selected",
            )

    return IntegrationGroupEvaluation(
        group_key=group_key,
        satisfied=False,
        implementation="none",
        reason="group_not_configured",
    )


def evaluate_required_integration_groups(
    *,
    capability_keys: list[str],
    integrations_draft: IntegrationsDraftPayload | None,
    modules_draft: dict[str, Any],
    service_profile_draft: dict[str, Any] | None = None,
    routing_draft: dict[str, Any] | None = None,
) -> list[IntegrationGroupEvaluation]:
    groups = sorted(required_integration_groups_for_capabilities(capability_keys))
    if not groups:
        return []
    draft = integrations_draft
    if isinstance(draft, dict):
        draft = IntegrationsDraftPayload.model_validate(draft)
    elif draft is None:
        draft = IntegrationsDraftPayload()
    return [
        _integration_group_satisfied(
            group,
            draft=draft,
            modules_draft=modules_draft,
            service_profile_draft=service_profile_draft,
            routing_draft=routing_draft,
            required_by_module=True,
        )
        for group in groups
    ]


def unsatisfied_required_groups(
    evaluations: list[IntegrationGroupEvaluation],
) -> list[IntegrationGroupEvaluation]:
    return [item for item in evaluations if not item.satisfied]


def group_implementation_from_draft(raw: dict[str, Any] | None) -> dict[str, GroupImplementationDraft]:
    if not raw:
        return {}
    out: dict[str, GroupImplementationDraft] = {}
    for group_key, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        try:
            out[group_key] = GroupImplementationDraft.model_validate(payload)
        except Exception:
            continue
    return out


def get_active_finance_implementation(draft: IntegrationsDraftPayload) -> str:
    impl = draft.group_implementations.get("finance_destination")
    if impl and impl.type == "manual_accounting_routing":
        return "manual_accounting_routing"
    visma_status, _ = effective_selection_status(draft, "visma", required_by_module=False)
    if visma_status in ("selected_optional", "selected_required"):
        return "visma"
    return "none"


def preview_accounting_routes(
    *,
    modules_draft: dict[str, Any],
    service_profile_draft: dict[str, Any] | None,
    routing_draft: dict[str, Any] | None,
) -> list[dict[str, str]]:
    if "invoice_handling" not in (modules_draft.get("capabilities") or []):
        return []
    effective = build_effective_routing(service_profile_draft, routing_draft)
    profile_hints = set(_CAPABILITY_PROFILE_HINTS.get("invoice_handling", ()))
    routes: list[dict[str, str]] = []
    for route in effective.get("routes") or []:
        if route.get("service_type") not in profile_hints:
            continue
        routes.append(
            {
                "service_type": str(route.get("service_type") or ""),
                "effective": str(route.get("effective") or ""),
                "source": str(route.get("source") or ""),
            }
        )
    return routes


def build_finance_destination_status(
    *,
    draft: IntegrationsDraftPayload,
    modules_draft: dict[str, Any],
    service_profile_draft: dict[str, Any] | None,
    routing_draft: dict[str, Any] | None,
    tenant_id: str,
) -> dict[str, Any]:
    active = get_active_finance_implementation(draft)
    routes = preview_accounting_routes(
        modules_draft=modules_draft,
        service_profile_draft=service_profile_draft,
        routing_draft=routing_draft,
    )
    routing_valid = has_valid_accounting_routing(
        modules_draft=modules_draft,
        service_profile_draft=service_profile_draft,
        routing_draft=routing_draft,
    )
    evaluations = evaluate_required_integration_groups(
        capability_keys=list(modules_draft.get("capabilities") or []),
        integrations_draft=draft,
        modules_draft=modules_draft,
        service_profile_draft=service_profile_draft,
        routing_draft=routing_draft,
    )
    finance_eval = next((ev for ev in evaluations if ev.group_key == "finance_destination"), None)
    return {
        "group_key": "finance_destination",
        "active_implementation": active,
        "accounting_routes": routes,
        "accounting_routing_valid": routing_valid,
        "satisfied": bool(finance_eval.satisfied) if finance_eval else False,
        "reason": finance_eval.reason if finance_eval else "group_not_configured",
        "routing_step_link": f"/ops/customers/{tenant_id}/onboarding?step=routing",
        "blocks_activation": bool(finance_eval and not finance_eval.satisfied),
    }


def apply_finance_destination_patch(
    draft: IntegrationsDraftPayload,
    *,
    choice: str,
    visma_disposition: str | None = None,
) -> IntegrationsDraftPayload:
    from app.admin.onboarding.integration_draft_schemas import IntegrationSelectionDraft

    groups = dict(draft.group_implementations)
    selections = dict(draft.selections)

    if choice == "manual_accounting_routing":
        if visma_disposition not in ("not_selected", "selected_optional"):
            raise ValueError("visma_disposition is required for manual_accounting_routing")
        groups["finance_destination"] = GroupImplementationDraft(type="manual_accounting_routing")
        selections["visma"] = IntegrationSelectionDraft(
            selection_status=visma_disposition,  # type: ignore[arg-type]
            migration_review_required=False,
        )
        return draft.model_copy(update={"group_implementations": groups, "selections": selections})

    if choice == "visma":
        groups.pop("finance_destination", None)
        return draft.model_copy(update={"group_implementations": groups})

    if choice == "none":
        groups.pop("finance_destination", None)
        return draft.model_copy(update={"group_implementations": groups})

    raise ValueError(f"Unsupported finance destination choice: {choice}")


def reject_coming_later_group_implementation(integration_key: str | None) -> None:
    if not integration_key:
        return
    from app.integrations.keys import registry_key_to_canonical

    canonical = registry_key_to_canonical(integration_key) or integration_key
    meta = INTEGRATION_REGISTRY.get(canonical, {})
    if meta.get("support_status") == "coming_later" or not meta.get("selectable", False):
        raise ValueError(f"Integration '{integration_key}' is not selectable as group implementation")
