"""Print a setup checklist for a new AI Receptionist test tenant.

Usage:
    python -m scripts.print_ai_receptionist_test_setup
    python scripts/print_ai_receptionist_test_setup.py

This script prints only — it does NOT modify any data.
"""
from __future__ import annotations


_REQUIRED_INTEGRATIONS = ["google_mail"]
_OPTIONAL_INTEGRATIONS = ["google_sheets"]

_SHEET_TABS = ["Leads", "Support", "Logg"]

_LEADS_COLUMNS = [
    "Datum", "Kund", "Telefon", "E-post", "Ärendetyp",
    "Prioritet", "Sammanfattning", "Saknas", "Föreslaget nästa steg",
    "Status", "Källa", "Job ID",
]

_SUPPORT_COLUMNS = [
    "Datum", "Kund", "Telefon", "E-post", "Ärende",
    "Prioritet", "Risk", "Sammanfattning", "Föreslagen åtgärd",
    "Status", "Källa", "Job ID",
]

_LOGG_COLUMNS = ["Tid", "Typ", "Job ID", "Action", "Resultat", "Kommentar"]


def _section(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def _item(label: str, value: str = "", ok: bool | None = None) -> None:
    if ok is True:
        prefix = "  [OK] "
    elif ok is False:
        prefix = "  [!!] "
    else:
        prefix = "  [ ]  "
    if value:
        print(f"{prefix}{label}: {value}")
    else:
        print(f"{prefix}{label}")


def main() -> None:
    print()
    print("  AI Receptionist — Test Tenant Setup Checklist")
    print("  (Read-only — no data is modified)")

    _section("TENANT SETTINGS")
    _item("enabled_job_types", "lead, customer_inquiry")
    _item("allowed_integrations (required)", ", ".join(_REQUIRED_INTEGRATIONS))
    _item("allowed_integrations (optional)", ", ".join(_OPTIONAL_INTEGRATIONS))
    _item("auto_actions.lead", "false  ← MUST be false")
    _item("auto_actions.customer_inquiry", "false  ← MUST be false")
    _item("auto_actions.invoice", "false  ← MUST be false")
    _item("automation.followups_enabled", "true")
    _item("automation.leads_enabled", "true")
    _item("scheduler.run_mode", "manual  ← MUST be manual for first tests")
    _item("support_email", "<your internal email>  ← required for handoff")

    _section("GMAIL SETUP")
    _item("Gmail label", "e.g. krowolf-demo-test01  ← create in Gmail first")
    _item("Gmail query", "label:<your-label>")
    _item("Test emails", "Apply label + mark unread before scan")
    _item("dry_run=true", "Always run dry first to preview scope")
    _item("max_emails", "10  ← limit during first tests")

    _section("GOOGLE SHEETS (if testing Sheets export)")
    _item("google_sheets.spreadsheet_id", "<paste sheet ID from URL>")
    _item("allowed_integrations includes", "google_sheets")
    print()
    print("  Required tabs:")
    for tab in _SHEET_TABS:
        print(f"    - {tab}")
    print()
    print(f"  Leads columns ({len(_LEADS_COLUMNS)}):")
    print("    " + ", ".join(_LEADS_COLUMNS))
    print()
    print(f"  Support columns ({len(_SUPPORT_COLUMNS)}):")
    print("    " + ", ".join(_SUPPORT_COLUMNS))
    print()
    print(f"  Logg columns ({len(_LOGG_COLUMNS)}):")
    print("    " + ", ".join(_LOGG_COLUMNS))

    _section("SAFETY CHECKLIST")
    _item("auto_actions = false for ALL job types", ok=None)
    _item("scheduler.run_mode = manual", ok=None)
    _item("No monday in allowed_integrations (unless explicitly testing)", ok=None)
    _item("No visma in allowed_integrations", ok=None)
    _item("API key stored securely (not in chat/logs)", ok=None)
    _item("Complaint/emergency emails verified → manual_review only", ok=None)
    _item("Pending approval body reviewed before approving email send", ok=None)

    _section("TEST SCENARIO REMINDERS")
    scenarios = [
        ("1", "Laddbox hemma", "lead", "Leads"),
        ("2", "Laddbox fel", "customer_inquiry", "Support"),
        ("3", "Batteri till solceller", "lead", "Leads"),
        ("4", "Solceller producerar dåligt", "customer_inquiry", "Support"),
        ("5", "Akut elrisk / luktar bränt", "customer_inquiry", "Logg (manual_review)"),
        ("6", "VVS-läcka", "customer_inquiry/lead", "Support"),
        ("7", "Bygg/snickarjobb", "lead", "Leads"),
        ("8", "Missnöjd kund / complaint", "customer_inquiry", "Logg (manual_review)"),
    ]
    print()
    print(f"  {'#':<3} {'Scenario':<35} {'job_type':<22} {'Sheet tab'}")
    print(f"  {'-'*3} {'-'*35} {'-'*22} {'-'*20}")
    for num, name, jtype, tab in scenarios:
        print(f"  {num:<3} {name:<35} {jtype:<22} {tab}")

    _section("DOCS REFERENCE")
    docs = [
        ("Onboarding checklist", "docs/ai-receptionist-test-customer-onboarding.md"),
        ("Test mail scenarios", "docs/ai-receptionist-test-mail-scenarios.md"),
        ("MVP Gate", "docs/ai-receptionist-mvp-gate.md"),
        ("Friend test guide", "docs/ai-receptionist-friend-test-guide.md"),
        ("Runbook", "docs/08-runbook.md"),
    ]
    for label, path in docs:
        print(f"  {label:<30} {path}")

    print()
    print("  Ready to set up? Follow docs/ai-receptionist-test-customer-onboarding.md")
    print()


if __name__ == "__main__":
    main()
