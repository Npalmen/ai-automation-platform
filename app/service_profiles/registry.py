"""Service Profile Registry.

Defines all first-version service profiles and exposes:
    get_profile(service_type)   → ServiceProfile | None
    list_profiles()             → list[ServiceProfile]

Profiles are grouped by family:
  installation_service  — ev_charger_installation, solar_installation,
                          battery_storage, electrical_fault, inverter_support,
                          electrical_panel
  generic_business      — generic_lead, generic_support,
                          invoice_generic, debt_collection_risk
"""
from __future__ import annotations

from app.service_profiles.models import ServiceProfile

# ── installation_service family ───────────────────────────────────────────────

_EV_CHARGER = ServiceProfile(
    service_type="ev_charger_installation",
    family="installation_service",
    keywords=(
        "laddbox", "laddstolpe", "elbilsladdning", "wallbox",
        "laddning av elbil", "hemmaladdning", "laddstation",
        "laddpunkt", "ev charger",
    ),
    required_fields=(
        "contact_name", "phone_or_email", "address",
        "property_type", "main_fuse", "desired_location",
    ),
    optional_fields=(
        "charger_count", "preferred_brand", "parking_type", "installation_timeline",
    ),
    risk_flags=(),
    default_route="sales",
    missing_info_action="ask_questions",
    complete_action="create_offer_draft",
    high_risk_action="manual_review",
    follow_up_intro=(
        "För att kunna ta fram rätt underlag för laddboxinstallationen behöver vi gärna:"
    ),
    follow_up_questions={
        "contact_name":        "Ditt namn",
        "phone_or_email":      "Telefonnummer",
        "address":             "Adress där laddboxen ska installeras",
        "property_type":       "Fastighetstyp (villa, BRF eller företag)",
        "main_fuse":           "Huvudsäkringens storlek om du vet den (ampere)",
        "desired_location":    "Önskad placering av laddboxen",
        "charger_count":       "Antal laddpunkter du behöver",
        "preferred_brand":     "Har du något föredraget märke? (Zaptec, Easee, m.fl.)",
        "parking_type":        "Parkeringstyp (garage, carport, utomhus)",
        "installation_timeline": "När vill du komma igång ungefär?",
    },
)

_SOLAR = ServiceProfile(
    service_type="solar_installation",
    family="installation_service",
    keywords=(
        "solcell", "solpanel", "solenergi", "solar", "solkraft",
        "solcellsinstallation", "solcellsanläggning", "pv",
    ),
    required_fields=(
        "contact_name", "phone_or_email", "address",
        "property_type", "annual_consumption", "roof_type", "main_fuse",
    ),
    optional_fields=(
        "battery_interest", "roof_angle", "current_electricity_cost",
        "installation_timeline",
    ),
    risk_flags=(),
    default_route="sales",
    missing_info_action="ask_questions",
    complete_action="create_offer_draft",
    high_risk_action="manual_review",
    follow_up_intro=(
        "För att kunna bedöma solcellsförutsättningarna behöver vi gärna:"
    ),
    follow_up_questions={
        "contact_name":            "Ditt namn",
        "phone_or_email":          "Telefonnummer",
        "address":                 "Adress",
        "property_type":           "Fastighetstyp (villa, BRF, lantbruk m.m.)",
        "annual_consumption":      "Ungefärlig årsförbrukning (kWh/år)",
        "roof_type":               "Taktyp eller bild på taket (betong, plåt, tegel m.m.)",
        "main_fuse":               "Huvudsäkringens storlek om du vet den (ampere)",
        "battery_interest":        "Är du intresserad av batterilager?",
        "roof_angle":              "Takvinkel (ungefärlig lutning i grader)",
        "current_electricity_cost": "Nuvarande elkostnad (kr/kWh eller elräkning per år)",
        "installation_timeline":   "Önskad tidsplan",
    },
)

