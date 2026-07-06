"""Local evals for tenant-aware routing hints.

Verifies that:
  - Tenant routing_hints can override service profile default_route.
  - Tenant-specific required fields can replace/extend default profile schema
    via compute_profile_missing_info + schema_for seam.
  - Company name is used in question messages when tenant context is available.
  - Routing hint seam works without full onboarding UI.

Deterministic only — no LLM, no live integrations.
"""
from __future__ import annotations

import pytest

from app.lead.tenant_context import TenantLeadContext
from app.service_profiles import (
    get_profile,
    select_profile,
    compute_profile_missing_info,
    apply_tenant_overrides,
    build_profile_question_message,
)
from app.lead.question_generator import generate_question_message


# ── Helpers ───────────────────────────────────────────────────────────────────

def _tenant_ctx(
    *,
    company_name: str = "Elmontören AB",
    routing_hints: dict | None = None,
    lead_requirements: dict | None = None,
) -> TenantLeadContext:
    ctx = TenantLeadContext(tenant_id="TENANT_TEST")
    ctx.context_available = True
    ctx.company_name = company_name
    ctx.routing_hints = routing_hints or {}
    ctx.lead_requirements = lead_requirements or {}
    ctx.sources_used = ["test_fixture"]
    return ctx


# ══════════════════════════════════════════════════════════════════════════════
# Routing hint override
# ══════════════════════════════════════════════════════════════════════════════

class TestRoutingHintOverride:
    def test_tenant_routing_hint_overrides_default_route(self):
        """If tenant says ev_charger_installation → sales, profile route changes."""
        tenant_ctx = _tenant_ctx(routing_hints={"ev_charger_installation": "sales"})
        profile = select_profile("lead", lead_type="ev_charger", tenant_ctx=tenant_ctx)
        assert profile.default_route == "sales"

    def test_tenant_routing_hint_for_solar_overrides_route(self):
        tenant_ctx = _tenant_ctx(routing_hints={"solar_installation": "technical_team"})
        profile = select_profile("lead", lead_type="solar_installation", tenant_ctx=tenant_ctx)
        assert profile.default_route == "technical_team"

    def test_no_routing_hint_keeps_default_route(self):
        tenant_ctx = _tenant_ctx(routing_hints={})
        profile = select_profile("lead", lead_type="ev_charger", tenant_ctx=tenant_ctx)
        # Default route should be the registry default
        default_profile = get_profile("ev_charger_installation")
        assert profile.default_route == default_profile.default_route

    def test_routing_hint_for_other_service_does_not_affect_selected_profile(self):
        """Routing hint for solar should not bleed into ev_charger profile."""
        tenant_ctx = _tenant_ctx(routing_hints={"solar_installation": "sales"})
        profile = select_profile("lead", lead_type="ev_charger", tenant_ctx=tenant_ctx)
        default_profile = get_profile("ev_charger_installation")
        assert profile.default_route == default_profile.default_route

    def test_no_tenant_context_returns_default_route(self):
        profile = select_profile("lead", lead_type="ev_charger", tenant_ctx=None)
        default_profile = get_profile("ev_charger_installation")
        assert profile.default_route == default_profile.default_route

    def test_apply_tenant_overrides_preserves_service_type(self):
        """Override must not change service_type."""
        profile = get_profile("ev_charger_installation")
        tenant_ctx = _tenant_ctx(routing_hints={"ev_charger_installation": "sales"})
        overridden = apply_tenant_overrides(profile, tenant_ctx)
        assert overridden.service_type == "ev_charger_installation"

    def test_apply_tenant_overrides_preserves_required_fields(self):
        """Override must not change required_fields."""
        profile = get_profile("solar_installation")
        tenant_ctx = _tenant_ctx(routing_hints={"solar_installation": "technical_team"})
        overridden = apply_tenant_overrides(profile, tenant_ctx)
        assert overridden.required_fields == profile.required_fields


