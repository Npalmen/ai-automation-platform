"""Service context detection.

Detects the SERVICE CONTEXT of a customer message — what kind of interaction
the customer is requesting (new installation, add-on to existing system,
repair/fault, etc.).

Used by select_profile() to refine profile selection beyond the raw lead_type.
This enables the system to distinguish e.g. "add battery to existing solar"
from "install new solar panels" even when both contain solar-related keywords.

Public API:
    detect_service_context(text: str) -> ServiceContext
"""
from __future__ import annotations

from typing import Literal

ServiceContext = Literal[
    "new_installation",
    "add_on_existing",
    "repair_or_fault",
    "service_or_maintenance",
    "urgent_issue",
    "unclear_followup",
    "price_shopping",
]

# Signals checked in specificity order — first match wins.
# urgent_issue must come BEFORE repair_or_fault to avoid false-negative safety cases.
_CONTEXT_SIGNALS: list[tuple[ServiceContext, list[str]]] = [
    ("urgent_issue", [
        "akut", "asap", "snarast möjligt", "idag om möjligt", "hjälp idag",
        "brinner", "brand", "vattenläcka", "översvämning",
        "barn hemma", "vi har barn", "omedelbart",
        # Electrical safety signals
        "luktar bränt", "bränt lukt", "bränt", "gnistor", "gnistrar",
        "livsfarligt", "brandrisk", "elstöt",
    ]),
    ("repair_or_fault", [
        "fungerar inte", "fungerar ej", "slutat fungera", "slutar fungera",
        "inte längre", "laddar inte", "laddar inte längre", "laddar inte alls",
        "trasig", "trasigt", "trasiga", "gick sönder", "gick av",
        "fel på", "felkod", "fel-led", "blinkar rött", "blinkar fel",
        "ingen produktion", "inte producerar", "producerar inte",
        "producerar ej", "produktionen har minskat",
        "inga solceller producerar", "producerar ingenting",
        "strömmen borta", "strömbortfall", "ingen ström",
        "säkringen löser", "säkring slår", "jordfelsbrytaren löser",
        "larm", "varningssignal", "varnar",
        # Solar low-production
        "producerar dåligt", "dålig produktion", "lägre produktion",
        "mycket lägre", "nästan ingenting", "produktion minskat",
        # VVS faults
        "läcker", "droppande", "vattenskada", "stopp i", "igensatt",
        "blockerat avlopp", "avloppsstopp",
    ]),
    ("unclear_followup", [
        "kolla läget", "följde upp", "hörde inte", "inte hört något",
        "inte hört ifrån er", "hör av sig", "tänkte bara kolla",
        "undrar om ni", "som jag nämnde", "tidigare mejl", "förra veckan",
        "återkoppling", "uppdatering på",
        # Dissatisfied/complaint signals
        "missnöjd", "inte nöjd", "ingen har ringt", "ingen ringde",
        "inte hört av er", "väntat länge",
        # Vague callback
        "ring mig", "kan du ringa", "ring när du kan", "ring oss",
        "kontakta mig", "kontakta oss",
    ]),
    ("price_shopping", [
        "billigast", "billigaste alternativet", "jämföra priser",
        "tre offerter", "tre anbud", "flera offerter",
        "vad tar ni betalt", "vad kostar det exakt", "letar efter billigaste",
    ]),
    ("add_on_existing", [
        # Explicit "we already have X" signals
        "vi har solceller", "har solceller", "vi har solar",
        "befintlig solcell", "befintliga solceller",
        "befintlig anläggning", "befintlig installation",
        "redan installerat", "redan har solceller",
        "10 kwp", "8 kwp", "6 kwp",   # system size mentions = has a system
        # Add-on intent signals
        "komplettera med", "komplettering med", "lägga till",
        "utöka med", "addera batteri", "batteri till",
        # EV charger add-on
        "har laddbox", "har en laddbox", "befintlig laddbox",
        # Returning customer signals
        "ni installerade", "installerade hos oss", "installerade vår",
        "befintlig kund", "återkommande kund",
        # Inverter/solar service signals (existing system referenced)
        "växelriktaren", "inverterfelet",
    ]),
    ("service_or_maintenance", [
        "servicebesök", "serviceavtal", "underhåll", "inspektion",
        "kontrollera", "rengöring", "besiktning", "städning",
        "service på", "ta hand om",
    ]),
]


def detect_service_context(text: str) -> ServiceContext:
    """Return the most likely service context for *text*.

    Checks context signals in specificity order. Returns "new_installation"
    as the default when no signal matches.

    Args:
        text: Combined subject + body text (lowercase recommended but not required).

    Returns:
        A ServiceContext literal string.
    """
    lower = text.lower()
    for context, signals in _CONTEXT_SIGNALS:
        if any(sig in lower for sig in signals):
            return context
    return "new_installation"