_BATTERY = ServiceProfile(
    service_type="battery_storage",
    family="installation_service",
    keywords=(
        "batteri", "batterilager", "energilager", "laddlager",
        "powerwall", "husbatteri",
    ),
    required_fields=(
        "contact_name", "phone_or_email", "address",
        "property_type", "solar_exists", "main_fuse",
    ),
    optional_fields=(
        "battery_capacity_preference", "current_electricity_cost",
        "installation_timeline",
    ),
    risk_flags=(),
    default_route="sales",
    missing_info_action="ask_questions",
    complete_action="create_offer_draft",
    high_risk_action="manual_review",
    follow_up_intro=(
        "För att kunna bedöma batterilagerlösningen behöver vi gärna:"
    ),
    follow_up_questions={
        "contact_name":               "Ditt namn",
        "phone_or_email":             "Telefonnummer",
        "address":                    "Adress",
        "property_type":              "Fastighetstyp",
        "solar_exists":               "Har du redan solceller? (ange gärna effekt/modell)",
        "main_fuse":                  "Huvudsäkringens storlek (ampere)",
        "battery_capacity_preference": "Önskad batterikapacitet (kWh)",
        "installation_timeline":      "Önskad tidsplan",
    },
)

_ELECTRICAL_FAULT = ServiceProfile(
    service_type="electrical_fault",
    family="installation_service",
    keywords=(
        "jordfelsbrytare", "säkring löser", "säkring slår",
        "felsökning", "kortslutning", "elfel", "elstörning",
    ),
    required_fields=(
        "contact_name", "phone_or_email", "address",
        "issue_description", "safety_risk",
    ),
    optional_fields=("error_code",),
    risk_flags=(
        "luktar bränt", "bränt lukt", "gnistor", "gnistrar",
        "elstöt", "brandrisk", "kortslutning",
    ),
    default_route="support",
    missing_info_action="ask_questions",
    complete_action="create_task",
    high_risk_action="manual_review",
    follow_up_intro=(
        "För att kunna hjälpa dig snabbare behöver vi gärna:"
    ),
    follow_up_questions={
        "contact_name":    "Ditt namn",
        "phone_or_email":  "Telefonnummer",
        "address":         "Adress",
        "issue_description": "Vad händer och när uppstod felet?",
        "safety_risk":     "Luktar det bränt, gnistrar det eller finns annan akut risk?",
        "error_code":      "Finns det en felkod eller kan du bifoga en bild?",
    },
)

_INVERTER_SUPPORT = ServiceProfile(
    service_type="inverter_support",
    family="installation_service",
    keywords=(
        "växelriktare", "inverter", "invertern",
    ),
    required_fields=(
        "contact_name", "phone_or_email", "address",
        "inverter_model_or_error_code", "issue_description", "production_status",
    ),
    optional_fields=("installation_timeline",),
    risk_flags=(),
    default_route="support",
    missing_info_action="ask_questions",
    complete_action="create_task",
    high_risk_action="manual_review",
    follow_up_intro=(
        "För att hjälpa dig med växelriktarproblemet behöver vi:"
    ),
    follow_up_questions={
        "contact_name":                "Ditt namn",
        "phone_or_email":              "Telefonnummer",
        "address":                     "Adress",
        "inverter_model_or_error_code": "Växelriktarens modell och eventuell felkod",
        "issue_description":           "Beskriv vad som händer",
        "production_status":           "Producerar solcellerna alls just nu? (ja/nej/lite)",
        "installation_timeline":       "Önskad åtgärdstid",
    },
)

_ELECTRICAL_PANEL = ServiceProfile(
    service_type="electrical_panel",
    family="installation_service",
    keywords=(
        "elcentral", "proppskåp", "säkringsskåp", "gruppcent", "eltavla",
    ),
    required_fields=(
        "contact_name", "phone_or_email", "address",
        "property_type", "main_fuse", "current_panel_age",
    ),
    optional_fields=("installation_timeline",),
    risk_flags=(
        "luktar bränt", "bränt lukt", "gnistor", "gnistrar", "kortslutning",
    ),
    default_route="sales",
    missing_info_action="ask_questions",
    complete_action="create_offer_draft",
    high_risk_action="manual_review",
    follow_up_intro=(
        "För att ta fram rätt förslag för elcentralen behöver vi:"
    ),
    follow_up_questions={
        "contact_name":    "Ditt namn",
        "phone_or_email":  "Telefonnummer",
        "address":         "Adress",
        "property_type":   "Fastighetstyp",
        "main_fuse":       "Nuvarande huvudsäkring (ampere)",
        "current_panel_age": "Hur gammal är elcentralen och hur ser den ut idag?",
        "installation_timeline": "Önskad tidsplan",
    },
)

# ── generic_business family ───────────────────────────────────────────────────

