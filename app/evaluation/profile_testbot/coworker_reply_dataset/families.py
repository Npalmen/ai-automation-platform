"""Coworker reply scenario family templates."""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.profile_testbot.coworker_reply_dataset.constants import COWORKER_FAMILIES


@dataclass(frozen=True)
class CoworkerFamilyCell:
    subject: str
    message_text: str
    service_type: str
    business_intent: str
    thread_state: str
    language: str
    expected_send: str
    known_entities: tuple[str, ...]
    forbid_name: bool
    forbid_phone: bool
    required_markers: tuple[str, ...]
    forbidden_markers: tuple[str, ...]


_FAMILY_TEMPLATES: dict[str, tuple[CoworkerFamilyCell, ...]] = {
    "solar_installation_new": (
        CoworkerFamilyCell("Offert solceller Uppsala", "Hej, vi vill installera solceller på villan i Uppsala.", "solar_installation", "lead", "new_thread", "sv", "send_after_approval", (), False, True, ("sol",), ("telefonnummer",)),
        CoworkerFamilyCell("Solcellsinstallation radhus", "Hej, intresserad av solceller till radhus i Enköping.", "solar_installation", "lead", "new_thread", "sv", "send_after_approval", ("city",), False, True, ("sol", "tak"), ()),
        CoworkerFamilyCell("Solar quote", "Hi, we need a solar quote for our house in Uppsala.", "solar_installation", "lead", "new_thread", "en", "send_after_approval", (), False, True, ("solar",), ()),
        CoworkerFamilyCell("Solceller BRF", "Hej, vi undersöker solceller för vår BRF i Uppsala.", "solar_installation", "lead", "new_thread", "sv", "send_after_approval", (), False, True, ("sol",), ()),
        CoworkerFamilyCell("Solceller tak", "Vi vill veta förutsättningar för solceller på plåttak.", "solar_installation", "lead", "new_thread", "sv", "send_after_approval", ("property_type",), False, True, ("sol",), ()),
        CoworkerFamilyCell("Solceller förbrukning", "Hej, vår årsförbrukning är cirka 18000 kWh och vi vill ha solceller.", "solar_installation", "lead", "new_thread", "sv", "send_after_approval", ("annual_consumption",), True, True, ("sol",), ("ditt namn",)),
        CoworkerFamilyCell("Solceller batteri intresse", "Hej, vi vill ha solceller och funderar på batteri i Uppsala.", "solar_installation", "lead", "new_thread", "sv", "send_after_approval", ("city",), False, True, ("sol",), ()),
        CoworkerFamilyCell("Solceller fortsättning", "Hej igen, följer upp vår förfrågan om solceller.", "solar_installation", "lead", "continuation", "sv", "send_after_approval", ("city",), True, True, ("uppföljning",), ("ny förfrågan",)),
    ),
    "battery_installation_new": (
        CoworkerFamilyCell("Batterilager villa", "Hej, vi vill installera batterilager i villan i Uppsala.", "battery_storage", "lead", "new_thread", "sv", "send_after_approval", (), False, True, ("batteri",), ()),
        CoworkerFamilyCell("Batteri befintlig sol", "Vi har solceller sedan 2021 och vill komplettera med batteri.", "battery_storage", "lead", "new_thread", "sv", "send_after_approval", ("existing_solar_system",), True, True, ("batteri",), ("taktyp",)),
        CoworkerFamilyCell("Battery add-on", "We have solar and want a 10 kWh battery in Uppsala.", "battery_storage", "lead", "new_thread", "en", "send_after_approval", ("existing_solar_system",), True, True, ("battery",), ()),
        CoworkerFamilyCell("Batteri växelriktare", "Har solceller och undrar om vår växelriktare klarar batteri.", "battery_storage", "lead", "new_thread", "sv", "send_after_approval", (), False, True, ("batteri", "växelrikt"), ()),
        CoworkerFamilyCell("Batteri syfte", "Vi vill ha batteri främst för egenförbrukning i Uppsala.", "battery_storage", "lead", "new_thread", "sv", "send_after_approval", ("city",), False, True, ("batteri",), ()),
        CoworkerFamilyCell("Batteri känd adress", "Vi har solceller på Storgatan 4 Uppsala och vill ha batteri.", "battery_storage", "lead", "new_thread", "sv", "send_after_approval", ("address", "existing_solar_system"), True, True, ("batteri",), ("adress",)),
        CoworkerFamilyCell("Batteri uppföljning", "Tack, här kommer info om befintlig anläggning 8 kWp.", "battery_storage", "lead", "continuation", "sv", "send_after_approval", ("existing_solar_system",), True, True, ("kompletter", "batteri"), ()),
        CoworkerFamilyCell("Batteri offert", "Kan ni titta på batterilager till vår villa?", "battery_storage", "lead", "new_thread", "sv", "send_after_approval", (), False, True, ("batteri",), ()),
    ),
}

