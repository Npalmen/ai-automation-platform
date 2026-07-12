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
    follow_up_intro="För att ta fram rätt underlag för laddboxen behöver vi:",
    reply_opener="Vi installerar laddboxar — kul att du valt elbil!",
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
    follow_up_intro="För att bedöma förutsättningarna behöver vi:",
    reply_opener="Kul att du är intresserad av solceller!",
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
    follow_up_intro="För att ta fram rätt batterilösning behöver vi:",
    reply_opener="Absolut, ett batterilager till befintlig solcellsanläggning kan vi ordna.",
    follow_up_questions={
        "contact_name":               "Ditt namn",
        "phone_or_email":             "Telefonnummer",
        "address":                    "Adress",
        "property_type":              "Fastighetstyp",
        "solar_exists":               "Vilket märke/modell är din befintliga solcellsanläggning? (effekt i kWp om du vet)",
        "main_fuse":                  "Huvudsäkringens storlek (ampere)",
        "battery_capacity_preference": "Önskad batterikapacitet i kWh, eller ungefärlig dagsförbrukning",
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
    follow_up_intro="För att hjälpa dig snabbt behöver vi:",
    reply_opener="Vi hjälper till med elfelsökning.",
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
    follow_up_intro="För att titta på växelriktarproblemet behöver vi:",
    reply_opener="Vi tittar gärna på växelriktarproblemet.",
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
    follow_up_intro="För att ta fram rätt förslag för elcentralen behöver vi:",
    reply_opener="Elcentralsbyte — det fixar vi.",
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
    follow_up_intro="Skicka gärna lite mer info så kan vi hjälpa dig:",
    reply_opener="",
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
    follow_up_intro="Skicka gärna lite mer info så kan vi hjälpa dig:",
    reply_opener="",
    follow_up_questions={
        "contact_name":      "Ditt namn",
        "phone_or_email":    "Telefonnummer eller e-postadress",
        "issue_description": "Beskriv problemet och när det uppstod",
        "address":           "Adress (om relevant)",
    },
)

_EV_CHARGER_FAULT = ServiceProfile(
    service_type="ev_charger_fault",
    family="installation_service",
    keywords=(
        "laddboxen fungerar inte", "laddboxen laddar inte",
        "laddboxen startar inte", "laddbox slutat",
    ),
    required_fields=(
        "contact_name", "phone_or_email", "address",
        "issue_description",
    ),
    optional_fields=(
        "charger_model_or_brand", "when_started", "error_code",
    ),
    risk_flags=(),
    default_route="support",
    missing_info_action="ask_questions",
    complete_action="create_task",
    high_risk_action="manual_review",
    follow_up_intro="Tråkigt att laddboxen strular — berätta lite mer så kollar vi:",
    reply_opener="Tråkigt att laddboxen strular — vi kollar upp det.",
    follow_up_questions={
        "contact_name":          "Ditt namn",
        "phone_or_email":        "Telefonnummer",
        "address":               "Adress där laddboxen är installerad",
        "issue_description":     "Vad händer när du försöker ladda?",
        "charger_model_or_brand": "Vilket märke/modell är laddboxen? (Zaptec, Easee, m.fl.)",
        "when_started":          "Sedan när fungerar det inte?",
        "error_code":            "Finns det en felkod eller blinkar någon lampa?",
    },
)

_VVS_SERVICE = ServiceProfile(
    service_type="vvs_service",
    family="installation_service",
    keywords=(
        "vattenläcka", "läcka", "rörmokar", "rörmokare", "vvs", "rörmokeri",
        "avlopp", "toalett", "badrum", "diskbänk", "kran", "rör läcker",
        "vatten", "droppande",
    ),
    required_fields=(
        "contact_name", "phone_or_email", "address",
        "issue_description",
    ),
    optional_fields=(
        "urgency_level", "water_shut_off",
    ),
    risk_flags=("översvämning", "vattenflöde", "akut läcka", "vattenskada"),
    default_route="support",
    missing_info_action="ask_questions",
    complete_action="create_task",
    high_risk_action="manual_review",
    follow_up_intro="Berätta lite mer, så ser vi hur snabbt vi kan komma:",
    reply_opener="VVS är ingen fara — vi hjälper till.",
    follow_up_questions={
        "contact_name":    "Ditt namn",
        "phone_or_email":  "Telefonnummer",
        "address":         "Adress",
        "issue_description": "Var läcker det och hur mycket? (t.ex. under diskbänk, droppande vs flödande)",
        "urgency_level":   "Är det akut, eller kan det vänta någon dag?",
        "water_shut_off":  "Har du stängt av vattnet? (om relevant)",
    },
)

_BUILDING_PROJECT = ServiceProfile(
    service_type="building_project",
    family="generic_business",
    keywords=(
        "förråd", "friggebod", "attefallsåtgärd", "snickare", "snickeri",
        "bygga", "byggarbete", "altan", "terrass", "carport", "pergola",
        "renovering", "ombyggnad", "tillbyggnad",
    ),
    required_fields=(
        "contact_name", "phone_or_email", "address",
        "issue_description",
    ),
    optional_fields=(
        "approximate_area", "installation_timeline",
    ),
    risk_flags=(),
    default_route="sales",
    missing_info_action="ask_questions",
    complete_action="create_offer_draft",
    high_risk_action="manual_review",
    follow_up_intro="Kul projekt — skicka gärna:",
    reply_opener="Kul projekt — vi tar gärna en titt!",
    follow_up_questions={
        "contact_name":      "Ditt namn",
        "phone_or_email":    "Telefonnummer",
        "address":           "Adress/plats för projektet",
        "issue_description": "Beskriv projektet kort (mått, material, önskemål)",
        "approximate_area":  "Ungefärlig yta (kvm) om relevant",
        "installation_timeline": "Ungefärlig tidplan — när vill du ha det klart?",
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
    follow_up_intro="För att hantera fakturan korrekt behöver vi:",
    reply_opener="",
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
    follow_up_intro="Detta ärende kräver manuell hantering och ska inte automatiseras.",
    reply_opener="",
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
        _EV_CHARGER_FAULT,
        _SOLAR,
        _BATTERY,
        _ELECTRICAL_FAULT,
        _INVERTER_SUPPORT,
        _ELECTRICAL_PANEL,
        _VVS_SERVICE,
        _BUILDING_PROJECT,
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
