"""Presenters for aggregate customer settings views."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.admin.customer_settings.domains import domain_permissions
from app.admin.customer_settings.readiness_invalidation import readiness_summary_for_tenant
from app.admin.customer_settings.validation import (
    integrations_draft_from_tenant,
    modules_draft_from_tenant,
)
from app.admin.integrations.selection_models import parse_selections_map
from app.admin.integrations.selection_resolver import derive_integration_selection
from app.admin.onboarding.integration_groups import (
    build_finance_destination_status,
    evaluate_required_integration_groups,
)
from app.admin.onboarding.registries import PRODUCT_CAPABILITIES
from app.core.admin_session import OperatorIdentity
from app.integrations.keys import INTEGRATION_REGISTRY, display_name_sv
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


def _domain_payload(record: TenantConfigRecord, domain: str) -> dict[str, Any]:
    settings = record.settings or {}
    if domain == "identity":
        return {
            "name": record.name,
            "slug": record.slug,
            **((settings.get("company") or {})),
        }
    if domain == "modules":
        return {
            "capabilities": list(modules_draft_from_tenant(record).get("capabilities") or []),
        }
    if domain == "services":
        return dict(settings.get("memory") or {})
    if domain == "routing":
        return dict(settings.get("routing") or {})
    if domain == "integrations":
        integrations = dict(settings.get("integrations") or {})
        return {
            "selections": integrations.get("selections") or {},
            "group_implementations": integrations.get("group_implementations") or {},
            "enabled_external_writes": integrations.get("enabled_external_writes") or [],
        }
    if domain == "automation":
        return {
            "policy": dict(settings.get("automation") or {}),
            "scheduler": dict(settings.get("scheduler") or {}),
            "effective_auto_actions": dict(record.auto_actions or {}),
            "external_writes_effective": (settings.get("integrations") or {}).get(
                "enabled_external_writes"
            )
            or [],
        }
    if domain == "intake":
        return dict(settings.get("intake") or {})
    return {}


def integration_selection_view(db: Session, record: TenantConfigRecord) -> list[dict[str, Any]]:
    settings = record.settings or {}
    selections = parse_selections_map((settings.get("integrations") or {}).get("selections"))
    items: list[dict[str, Any]] = []
    for canonical in sorted(INTEGRATION_REGISTRY.keys()):
        meta = INTEGRATION_REGISTRY[canonical]
        derived = derive_integration_selection(db, record, canonical)
        stored = selections.get(canonical)
        items.append(
            {
                "integration_key": canonical,
                "display_name_sv": display_name_sv(canonical),
                "selection_status": (
                    stored.selection_status if stored else derived.selection_status
                ),
                "support_status": meta.get("support_status"),
                "selectable": bool(meta.get("selectable", False)),
                "migration_review_required": (
                    stored.migration_review_required if stored else derived.migration_review_required
                ),
                "requirement_source": derived.requirement_source,
            }
        )
    return items


def integration_group_status(record: TenantConfigRecord) -> dict[str, Any]:
    settings = record.settings or {}
    modules = modules_draft_from_tenant(record)
    memory = settings.get("memory") or {}
    routing = settings.get("routing") or {}
    draft = integrations_draft_from_tenant(settings)
    evaluations = evaluate_required_integration_groups(
        capability_keys=list(modules.get("capabilities") or []),
        integrations_draft=draft,
        modules_draft=modules,
        service_profile_draft=memory.get("service_profile"),
        routing_draft=routing,
    )
    finance = build_finance_destination_status(
        draft=draft,
        modules_draft=modules,
        service_profile_draft=memory.get("service_profile"),
        routing_draft=routing,
        tenant_id=record.tenant_id,
    )
    return {
        "groups": [
            {
                "group_key": ev.group_key,
                "satisfied": ev.satisfied,
                "implementation": ev.implementation,
                "reason": ev.reason,
            }
            for ev in evaluations
        ],
        "finance_destination": finance,
    }


def routing_summary(record: TenantConfigRecord) -> dict[str, Any]:
    routing = (record.settings or {}).get("routing") or {}
    memory = (record.settings or {}).get("memory") or {}
    return {
        "routing": routing,
        "internal_routing_hints": memory.get("internal_routing_hints") or {},
    }


def automation_policy_summary(record: TenantConfigRecord) -> dict[str, Any]:
    settings = record.settings or {}
    return {
        "automation": settings.get("automation") or {},
        "scheduler_run_mode": (settings.get("scheduler") or {}).get("run_mode"),
        "operations_paused": bool((settings.get("operations") or {}).get("paused", False)),
        "auto_actions": record.auto_actions or {},
        "enabled_external_writes": (settings.get("integrations") or {}).get(
            "enabled_external_writes"
        )
        or [],
    }


def effective_capabilities(record: TenantConfigRecord) -> list[dict[str, Any]]:
    caps = _capability_keys(record)
    return [
        {
            "key": key,
            "label_sv": PRODUCT_CAPABILITIES[key].label_sv,
            "enabled_job_types": list(PRODUCT_CAPABILITIES[key].enabled_job_types),
        }
        for key in caps
        if key in PRODUCT_CAPABILITIES
    ]


def _capability_keys(record: TenantConfigRecord) -> list[str]:
    return list(modules_draft_from_tenant(record).get("capabilities") or [])


def build_aggregate_view(
    db: Session,
    record: TenantConfigRecord,
    operator: OperatorIdentity,
) -> dict[str, Any]:
    domains = {
        domain: _domain_payload(record, domain)
        for domain in (
            "identity",
            "modules",
            "services",
            "integrations",
            "routing",
            "automation",
            "intake",
        )
    }
    return {
        "tenant_id": record.tenant_id,
        "tenant_status": record.status,
        "lifecycle_status": record.lifecycle_status,
        "config_version": int(record.config_version or 1),
        "domains": domains,
        "effective_capabilities": effective_capabilities(record),
        "integration_selection_view": integration_selection_view(db, record),
        "integration_group_status": integration_group_status(record),
        "routing_summary": routing_summary(record),
        "automation_policy_summary": automation_policy_summary(record),
        "readiness_summary": readiness_summary_for_tenant(record),
        "permissions": domain_permissions(operator),
        "last_updated": {
            "at": record.updated_at.isoformat() if record.updated_at else None,
            "by": record.last_config_updated_by,
        },
    }