# Fill remaining families with compact deterministic variants
def _support_cells() -> tuple[CoworkerFamilyCell, ...]:
    base = "Hej, vår {system} fungerar dåligt sedan {when}."
    return tuple(
        CoworkerFamilyCell(
            f"Support {i}",
            base.format(system=("solceller", "laddbox", "växelriktare")[i % 3], when=("igår", "förra veckan", "en månad")[i % 3]),
            ("solar_service", "ev_charger_fault", "solar_service")[i % 3],
            "support_status",
            ("new_thread", "continuation")[i % 2],
            "sv",
            "send_after_approval",
            ("customer_name",) if i % 2 else (),
            True,
            True,
            ("befintlig", "fel"),
            (),
        )
        for i in range(8)
    )


def _simple_family(
    family: str,
    *,
    service_type: str,
    intent: str,
    marker_sv: str,
    marker_en: str,
    subjects: tuple[str, ...],
) -> tuple[CoworkerFamilyCell, ...]:
    cells: list[CoworkerFamilyCell] = []
    for i in range(8):
        language = "en" if i % 4 == 0 else "sv"
        if language == "en":
            if marker_en == "solar":
                message_text = "Hi, we are interested in solar panels for our home in Uppsala."
            elif marker_en == "battery":
                message_text = "Hi, we are interested in battery storage for our home in Uppsala."
            elif marker_en == "charger":
                message_text = "Hi, we are interested in an EV charger for our home in Uppsala."
            elif marker_en == "consultation":
                message_text = "Hi, we would like advice on solar and battery options for our villa in Uppsala."
            else:
                message_text = f"Hi, we are interested in {marker_en} for our home in Uppsala."
            required_markers = (marker_en,)
        else:
            if marker_sv == "sol":
                variants = (
                    "Hej, vi vill ha offert på solceller till villan i Uppsala.",
                    "Hej, vi undersöker solceller för radhus i Enköping.",
                    "Vi vill veta förutsättningarna för solceller på plåttak i Uppsala.",
                    "Hej, vår årsförbrukning är cirka 18000 kWh och vi vill ha solceller.",
                    "Hej, vi vill ha solceller och funderar på batteri i Uppsala.",
                    "Hej igen, följer upp vår förfrågan om solceller i Uppsala.",
                    "Hej, kan ni ge en indikation på solceller för vår villa i Enköping?",
                    "Hej, vi planerar solceller på taket i Uppsala och vill ha en offert.",
                )
            elif marker_sv == "batteri":
                variants = (
                    "Hej, vi vill installera batterilager i villan i Uppsala.",
                    "Vi har solceller sedan 2021 och vill komplettera med batteri.",
                    "Hej, har solceller och undrar om vår växelriktare klarar batteri.",
                    "Vi vill ha batteri främst för egenförbrukning i Uppsala.",
                    "Vi har solceller på Storgatan 4 Uppsala och vill ha batteri.",
                    "Tack, här kommer info om befintlig anläggning 8 kWp.",
                    "Kan ni titta på batterilager till vår villa i Enköping?",
                    "Hej, vi funderar på batteri till befintliga solceller i Uppsala.",
                )
            elif marker_sv == "laddbox":
                variants = (
                    "Hej, vi vill ha laddbox installerad i villan i Uppsala.",
                    "Hej, intresserad av laddbox till villa i Enköping.",
                    "Vi behöver offert på laddbox med lastbalansering i Uppsala.",
                    "Hej, vi har huvudsäkring 25A och vill installera laddbox.",
                    "Kan ni installera laddbox i carport i Uppsala?",
                    "Hej igen, följer upp vår förfrågan om laddbox.",
                    "Vi vill ha två laddpunkter till villan i Enköping.",
                    "Hej, vi söker offert på laddbox till radhus i Uppsala.",
                )
            elif marker_sv == "konsultation":
                variants = (
                    "Hej, vi funderar på solceller och batteri men vet inte vad som passar vår villa.",
                    "Kan ni ge råd om solceller kontra batteri för vår förbrukning?",
                    "Hej, vi vill ha en genomgång av möjligheterna för energilagring i Uppsala.",
                    "Vi behöver hjälp att bedöma om laddbox eller solceller bör prioriteras.",
                    "Hej, vi planerar renovering och vill veta vad som är rimligt för taket.",
                    "Kan ni boka ett kort samtal om sol, batteri och laddning?",
                    "Hej, vi vill ha en översiktlig rådgivning för vår villa i Enköping.",
                    "Vi undrar vilken lösning som ger bäst nytta för vår årsförbrukning.",
                )
            else:
                variants = tuple(
                    f"Hej, vi vill ha hjälp med {marker_sv} i Uppsala." for _ in range(8)
                )
            message_text = variants[i % len(variants)]
            required_markers = (marker_sv,)
        cells.append(
            CoworkerFamilyCell(
                subjects[i % len(subjects)],
                message_text,
                service_type,
                intent,
                ("new_thread", "continuation")[i % 2],
                language,
                "send_after_approval" if i % 5 else "draft_for_approval",
                ("city",) if i % 3 == 0 else (),
                i % 2 == 0,
                True,
                required_markers,
                ("pris", "bokad"),
            )
        )
    return tuple(cells)


