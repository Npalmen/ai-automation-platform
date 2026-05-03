"""Tenant Context Loader for the support analysis layer.

Reads tenant memory/config and returns a TenantSupportContext.
Falls back gracefully when context is absent.

Memory shape expected at settings["memory"]["support_config"]:
  support_categories: list[str]
  support_requirements: { ticket_type: { required: [...], optional: [...] } }
  common_issues: [ { keywords: [...], solution_steps: [...], category: str } ]
  sla_rules: { critical_keywords: [...], urgent_categories: [...] }
  priority_rules: { high_value_keywords: [...] }
  warranty_rules: { warranty_period_months: int, covered_services: [...] }

Also reads from settings["memory"]["business_profile"] for:
  company_name, industry, geographic_area, tone

And from settings["memory"]["lead_config"]["services"] (shared with lead layer)
for service/offering matching.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TenantSupportContext:
    tenant_id: str
    context_available: bool = False
    sources_used: list[str] = field(default_factory=list)

    # Business profile (shared with lead layer)
    company_name: str | None = None
    industry: str | None = None
    geographic_area: str | None = None
    tone: str | None = None

    # Services the tenant offers (for matched_service detection)
    services: list[dict] = field(default_factory=list)

    # Support-specific config
    support_categories: list[str] = field(default_factory=list)

    # Per-ticket-type field requirements override
    # Shape: { "emergency": { "required": [...], "optional": [...] }, ... }
    support_requirements: dict[str, dict] = field(default_factory=dict)

    # Common issues / FAQ for response drafting
    # Shape: [ { "keywords": [...], "solution_steps": [...], "category": str } ]
    common_issues: list[dict] = field(default_factory=list)

    # SLA / priority rules
    # Shape: { "critical_keywords": [...], "urgent_categories": [...] }
    sla_rules: dict = field(default_factory=dict)

    # Priority rules for tenant-specific bonuses
    priority_rules: dict = field(default_factory=dict)

    # Warranty rules
    warranty_rules: dict = field(default_factory=dict)

    # Geographic constraints (shared key with lead config)
    served_areas: list[str] = field(default_factory=list)

    # Routing hints
    routing_hints: dict = field(default_factory=dict)

    def schema_for(self, ticket_type: str) -> dict | None:
        """Return tenant-specific field schema for ticket_type, or None."""
        return self.support_requirements.get(ticket_type)

    def service_lead_types(self) -> list[str]:
        return [s.get("lead_type", "") for s in self.services if s.get("lead_type")]

    def service_keywords_for(self, service_name: str) -> list[str]:
        for s in self.services:
            if s.get("lead_type") == service_name or s.get("name") == service_name:
                return s.get("keywords") or []
        return []

    def matching_common_issue(self, text: str) -> dict | None:
        """Return first common_issue whose keywords match text, or None."""
        import re
        for issue in self.common_issues:
            for kw in (issue.get("keywords") or []):
                if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text.lower()):
                    return issue
        return None

    def is_critical_by_sla(self, text: str) -> bool:
        """Return True if text matches any tenant-defined critical keyword."""
        import re
        for kw in (self.sla_rules.get("critical_keywords") or []):
            if re.search(r"\b" + re.escape(kw.lower()) + r"\b", text.lower()):
                return True
        return False

    def is_urgent_category(self, category: str) -> bool:
        return category in (self.sla_rules.get("urgent_categories") or [])


def load_support_context(
    tenant_id: str,
    settings: dict,
) -> TenantSupportContext:
    """Build a TenantSupportContext from raw settings dict.

    Never raises — returns context_available=False on any missing data.
    """
    ctx = TenantSupportContext(tenant_id=tenant_id)

    memory: dict = settings.get("memory") or {}
    if not memory:
        return ctx

    sources: list[str] = []

    # Business profile (shared)
    bp: dict = memory.get("business_profile") or {}
    if bp:
        sources.append("business_profile")
        ctx.company_name = bp.get("company_name") or None
        ctx.industry = bp.get("industry") or None
        ctx.geographic_area = bp.get("geographic_area") or None
        ctx.tone = bp.get("tone") or None

    # Services (shared with lead layer — same memory key)
    lead_cfg: dict = memory.get("lead_config") or {}
    if lead_cfg:
        svcs = lead_cfg.get("services") or []
        if svcs:
            ctx.services = svcs
            sources.append("lead_config_services")
        served = lead_cfg.get("served_areas") or []
        if served:
            ctx.served_areas = served

    # Support-specific config
    support_cfg: dict = memory.get("support_config") or {}
    if support_cfg:
        sources.append("support_config")
        ctx.support_categories = support_cfg.get("support_categories") or []
        ctx.support_requirements = support_cfg.get("support_requirements") or {}
        ctx.common_issues = support_cfg.get("common_issues") or []
        ctx.sla_rules = support_cfg.get("sla_rules") or {}
        ctx.priority_rules = support_cfg.get("priority_rules") or {}
        ctx.warranty_rules = support_cfg.get("warranty_rules") or {}

    # Routing hints
    rh = memory.get("routing_hints") or {}
    if rh:
        ctx.routing_hints = rh
        sources.append("routing_hints")

    ctx.sources_used = sources
    ctx.context_available = bool(sources)
    return ctx


def load_support_context_from_job(job: Any, db: Any = None) -> TenantSupportContext:
    """Load tenant support context using a Job object and optional DB session."""
    if db is None:
        return TenantSupportContext(tenant_id=job.tenant_id)
    try:
        from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
        settings = TenantConfigRepository.get_settings(db, job.tenant_id)
        return load_support_context(job.tenant_id, settings)
    except Exception:
        return TenantSupportContext(tenant_id=job.tenant_id)
