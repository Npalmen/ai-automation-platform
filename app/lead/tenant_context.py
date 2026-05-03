"""Tenant Context Loader for the lead analysis layer.

Reads tenant memory/config and returns a normalised TenantLeadContext.
Falls back gracefully when context is absent — all engines still work.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TenantLeadContext:
    tenant_id: str
    context_available: bool = False
    sources_used: list[str] = field(default_factory=list)

    # Business profile
    company_name: str | None = None
    industry: str | None = None
    geographic_area: str | None = None
    tone: str | None = None          # e.g. "formal", "friendly"

    # Services the tenant offers (list of str or dicts with name/keywords/lead_type)
    services: list[dict] = field(default_factory=list)

    # Per-lead-type field requirements (override defaults)
    # Shape: { "solar_installation": { "required": [...], "optional": [...] }, ... }
    lead_requirements: dict[str, dict] = field(default_factory=dict)

    # Pricing guidelines per lead_type
    # Shape: { "solar_installation": { "price_range": "...", "notes": "..." }, ... }
    pricing_guidelines: dict[str, dict] = field(default_factory=dict)

    # Offer principles (list of strings, e.g. ["Always include ROT info"])
    offer_principles: list[str] = field(default_factory=list)

    # Geographic constraints (list of cities/regions served)
    served_areas: list[str] = field(default_factory=list)

    # Ideal customer profile hints
    ideal_customer: dict = field(default_factory=dict)

    # Routing hints (pass-through from memory)
    routing_hints: dict = field(default_factory=dict)

    # Scanner summaries keyed by system
    system_map: dict = field(default_factory=dict)

    def service_lead_types(self) -> list[str]:
        """Return lead_type strings for all configured services."""
        result = []
        for s in self.services:
            lt = s.get("lead_type")
            if lt:
                result.append(lt)
        return result

    def service_keywords_for(self, lead_type: str) -> list[str]:
        """Return extra keywords for a given lead_type from tenant service config."""
        for s in self.services:
            if s.get("lead_type") == lead_type:
                return s.get("keywords") or []
        return []

    def is_service_offered(self, lead_type: str) -> bool:
        """Return True if this lead_type is in the tenant's service list."""
        offered = self.service_lead_types()
        if not offered:
            return True  # no config → assume all types valid
        return lead_type in offered

    def schema_for(self, lead_type: str) -> dict | None:
        """Return tenant-specific field schema for lead_type, or None."""
        return self.lead_requirements.get(lead_type)

    def pricing_for(self, lead_type: str) -> dict | None:
        """Return tenant pricing guidelines for lead_type, or None."""
        return self.pricing_guidelines.get(lead_type)


def load_tenant_context(
    tenant_id: str,
    settings: dict,
) -> TenantLeadContext:
    """Build a TenantLeadContext from the raw settings dict stored in tenant_configs.

    Never raises — returns context_available=False on any missing data.
    """
    ctx = TenantLeadContext(tenant_id=tenant_id)

    memory: dict = settings.get("memory") or {}
    if not memory:
        return ctx

    sources: list[str] = []

    # Business profile
    bp: dict = memory.get("business_profile") or {}
    if bp:
        sources.append("business_profile")
        ctx.company_name = bp.get("company_name") or None
        ctx.industry = bp.get("industry") or None
        ctx.geographic_area = bp.get("geographic_area") or None
        ctx.tone = bp.get("tone") or None

    # Served areas (can also live under lead_config)
    lead_cfg: dict = memory.get("lead_config") or {}
    if lead_cfg:
        sources.append("lead_config")
        ctx.served_areas = lead_cfg.get("served_areas") or []
        ctx.ideal_customer = lead_cfg.get("ideal_customer") or {}
        ctx.offer_principles = lead_cfg.get("offer_principles") or []

        # Services
        svcs = lead_cfg.get("services") or []
        if svcs:
            ctx.services = svcs

        # Per-lead-type field requirements
        reqs = lead_cfg.get("lead_requirements") or {}
        if reqs:
            ctx.lead_requirements = reqs

        # Pricing guidelines
        pricing = lead_cfg.get("pricing_guidelines") or {}
        if pricing:
            ctx.pricing_guidelines = pricing

    # Also accept services directly under memory for simpler config
    if not ctx.services:
        svcs = memory.get("services") or []
        if svcs:
            ctx.services = svcs
            if "services" not in sources:
                sources.append("services")

    # Routing hints
    rh = memory.get("routing_hints") or {}
    if rh:
        ctx.routing_hints = rh
        sources.append("routing_hints")

    # System map (scanner results)
    sm = memory.get("system_map") or {}
    if sm:
        ctx.system_map = sm
        sources.append("system_map")

    ctx.sources_used = sources
    ctx.context_available = bool(sources)
    return ctx


def load_tenant_context_from_job(job: Any, db: Any = None) -> TenantLeadContext:
    """Load tenant context using a Job object and optional DB session.

    When db is provided reads live settings; otherwise returns empty context.
    """
    if db is None:
        return TenantLeadContext(tenant_id=job.tenant_id)

    try:
        from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
        settings = TenantConfigRepository.get_settings(db, job.tenant_id)
        return load_tenant_context(job.tenant_id, settings)
    except Exception:
        return TenantLeadContext(tenant_id=job.tenant_id)