for family in COWORKER_FAMILIES:
    if family in _FAMILY_TEMPLATES:
        continue
    if family in {"existing_support_symptom", "existing_support_followup"}:
        _FAMILY_TEMPLATES[family] = _support_cells()
    elif family == "ev_charger_new":
        _FAMILY_TEMPLATES[family] = _simple_family(
            family, service_type="ev_charger_installation", intent="lead", marker_sv="laddbox", marker_en="charger",
            subjects=("Laddbox offert", "Installation laddbox", "Laddbox villa"),
        )
    elif family == "ev_charger_known_facts":
        _FAMILY_TEMPLATES[family] = tuple(
            CoworkerFamilyCell(
                "Laddbox känd info",
                "Vi vill ha laddbox. Adress Storgatan 2 Uppsala, villa, huvudsäkring 25A.",
                "ev_charger_installation",
                "lead",
                "new_thread",
                "sv",
                "send_after_approval",
                ("address", "property_type", "main_fuse"),
                True,
                True,
                ("laddbox",),
                ("huvudsäkring", "fastighetstyp"),
            )
            for _ in range(8)
        )
    elif family == "solar_battery_combined":
        _FAMILY_TEMPLATES[family] = tuple(
            CoworkerFamilyCell(
                ("Sol och batteri", "Solceller med batteri", "Sol+batteri offert")[i % 3],
                (
                    "Hej, vi vill installera både solceller och batteri i villan i Uppsala.",
                    "Hej, vi har solceller och vill komplettera med batterilager i Enköping.",
                    "Hi, we want solar panels and battery storage for our house in Uppsala.",
                    "Hej, vi undersöker solceller tillsammans med batteri för vår villa.",
                    "Vi vill ha offert på solceller och batteri till radhus i Uppsala.",
                    "Hej, vi vill ha offert på både solceller och batteri till villan i Uppsala.",
                    "Hej, vår årsförbrukning är 20000 kWh och vi vill ha sol och batteri i Uppsala.",
                    "Kan ni ge en indikation på solceller med batterilager i Enköping?",
                )[i],
                "solar_installation",
                "lead",
                "new_thread",
                "en" if i % 4 == 2 else "sv",
                "send_after_approval" if i % 5 else "draft_for_approval",
                ("city",) if i % 3 == 0 else (),
                i % 2 == 0,
                True,
                ("sol", "batteri") if i != 2 else ("solar", "battery"),
                ("pris", "bokad"),
            )
            for i in range(8)
        )
    elif family == "job_status_request":
        _FAMILY_TEMPLATES[family] = tuple(
            CoworkerFamilyCell(
                "Status på ärende",
                f"Hej, vad är status på vårt ärende {1000+i}?",
                "generic_support",
                "support_status",
                "continuation",
                "sv",
                "send_after_approval",
                ("customer_name",),
                True,
                True,
                ("ärende",),
                ("solcellsinstallation",),
            )
            for i in range(8)
        )
    elif family == "job_status_no_contact":
        _FAMILY_TEMPLATES[family] = tuple(
            CoworkerFamilyCell(
                "Status utan telefon",
                f"Kan ni uppdatera status på offertförfrågan {1042 + i}?",
                "generic_support",
                "support_status",
                "continuation",
                "sv",
                "send_after_approval",
                ("email",),
                True,
                True,
                ("ärende",),
                ("telefon",),
            )
            for i in range(8)
        )
    elif family == "complaint_warranty":
        _FAMILY_TEMPLATES[family] = tuple(
            CoworkerFamilyCell(
                "Reklamation installation",
                (
                    "Hej, vi vill reklamera ett problem med solcellsanläggningen som upptäcktes i går.",
                    "Hej, installationen från förra året har börjat ge felmeddelanden och vi vill få det åtgärdat.",
                    "Vi upptäckte ett problem med växelriktaren för två veckor sedan och behöver hjälp under garantin.",
                    "Hej, produktionen har sjunkit kraftigt sedan installationen och vi vill rapportera det.",
                    "Vi har sett varningar i appen nyligen och vill få en reklamation registrerad.",
                    "Hej, en panel verkar ha slutat fungera och vi vill få garantiärendet igång.",
                    "Problemet märktes för en vecka sedan och vi behöver support kring installationen.",
                    "Hej, vi vill få hjälp med ett fel som uppstod efter er installation i höstas.",
                )[i],
                "solar_service",
                "support_status",
                "new_thread",
                "sv",
                "send_after_approval",
                (),
                False,
                True,
                ("reklamation",),
                ("pris",),
            )
            for i in range(8)
        )
    elif family == "general_consultation":
        _langs = ("sv", "sv", "en", "sv", "sv", "en", "sv", "en")
        _FAMILY_TEMPLATES[family] = tuple(
            CoworkerFamilyCell(
                ("Allmän fråga", "Rådgivning", "Energirådgivning")[i % 3],
                (
                    "Hej, vi funderar på solceller och batteri men vet inte vad som passar vår villa.",
                    "Kan ni ge råd om solceller kontra batteri för vår förbrukning?",
                    "Hi, we would like an overview of energy storage options for our home in Uppsala.",
                    "Vi behöver hjälp att bedöma om laddbox eller solceller bör prioriteras.",
                    "Hej, vi planerar renovering och vill veta vad som är rimligt för taket.",
                    "Can you book a short call about solar, battery and charging?",
                    "Hej, vi vill ha en översiktlig rådgivning för vår villa i Enköping.",
                    "We wonder which solution gives the best value for our annual consumption.",
                )[i],
                "generic_lead",
                "lead",
                "new_thread",
                _langs[i],
                "send_after_approval",
                (),
                False,
                True,
                ("consultation",) if _langs[i] == "en" else ("rådgivning",),
                ("pris",),
            )
            for i in range(8)
        )
    elif family == "missing_attachment":
        _FAMILY_TEMPLATES[family] = tuple(
            CoworkerFamilyCell(
                ("Bifogar snart", "Saknar ritning", "Ritning följer")[i % 3],
                (
                    "Hej, vi vill ha offert på solceller men saknar ritning på taket just nu.",
                    "Hej, vi planerar laddbox och kan bifoga elschema senare idag.",
                    "Hi, we need a solar quote but the roof drawing is not attached yet.",
                    "Hej, bifogar bilder på taket så snart vi är hemma.",
                    "Vi vill ha solceller i Uppsala och har ritningen kvar på datorn, skickar den strax.",
                    "Hej, laddbox-offert önskas. Elritning saknas i det här mailet.",
                    "Hej, kan ni titta på solceller? Jag bifogar takmätning i nästa mail.",
                    "Hej, vi söker offert men utan bifogad ritning i detta meddelande.",
                )[i],
                "solar_installation" if i % 2 == 0 else "ev_charger_installation",
                "ambiguous_short",
                "new_thread",
                "en" if i == 2 else "sv",
                "send_after_approval",
                (),
                False,
                True,
                ("bifog",) if i != 2 else ("attach",),
                ("pris",),
            )
            for i in range(8)
        )
    elif family == "multi_turn_continuation":
        _FAMILY_TEMPLATES[family] = tuple(
            CoworkerFamilyCell(
                "Fortsättning tråd",
                (
                    "Hej igen, här kommer takytan: cirka 45 kvm plåttak i Uppsala.",
                    "Tack, bifogar nu årsförbrukningen på 18500 kWh.",
                    "Hej, vi kan bekräfta att det gäller villa och inte BRF.",
                    "Här kommer adressen: Storgatan 12 i Enköping.",
                    "Hej igen, vi har mätt taket till 38 kvm och vill veta nästa steg.",
                    "Kompletterar med att huvudsäkringen är 25A.",
                    "Hej, vi följer upp offertförfrågan och kan skicka takbilder idag.",
                    "Här är kompletterande info: taket vetter söder och är utan skugga.",
                )[i],
                "solar_installation",
                "lead",
                "continuation",
                "sv",
                "send_after_approval",
                ("city", "customer_name"),
                True,
                True,
                ("kompletter",),
                ("tack för din förfrågan",),
            )
            for i in range(8)
        )
    elif family == "battery_installation_known_facts":
        _FAMILY_TEMPLATES[family] = _simple_family(
            family, service_type="battery_storage", intent="lead", marker_sv="batteri", marker_en="battery",
            subjects=("Batteri känd anläggning",),
        )
    elif family == "solar_installation_followup":
        _FAMILY_TEMPLATES[family] = _FAMILY_TEMPLATES["solar_installation_new"]


def all_coworker_family_cells() -> list[tuple[str, CoworkerFamilyCell]]:
    cells: list[tuple[str, CoworkerFamilyCell]] = []
    for family in COWORKER_FAMILIES:
        for cell in _FAMILY_TEMPLATES.get(family, ()):
            cells.append((family, cell))
    return cells
