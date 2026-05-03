"""Support Missing Info Engine.

Determines which fields are required/optional for a given ticket_type,
checks which are present in input_data/entities, and computes completeness_score.

Tenant-aware: support_requirements[ticket_type] overrides defaults.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.support.models import SupportMissingInfoResult

if TYPE_CHECKING:
    from app.support.tenant_context import TenantSupportContext


# ── Default schemas per ticket_type ──────────────────────────────────────────

_DEFAULT_SCHEMAS: dict[str, dict[str, list[str]]] = {
    "emergency": {
        "required": ["address", "phone", "issue_description"],
        "optional": ["email", "photos"],
    },
    "issue": {
        "required": ["address", "issue_description"],
        "optional": ["product_model", "error_code", "photos", "when_started"],
    },
    "warranty": {
        "required": ["address", "installation_date", "issue_description"],
        "optional": ["invoice_number", "photos", "product_model"],
    },
    "invoice_question": {
        "required": ["invoice_number", "issue_description"],
        "optional": ["customer_number", "email"],
    },
    "scheduling": {
        "required": ["address", "preferred_time", "issue_description"],
        "optional": ["phone", "email"],
    },
    "complaint": {
        "required": ["issue_description"],
        "optional": ["address", "invoice_number", "email"],
    },
    "question": {
        "required": ["issue_description"],
        "optional": ["address", "email"],
    },
    "other": {
        "required": ["issue_description"],
        "optional": ["address", "email", "phone"],
    },
}


# ── Field presence detection ──────────────────────────────────────────────────

_FIELD_KEYWORDS: dict[str, list[str]] = {
    "address": [
        "adress", "gatuadress", "gatan", "vägen", "bostadsadress",
        "postnummer", "stad", "ort", "hemma i",
    ],
    "phone": [
        "telefon", "telefonnummer", "mobil", "mobilnummer", "nå mig på",
        "ring mig", "nummer är",
    ],
    "email": [
        "email", "e-post", "epost", "mejl", "mailadress",
    ],
    "issue_description": [
        "problem", "fel", "fungerar inte", "trasig", "fråga",
        "klagomål", "missnöjd", "ärende", "vill ha hjälp", "behöver",
        "hjälp med",
    ],
    "product_model": [
        "modell", "typ", "fabrikat", "artikel", "produkten heter",
        "serienummer", "produkt", "enhet",
    ],
    "error_code": [
        "felkod", "error", "kod", "larmkod", "larm visar", "display visar",
    ],
    "photos": [
        "bild", "foto", "bilder", "foton", "bifogat", "se bild",
    ],
    "when_started": [
        "sedan", "börjat", "uppstod", "hände", "har haft",
        "för hur länge", "när började",
    ],
    "installation_date": [
        "installerades", "installationsdatum", "monterades", "driftsattes",
        "datum för installation", "när ni installerade",
    ],
    "invoice_number": [
        "fakturanummer", "faktura nr", "fakturanr", "verifikationsnummer",
        "ordernummer",
    ],
    "customer_number": [
        "kundnummer", "kund nr", "kundnr",
    ],
    "preferred_time": [
        "tid", "datum", "när passar", "föredrar", "tisdag", "måndag",
        "onsdag", "torsdag", "fredag", "förmiddag", "eftermiddag",
        "vecka", "kan ni komma",
    ],
}

# Entity field mapping: entity key → field name
_ENTITY_FIELD_MAP: dict[str, str] = {
    "phone": "phone",
    "email": "email",
    "address": "address",
    "city": "address",
    "invoice_number": "invoice_number",
    "customer_number": "customer_number",
    "product_model": "product_model",
    "error_code": "error_code",
}


def _field_present(
    field: str,
    input_data: dict,
    entities: dict,
    text: str,
) -> bool:
    # Direct entity match
    ent_key = _ENTITY_FIELD_MAP.get(field)
    if ent_key and entities.get(ent_key):
        return True
    if entities.get(field):
        return True

    # Direct input_data key
    if input_data.get(field):
        return True

    # issue_description: long message body or explicit subject counts
    if field == "issue_description":
        body = input_data.get("message_text") or ""
        subj = input_data.get("subject") or ""
        return len(body.strip()) > 20 or len(subj.strip()) > 5

    # Keyword match in combined text
    kws = _FIELD_KEYWORDS.get(field) or []
    return any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in kws)


def compute_support_missing_info(
    ticket_type: str,
    input_data: dict,
    entities: dict | None = None,
    tenant_ctx: "TenantSupportContext | None" = None,
) -> SupportMissingInfoResult:
    """Compute which required/optional fields are present and return completeness score."""
    entities = entities or {}
    subject = (input_data.get("subject") or "").lower()
    body = (input_data.get("message_text") or "").lower()
    text = f"{subject} {body}"

    # Select schema — tenant override wins
    schema_source = "default"
    tenant_ctx_used = False
    ctx_sources: list[str] = []

    if tenant_ctx and tenant_ctx.context_available:
        schema = tenant_ctx.schema_for(ticket_type)
        if schema:
            required = list(schema.get("required") or [])
            optional = list(schema.get("optional") or [])
            schema_source = "tenant"
            tenant_ctx_used = True
            ctx_sources = list(tenant_ctx.sources_used)
        else:
            default = _DEFAULT_SCHEMAS.get(ticket_type, _DEFAULT_SCHEMAS["other"])
            required = list(default["required"])
            optional = list(default["optional"])
    else:
        default = _DEFAULT_SCHEMAS.get(ticket_type, _DEFAULT_SCHEMAS["other"])
        required = list(default["required"])
        optional = list(default["optional"])

    # Detect which fields are present
    present: list[str] = []
    missing: list[str] = []
    for f in required:
        if _field_present(f, input_data, entities, text):
            present.append(f)
        else:
            missing.append(f)

    # Completeness = present required / total required
    total_required = len(required)
    completeness = len(present) / total_required if total_required > 0 else 1.0

    return SupportMissingInfoResult(
        required_fields=required,
        present_fields=present,
        missing_fields=missing,
        optional_fields=optional,
        completeness_score=round(completeness, 3),
        schema_source=schema_source,
        tenant_context_used=tenant_ctx_used,
        context_sources=ctx_sources,
    )
