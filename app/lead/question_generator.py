"""Question Generator.

Generates a customer-facing Swedish message asking for missing fields.
Triggered when completeness_score < 0.7.
"""
from __future__ import annotations

# Swedish question templates per field
_FIELD_QUESTIONS: dict[str, str] = {
    "address":                   "Adress (gatuadress och ort)",
    "roof_type":                  "Taktyp (t.ex. betongpannor, plåt, tegelpannor)",
    "annual_consumption":         "Ungefärlig årsförbrukning (kWh/år)",
    "installation_timeline":      "När vill du komma igång ungefär?",
    "battery_interest":           "Är du intresserad av batterilager?",
    "roof_angle":                 "Takvinkel (ungefärlig lutning i grader)",
    "current_electricity_cost":   "Nuvarande elkostnad (kr/kWh eller elräkning per år)",
    "solar_exists":               "Har du redan solceller installerade?",
    "battery_capacity_preference":"Önskad batterikapacitet (kWh)",
    "property_type":              "Fastighetstyp (villa, radhus, lägenhet, lokal m.m.)",
    "charger_count":              "Antal laddpunkter du behöver",
    "main_fuse":                  "Huvudsäkringens storlek (ampere)",
    "work_description":           "Vad vill du ha hjälp med? Beskriv gärna ditt ärende",
    "current_panel_age":          "Hur gammal är din elcentral ungefär?",
    "roof_material":              "Taktäckningsmaterial (t.ex. betong, plåt, shingel)",
    "approximate_area":           "Ungefärlig takyta (kvm)",
    "roof_condition":             "Takets nuvarande skick (t.ex. mossa, alger, sprickor)",
    "preferred_color":            "Önskad färg eller kulör",
    "moss_level":                 "Ungefärlig mängd mossa/lav (lite/måttlig/kraftig)",
    "previous_cleaning":          "Har taket tvättats tidigare, och i så fall när?",
    "preferred_brand":            "Har du något föredraget laddboxsmärke?",
    "parking_type":               "Parkeringstyp (garage, carport, utomhus)",
}

_COMPLETENESS_THRESHOLD = 0.7


def generate_question_message(missing_fields: list[str]) -> str | None:
    """Return a Swedish customer message asking for missing_fields, or None if list is empty."""
    if not missing_fields:
        return None

    questions = [
        f"• {_FIELD_QUESTIONS.get(f, f.replace('_', ' ').capitalize())}"
        for f in missing_fields
    ]
    body = "\n".join(questions)

    return (
        "För att kunna ta fram ett bra förslag behöver vi bara lite mer information:\n\n"
        f"{body}\n\n"
        "Svar räcker kort — så återkommer vi med nästa steg."
    )


def should_ask_questions(completeness_score: float) -> bool:
    return completeness_score < _COMPLETENESS_THRESHOLD