_GENERIC_LEAD = ServiceProfile(
    service_type="generic_lead",
    family="generic_business",
    keywords=(),
    required_fields=(
        "contact_name", "phone_or_email", "address", "service_type",
    ),
    optional_fields=("notes", "installation_timeline"),
    risk_flags=(),
    default_route="sales",
    missing_info_action="ask_questions",
    complete_action="create_offer_draft",
    high_risk_action="manual_review",
    follow_up_intro=(
        "För att kunna hjälpa dig behöver vi lite mer information:"
    ),
    follow_up_questions={
        "contact_name":        "Ditt namn",
        "phone_or_email":      "Telefonnummer eller e-postadress",
        "address":             "Adress (gatuadress och ort)",
        "service_type":        "Vad vill du ha hjälp med?",
        "notes":               "Övrig information",
        "installation_timeline": "Önskad tidsplan",
    },
)

_GENERIC_SUPPORT = ServiceProfile(
    service_type="generic_support",
    family="generic_business",
    keywords=("support", "problem", "fråga", "hjälp med"),
    required_fields=(
        "contact_name", "phone_or_email", "issue_description",
    ),
    optional_fields=("address",),
    risk_flags=(),
    default_route="support",
    missing_info_action="ask_questions",
    complete_action="create_task",
    high_risk_action="manual_review",
    follow_up_intro=(
        "För att kunna hjälpa dig snabbare behöver vi:"
    ),
    follow_up_questions={
        "contact_name":      "Ditt namn",
        "phone_or_email":    "Telefonnummer eller e-postadress",
        "issue_description": "Beskriv problemet och när det uppstod",
        "address":           "Adress (om relevant)",
    },
)

_INVOICE_GENERIC = ServiceProfile(
    service_type="invoice_generic",
    family="generic_business",
    keywords=("faktura", "invoice", "payment request"),
    required_fields=(
        "invoice_number_or_reference", "amount", "supplier_or_customer", "due_date",
    ),
    optional_fields=("ocr_number", "vat"),
    risk_flags=(),
    default_route="invoice",
    missing_info_action="manual_review",
    complete_action="auto_process",
    high_risk_action="manual_review",
    follow_up_intro=(
        "För att kunna hantera fakturan korrekt behöver vi:"
    ),
    follow_up_questions={
        "invoice_number_or_reference": "Fakturanummer eller referens",
        "amount":                      "Belopp",
        "supplier_or_customer":        "Leverantör eller kund",
        "due_date":                    "Förfallodatum",
        "ocr_number":                  "OCR-nummer (för betalning)",
        "vat":                         "Momssats om det inte framgår",
    },
)

_DEBT_COLLECTION = ServiceProfile(
    service_type="debt_collection_risk",
    family="generic_business",
    keywords=(
        "inkasso", "betalningskrav", "kravbrev", "kronofogden",
        "förfallen skuld", "betalningsanmärkning",
    ),
    required_fields=("sender", "reference", "amount", "deadline"),
    optional_fields=("legal_threat",),
    risk_flags=(
        "inkasso", "kravbrev", "kronofogden", "betalningskrav",
        "betalningsanmärkning", "förfallen skuld",
    ),
    default_route="manual_review",
    missing_info_action="manual_review",
    complete_action="manual_review",
    high_risk_action="manual_review",
    follow_up_intro=(
        "Detta ärende kräver manuell hantering och ska inte automatiseras."
    ),
    follow_up_questions={
        "sender":      "Avsändare (inkassobolag eller fordringsägare)",
        "reference":   "Ärendenummer eller referens",
        "amount":      "Belopp inkl. eventuell ränta och avgifter",
        "deadline":    "Senaste betalningsdatum",
        "legal_threat": "Finns uppgift om rättslig åtgärd?",
    },
)

# ── Registry ──────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, ServiceProfile] = {
    p.service_type: p
    for p in [
        _EV_CHARGER,
        _SOLAR,
        _BATTERY,
        _ELECTRICAL_FAULT,
        _INVERTER_SUPPORT,
        _ELECTRICAL_PANEL,
        _GENERIC_LEAD,
        _GENERIC_SUPPORT,
        _INVOICE_GENERIC,
        _DEBT_COLLECTION,
    ]
}


def get_profile(service_type: str) -> ServiceProfile | None:
    """Return the ServiceProfile for *service_type*, or None if not found."""
    return _REGISTRY.get(service_type)


def list_profiles() -> list[ServiceProfile]:
    """Return all registered ServiceProfile objects."""
    return list(_REGISTRY.values())
