"""Service profile qualification helpers.

Provides:
    select_profile()            — choose the right ServiceProfile for a job
    compute_profile_missing_info() — compute which required fields are present/missing
    build_profile_question_message() — build a Swedish follow-up question message
    apply_tenant_overrides()    — thin seam for future tenant profile overrides

The four-level hierarchy is:
    1. General core      (classification, risk, approval — not here)
    2. Industry/family   (installation_service | generic_business)
    3. Service profile   (ev_charger_installation, solar_installation, …)
    4. Tenant/customer   (apply_tenant_overrides — currently a seam)

None of these functions make network calls or touch the database.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.service_profiles.context import detect_service_context
from app.service_profiles.models import ServiceProfile
from app.service_profiles.registry import get_profile, _REGISTRY

if TYPE_CHECKING:
    from app.lead.tenant_context import TenantLeadContext


# ── Lead-type → service_type mapping ─────────────────────────────────────────

_LEAD_TYPE_TO_PROFILE: dict[str, str] = {
    "ev_charger":          "ev_charger_installation",
    "solar_installation":  "solar_installation",
    "battery_storage":     "battery_storage",
    "electrical_work":     "electrical_panel",
    "roof_painting":       "generic_lead",
    "roof_cleaning":       "generic_lead",
}

def _refine_profile_by_context(profile_key: str, context: str, lower_text: str) -> str:
    """Return a refined profile key based on service context.

    Handles cases where keyword classification picks the wrong profile:
    - solar_installation + add_on_existing + battery keywords → battery_storage
    - ev_charger_installation + repair_or_fault → ev_charger_fault
    """
    if (
        profile_key == "solar_installation"
        and context == "add_on_existing"
        and any(kw in lower_text for kw in ("batteri", "batterilager", "laddlager", "energilager"))
    ):
        return "battery_storage"

    if profile_key == "ev_charger_installation" and context == "repair_or_fault":
        return "ev_charger_fault"

    return profile_key


# Support-category / text → service_type
_INVERTER_KEYWORDS = ("växelriktare", "inverter", "invertern")
_ELECTRICAL_FAULT_KEYWORDS = (
    "jordfelsbrytare", "felsökning", "kortslutning", "elfel",
    "säkring löser", "säkring slår",
)
_DEBT_COLLECTION_KEYWORDS = (
    "inkasso", "betalningskrav", "kravbrev", "kronofogden",
    "förfallen skuld", "betalningsanmärkning",
)
_VVS_KEYWORDS = (
    "vattenläcka", "läcka", "rörmokar", "rörmokare", "vvs", "rörmokeri",
    "avlopp", "toalett", "droppande", "diskbänk",
)


# ── Field presence detection ──────────────────────────────────────────────────

def _combined(input_data: dict) -> str:
    subject = (input_data.get("subject") or "").lower()
    body = (input_data.get("message_text") or "").lower()
    return f"{subject} {body}"


def _profile_field_present(field: str, text: str, entities: dict[str, Any]) -> bool:
    """Return True if *field* can be considered present given *text* and *entities*.

    Handles both the standard lead fields (delegating to existing logic where
    possible) and the new service-profile-specific fields.
    """
    # ── standard entity fields ─────────────────────────────────────────────
    if field == "address":
        if entities.get("address") or entities.get("city"):
            return True
        from app.workflows.processors.ai_processor_utils import extract_swedish_location
        loc = extract_swedish_location(text)
        return bool(loc.get("street_address") or loc.get("city") or loc.get("postal_code"))

    if field == "contact_name":
        return bool(entities.get("customer_name") or entities.get("company_name"))

    if field == "phone_or_email":
        return bool(
            entities.get("phone") or entities.get("email")
            or re.search(r"\b0\d[\d\s\-]{6,12}\b", text)
            or "@" in text
        )

    if field == "main_fuse":
        return bool(
            re.search(r"\b(?:huvudsäkring|säkring)\b", text)
            or re.search(r"\b\d{1,3}\s*a\b", text)  # "16a", "20 a"
            or re.search(r"\b(?:16|20|25|35|50|63|80|100)\b", text)
        )

    if field == "property_type":
        kws = (
            "villa", "radhus", "lägenhet", "brf", "fastighet",
            "hus", "kontor", "lokal", "garage", "lantbruk", "gård",
        )
        return any(kw in text for kw in kws)

    if field == "annual_consumption":
        return bool(
            re.search(r"\b\d{3,6}\s*(?:kwh|kw/h)\b", text)
            or any(kw in text for kw in ("årsförbrukning", "elförbrukning", "förbrukning"))
        )

    if field == "installation_timeline":
        return any(
            kw in text
            for kw in ("när", "tidplan", "månad", "kvartal", "vecka", "datum", "snart", "år")
        )

    if field == "roof_type":
        return any(
            kw in text
            for kw in (
                "betong", "tegel", "tegelpannor", "plåt", "shingel",
                "eternit", "trätak", "platt tak", "sadel", "taktyp",
            )
        )

    if field == "solar_exists":
        return any(kw in text for kw in ("solcell", "solpanel", "solar", "befintlig solar", "har solar"))

    if field == "battery_interest":
        return any(kw in text for kw in ("batteri", "batterilager", "lagra"))

    if field == "battery_capacity_preference":
        return bool(re.search(r"\b\d+\s*kwh\b", text))

    if field == "desired_location":
        return any(
            kw in text
            for kw in (
                "garage", "carport", "utomhus", "väggen", "inne i",
                "placering", "ingången", "parkeringsplats",
            )
        )

    if field == "charger_count":
        return any(
            kw in text
            for kw in ("en laddbox", "två laddbox", "antal laddbox", "laddpunkt")
        ) or bool(re.search(r"\b\d+\s*laddbox", text))

    if field == "current_panel_age":
        return any(
            kw in text
            for kw in ("gammal", "år gammal", "elcentral", "ålder", "proppskåp", "eltavla")
        )

    if field == "issue_description":
        body = (text.split("\n", 1)[-1] if "\n" in text else text).strip()
        return len(body) >= 20

    if field == "safety_risk":
        risk_kws = (
            "luktar bränt", "bränt lukt", "gnistor", "gnistrar",
            "elstöt", "brandrisk", "kortslutning", "inga risker", "ej akut",
            "inget akut", "inte farligt",
        )
        # Present means the customer has addressed the safety question (yes or no)
        return any(kw in text for kw in risk_kws)

    if field == "error_code":
        return bool(
            re.search(r"\b(?:felkod|error|e-\d+|fel \d+)\b", text)
            or "felkod" in text
        )

    if field == "inverter_model_or_error_code":
        return bool(
            any(kw in text for kw in ("felkod", "modell", "typ", "serie"))
            or re.search(r"\b[A-Z]{2,}\d{2,}", text)  # model number pattern
        )

    if field == "production_status":
        return any(
            kw in text
            for kw in (
                "producerar", "produktion", "kwh", "inte igång",
                "inga solceller", "producerar inget", "producerar lite",
            )
        )

    if field == "service_type":
        body_len = len(text.strip())
        return body_len >= 10

    # ── invoice fields ─────────────────────────────────────────────────────
    if field == "invoice_number_or_reference":
        return bool(
            entities.get("invoice_number")
            or re.search(r"\b(?:faktura(?:nummer)?|invoice|ref)\b", text)
        )

    if field == "amount":
        return bool(
            entities.get("amount")
            or re.search(r"\d+\s*kr\b", text)
            or re.search(r"\bsek\b", text)
        )

    if field == "supplier_or_customer":
        return bool(entities.get("supplier_name") or entities.get("customer_name"))

    if field == "due_date":
        return bool(
            entities.get("due_date")
            or re.search(r"\b20\d{2}[-/.]\d{2}[-/.]\d{2}\b", text)
            or any(kw in text for kw in ("förfallodatum", "betala senast", "betalas"))
        )

    if field == "ocr_number":
        return bool(re.search(r"\bocr\b", text))

    if field == "vat":
        return bool(re.search(r"\b(?:moms|mervärdesskatt|vat)\b", text))

    # ── debt-collection fields ─────────────────────────────────────────────
    if field == "sender":
        return bool(
            entities.get("customer_name") or entities.get("company_name")
            or entities.get("email") or entities.get("sender_name")
        )

    if field == "reference":
        return bool(
            entities.get("invoice_number")
            or re.search(r"\b(?:ref(?:erens)?|ärendenummer|ärende)\b", text)
        )

    if field == "deadline":
        return bool(
            re.search(r"\b20\d{2}[-/.]\d{2}[-/.]\d{2}\b", text)
            or any(kw in text for kw in ("senaste betalning", "sista datum", "betala senast"))
        )

    if field == "legal_threat":
        return any(
            kw in text
            for kw in ("advokat", "rättslig", "polisanmälan", "stämning", "inkasso")
        )

    # ── phone / email ──────────────────────────────────────────────────────
    if field == "phone":
        return bool(
            entities.get("phone")
            or re.search(r"\b07\d{8}\b", text)
            or re.search(r"\b0[0-9]{1,3}[-\s]?\d{6,9}\b", text)
        )

    if field == "email":
        return bool(
            entities.get("email")
            or re.search(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", text)
        )

    # ── generic entity fallback ────────────────────────────────────────────
    # If the entity extractor found a value for this field, treat as present.
    if entities.get(field):
        return True

    # ── always-ask fields ──────────────────────────────────────────────────
    if field in ("notes",):
        return False

    return False


# ── Core selection logic ──────────────────────────────────────────────────────

def select_profile(
    job_type: str,
    lead_type: str | None = None,
    support_category: str | None = None,
    text: str | None = None,
    tenant_ctx: "TenantLeadContext | None" = None,
) -> ServiceProfile:
    """Choose the best ServiceProfile for a job.

    Selection priority:
      1. Invoice: debt_collection_risk if high-risk text, else invoice_generic.
      2. Support / customer_inquiry: safety → electrical_fault; inverter keywords →
         inverter_support; electrical fault keywords → electrical_fault; else generic_support.
      3. Lead: mapped by lead_type; fallback generic_lead.
      4. Unknown / other: text-based keyword scan, fallback generic_lead.

    Tenant profile overrides are applied at the end via apply_tenant_overrides().
    """
    lower_text = (text or "").lower()

    # ── invoice path ───────────────────────────────────────────────────────
    if job_type == "invoice":
        from app.workflows.processors.ai_processor_utils import detect_invoice_risk_level
        if lower_text and detect_invoice_risk_level("", lower_text) == "high_risk":
            profile = _REGISTRY["debt_collection_risk"]
        else:
            profile = _REGISTRY["invoice_generic"]
        return apply_tenant_overrides(profile, tenant_ctx)

    # ── support / customer_inquiry path ───────────────────────────────────
    if job_type in ("customer_inquiry", "support"):
        if support_category == "safety" or (
            lower_text
            and any(kw in lower_text for kw in ("luktar bränt", "gnistor", "gnistrar", "elstöt"))
        ):
            profile = _REGISTRY["electrical_fault"]
        elif lower_text and any(kw in lower_text for kw in _INVERTER_KEYWORDS):
            profile = _REGISTRY["inverter_support"]
        elif lower_text and any(kw in lower_text for kw in _ELECTRICAL_FAULT_KEYWORDS):
            profile = _REGISTRY["electrical_fault"]
        elif lower_text and any(kw in lower_text for kw in _VVS_KEYWORDS):
            profile = _REGISTRY["vvs_service"]
        else:
            profile = _REGISTRY["generic_support"]
        return apply_tenant_overrides(profile, tenant_ctx)

    # ── lead path ─────────────────────────────────────────────────────────
    if job_type == "lead":
        profile_key = _LEAD_TYPE_TO_PROFILE.get(lead_type or "", "generic_lead")

        # Context-aware refinement: adjust profile when context contradicts
        # the lead_type classification (e.g. "we already have solar + want battery").
        if lower_text:
            context = detect_service_context(lower_text)
            profile_key = _refine_profile_by_context(profile_key, context, lower_text)

        profile = _REGISTRY.get(profile_key) or _REGISTRY["generic_lead"]
        return apply_tenant_overrides(profile, tenant_ctx)

    # ── fallback: scan keywords then use generic_lead ─────────────────────
    if lower_text:
        for stored_profile in _REGISTRY.values():
            if any(kw in lower_text for kw in stored_profile.keywords):
                return apply_tenant_overrides(stored_profile, tenant_ctx)

    return apply_tenant_overrides(_REGISTRY["generic_lead"], tenant_ctx)


# ── Missing-info computation ──────────────────────────────────────────────────

def compute_profile_missing_info(
    profile: ServiceProfile,
    input_data: dict,
    entities: dict[str, Any] | None = None,
    tenant_ctx: "TenantLeadContext | None" = None,
) -> dict[str, Any]:
    """Return a qualification result dict for *profile* given *input_data*.

    Returns:
        service_type:       profile.service_type
        required_fields:    list[str]
        optional_fields:    list[str]
        present_fields:     list[str] (required only)
        missing_fields:     list[str] (required only)
        completeness_score: float 0.0–1.0
        is_complete:        bool
        schema_source:      "service_profile" | "tenant_override"
    """
    entities = entities or {}
    text = _combined(input_data)

    # Allow tenant to override required/optional via lead_requirements
    schema_source = "service_profile"
    required = list(profile.required_fields)
    optional = list(profile.optional_fields)

    if tenant_ctx and tenant_ctx.context_available:
        tenant_schema = tenant_ctx.schema_for(profile.service_type)
        if tenant_schema:
            required = list(tenant_schema.get("required", required))
            optional = list(tenant_schema.get("optional", optional))
            schema_source = "tenant_override"

    present: list[str] = []
    missing: list[str] = []
    for field in required:
        if _profile_field_present(field, text, entities):
            present.append(field)
        else:
            missing.append(field)

    completeness = len(present) / len(required) if required else 1.0

    return {
        "service_type": profile.service_type,
        "required_fields": required,
        "optional_fields": optional,
        "present_fields": present,
        "missing_fields": missing,
        "completeness_score": round(completeness, 3),
        "is_complete": len(missing) == 0,
        "schema_source": schema_source,
    }


# ── Question message builder ──────────────────────────────────────────────────

def build_profile_question_message(
    profile: ServiceProfile,
    missing_fields: list[str],
    company_name: str | None = None,
) -> str | None:
    """Return a Swedish customer question message for *missing_fields*, or None.

    Uses the profile's follow_up_intro and follow_up_questions for service-
    specific, context-rich questions rather than generic field labels.
    """
    if not missing_fields:
        return None

    intro = profile.follow_up_intro
    if company_name:
        # Personalise intro with company name when available
        intro = intro.replace(
            "Vi behöver", f"Vi på {company_name} behöver"
        ).replace(
            "vi behöver", f"vi på {company_name} behöver"
        ).replace(
            "vi gärna:", f"vi på {company_name} gärna:"
        ).replace(
            "vi:", f"vi på {company_name}:"
        )

    lines: list[str] = []
    for f in missing_fields:
        label = (
            profile.follow_up_questions.get(f)
            or f.replace("_", " ").capitalize()
        )
        lines.append(f"• {label}")

    body = "\n".join(lines)
    return f"{intro}\n\n{body}\n\nSkicka gärna tillbaka det du kan, så hör vi av oss snart."


# ── Tenant override seam ──────────────────────────────────────────────────────

def apply_tenant_overrides(
    profile: ServiceProfile,
    tenant_ctx: "TenantLeadContext | None" = None,
) -> ServiceProfile:
    """Return a profile with tenant overrides applied.

    Currently a thin seam — returns *profile* unchanged if no tenant context
    or if the tenant has no override for this profile's service_type.

    Future connections (see docs/02-first-customer-plan.md):
      - tenant_ctx.routing_hints → override default_route
      - tenant_ctx.lead_requirements → override required/optional (handled
        in compute_profile_missing_info where schema is resolved)
      - tenant_ctx.services filter → restrict which profiles are active

    The seam is intentionally kept at the profile level (not schema level) so
    that compute_profile_missing_info can handle per-field tenant schema
    overrides independently.
    """
    if tenant_ctx is None or not tenant_ctx.context_available:
        return profile

    # Routing hint override: if tenant has a routing_hint for this service_type,
    # apply it by reconstructing the profile with the new default_route.
    routing_hints: dict = getattr(tenant_ctx, "routing_hints", {}) or {}
    new_route = routing_hints.get(profile.service_type)
    if new_route and new_route != profile.default_route:
        # dataclasses.replace is not available for frozen DCs in 3.10+, use manual rebuild
        import dataclasses
        return dataclasses.replace(profile, default_route=new_route)

    return profile