# ══════════════════════════════════════════════════════════════════════════════
# Tenant-specific required fields (schema seam)
# ══════════════════════════════════════════════════════════════════════════════

class TestTenantRequiredFields:
    def test_tenant_schema_can_add_pictures_to_ev_charger(self):
        """Tenant schema can extend required fields, e.g. add 'pictures'."""
        profile = get_profile("ev_charger_installation")
        tenant_ctx = _tenant_ctx(
            lead_requirements={
                "ev_charger_installation": {
                    "required": ["address", "main_fuse", "pictures"],
                    "optional": [],
                }
            }
        )
        result = compute_profile_missing_info(
            profile,
            {"message_text": "Laddbox till villa"},
            {},
            tenant_ctx=tenant_ctx,
        )
        assert result["schema_source"] == "tenant_override"
        assert "pictures" in result["missing_fields"]

    def test_tenant_schema_can_reduce_required_fields(self):
        """Tenant can simplify required fields to just address."""
        profile = get_profile("ev_charger_installation")
        tenant_ctx = _tenant_ctx(
            lead_requirements={
                "ev_charger_installation": {
                    "required": ["address"],
                    "optional": [],
                }
            }
        )
        result = compute_profile_missing_info(
            profile,
            {"message_text": "Laddbox på Storgatan 1"},
            {"address": "Storgatan 1"},
            tenant_ctx=tenant_ctx,
        )
        assert result["schema_source"] == "tenant_override"
        assert result["is_complete"] is True

    def test_default_schema_used_when_no_tenant_requirements(self):
        profile = get_profile("ev_charger_installation")
        tenant_ctx = _tenant_ctx(lead_requirements={})
        result = compute_profile_missing_info(
            profile,
            {"message_text": "Laddbox"},
            {},
            tenant_ctx=tenant_ctx,
        )
        assert result["schema_source"] == "service_profile"

    def test_tenant_schema_not_available_when_context_unavailable(self):
        profile = get_profile("ev_charger_installation")
        # context_available=False — override must be ignored
        tenant_ctx = TenantLeadContext(tenant_id="TENANT_TEST")
        tenant_ctx.context_available = False
        tenant_ctx.lead_requirements = {
            "ev_charger_installation": {"required": ["phone"], "optional": []}
        }
        result = compute_profile_missing_info(profile, {"message_text": "Laddbox"}, {}, tenant_ctx=tenant_ctx)
        assert result["schema_source"] == "service_profile"


# ══════════════════════════════════════════════════════════════════════════════
# Company name in follow-up questions
# ══════════════════════════════════════════════════════════════════════════════

class TestCompanyNameInReply:
    def test_company_name_appears_in_profile_question_message(self):
        profile = get_profile("ev_charger_installation")
        msg = build_profile_question_message(
            profile,
            ["address", "main_fuse"],
            company_name="ElFirman AB",
        )
        assert "ElFirman AB" in (msg or "")

    def test_company_name_appears_in_question_generator_output(self):
        profile = get_profile("solar_installation")
        tenant_ctx = _tenant_ctx(company_name="Solenergi AB")
        msg = generate_question_message(
            ["address", "roof_type"],
            tenant_ctx,
            "solar_installation",
            service_profile=profile,
        )
        assert "Solenergi AB" in (msg or "")

    def test_no_company_name_produces_valid_message(self):
        profile = get_profile("ev_charger_installation")
        msg = build_profile_question_message(
            profile,
            ["address"],
            company_name=None,
        )
        assert msg is not None
        assert len(msg) > 10

    def test_tenant_ctx_without_company_name_skips_company_in_intro(self):
        profile = get_profile("ev_charger_installation")
        tenant_ctx = _tenant_ctx(company_name="")
        msg = generate_question_message(
            ["address"],
            tenant_ctx,
            "ev_charger",
            service_profile=profile,
        )
        # No company name — should not contain empty company placeholder
        assert msg is not None
        assert "vi på  " not in (msg or "").lower()  # no double-space from empty name
