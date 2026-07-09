"""
Demo safety contract tests — Mårtens Demo and Niklas Demo (rehearsal).

These tests verify that the demo documentation files correctly document
all required safety properties. No product logic is tested — only that
critical safety terms appear in the relevant docs.

Covered — Mårtens Demo:
- MARTENS_DEMO_SETUP.md mentions auto_actions=false
- MARTENS_DEMO_SETUP.md mentions approval-first / Gmail send requires approval
- MARTENS_DEMO_SETUP.md mentions no Visma production writes
- MARTENS_DEMO_SETUP.md mentions Google Sheet ID must not be committed
- MARTENS_DEMO_SETUP.md mentions no real customer data
- MARTENS_DEMO_SETUP.md mentions no external writes except isolated demo sheet
- MARTENS_DEMO_READINESS_CHECKLIST.md classifies DO_NOT_DO items
- MARTENS_DEMO_READINESS_CHECKLIST.md classifies BLOCKER items
- MARTENS_DEMO_READINESS_CHECKLIST.md has auto_actions=false as BLOCKER
- MARTENS_DEMO_READINESS_CHECKLIST.md has Visma production write as DO_NOT_DO
- MARTENS_DEMO_READINESS_CHECKLIST.md has Google Sheet ID not committed
- google-sheets-leads-support-structure.md marks as manual/demo step
- google-sheets-leads-support-structure.md prohibits committing Sheet ID
- martens-sales-talk-track.md mentions what not to promise
- Demo setup has rollback/cleanup section

Covered — Niklas Demo (rehearsal):
- NIKLAS_DEMO_SETUP.md mentions auto_actions=false
- NIKLAS_DEMO_SETUP.md mentions approval-first / Gmail send requires approval
- NIKLAS_DEMO_SETUP.md mentions label:krowolf-demo-niklas is:unread
- NIKLAS_DEMO_SETUP.md mentions no Visma production writes
- NIKLAS_DEMO_SETUP.md mentions no Monday production writes
- NIKLAS_DEMO_SETUP.md mentions no real customer data
- NIKLAS_DEMO_SETUP.md mentions Google Sheet ID not committed
- NIKLAS_DEMO_SETUP.md mentions dry_run before real processing
- NIKLAS_DEMO_SETUP.md mentions rollback/cleanup
- NIKLAS_DEMO_SETUP.md references T_NIKLAS_DEMO_001
- NIKLAS_DEMO_READINESS_CHECKLIST.md has BLOCKER / REQUIRED / DO_NOT_DO
- NIKLAS_DEMO_READINESS_CHECKLIST.md has auto_actions=false as BLOCKER
- NIKLAS_DEMO_READINESS_CHECKLIST.md has Visma/Monday as DO_NOT_DO
- NIKLAS_DEMO_READINESS_CHECKLIST.md has dry_run as BLOCKER
- NIKLAS_DEMO_READINESS_CHECKLIST.md has no real customer data
- Both NIKLAS docs exist in repo
"""
from __future__ import annotations

import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent

SETUP_DOC = REPO_ROOT / "docs" / "MARTENS_DEMO_SETUP.md"
CHECKLIST_DOC = REPO_ROOT / "docs" / "MARTENS_DEMO_READINESS_CHECKLIST.md"
SCENARIOS_DOC = REPO_ROOT / "docs" / "demo" / "martens-gmail-demo-scenarios.md"
SHEETS_DOC = REPO_ROOT / "docs" / "demo" / "google-sheets-leads-support-structure.md"
TALK_TRACK_DOC = REPO_ROOT / "docs" / "demo" / "martens-sales-talk-track.md"


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


# ─── File existence ────────────────────────────────────────────────────────────

class TestDemoDocsExist:
    def test_setup_doc_exists(self):
        assert SETUP_DOC.exists(), f"Missing: {SETUP_DOC}"

    def test_checklist_doc_exists(self):
        assert CHECKLIST_DOC.exists(), f"Missing: {CHECKLIST_DOC}"

    def test_scenarios_doc_exists(self):
        assert SCENARIOS_DOC.exists(), f"Missing: {SCENARIOS_DOC}"

    def test_sheets_doc_exists(self):
        assert SHEETS_DOC.exists(), f"Missing: {SHEETS_DOC}"

    def test_talk_track_doc_exists(self):
        assert TALK_TRACK_DOC.exists(), f"Missing: {TALK_TRACK_DOC}"


# ─── MARTENS_DEMO_SETUP.md safety properties ──────────────────────────────────

class TestDemoSetupSafetyProps:
    def setup_method(self):
        self.text = _read(SETUP_DOC).lower()

    def test_mentions_auto_actions_false(self):
        assert "auto_actions" in self.text and "false" in self.text, (
            "MARTENS_DEMO_SETUP.md must document auto_actions=false"
        )

    def test_mentions_approval_first(self):
        assert "approval" in self.text, (
            "MARTENS_DEMO_SETUP.md must document approval-first Gmail send"
        )

    def test_mentions_no_visma_production_writes(self):
        assert "no production" in self.text or "no visma production" in self.text or (
            "visma" in self.text and "production" in self.text
        ), "MARTENS_DEMO_SETUP.md must document no Visma production writes"

    def test_mentions_no_commit_sheet_id(self):
        assert "commit" in self.text or "sheet id" in self.text, (
            "MARTENS_DEMO_SETUP.md must document that Sheet ID must not be committed"
        )

    def test_mentions_no_real_customer_data(self):
        assert "no real customer" in self.text or "real customer data" in self.text or (
            "real" in self.text and "customer" in self.text and "data" in self.text
        ), "MARTENS_DEMO_SETUP.md must document no real customer data"

    def test_mentions_external_writes_isolated(self):
        assert (
            "isolated" in self.text or "external writes" in self.text
        ), "MARTENS_DEMO_SETUP.md must document external writes isolation"

    def test_mentions_dry_run(self):
        assert "dry_run" in self.text or "dry run" in self.text, (
            "MARTENS_DEMO_SETUP.md must mention dry_run to scope demo safely"
        )

    def test_mentions_rollback_cleanup(self):
        assert "rollback" in self.text or "cleanup" in self.text, (
            "MARTENS_DEMO_SETUP.md must include rollback/cleanup steps"
        )

    def test_mentions_tenant_id(self):
        assert "t_martens_demo_001" in self.text or "martens_demo_001" in self.text, (
            "MARTENS_DEMO_SETUP.md must reference the demo tenant ID"
        )

    def test_mentions_no_monday_production_writes(self):
        assert "monday" in self.text, (
            "MARTENS_DEMO_SETUP.md must reference Monday (to document no production writes)"
        )


# ─── MARTENS_DEMO_READINESS_CHECKLIST.md ─────────────────────────────────────

class TestDemoReadinessChecklist:
    def setup_method(self):
        self.text = _read(CHECKLIST_DOC)
        self.lower = self.text.lower()

    def test_has_blocker_classification(self):
        assert "BLOCKER" in self.text, (
            "Checklist must classify BLOCKER items"
        )

    def test_has_required_classification(self):
        assert "REQUIRED" in self.text, (
            "Checklist must classify REQUIRED items"
        )

    def test_has_do_not_do_classification(self):
        assert "DO_NOT_DO" in self.text, (
            "Checklist must classify DO_NOT_DO items"
        )

    def test_auto_actions_false_is_blocker(self):
        lines = self.text.splitlines()
        blocker_lines = [l for l in lines if "BLOCKER" in l]
        assert any("auto_actions" in l.lower() for l in blocker_lines), (
            "auto_actions=false must be classified as BLOCKER in the readiness checklist"
        )

    def test_visma_production_write_is_do_not_do(self):
        lines = self.text.splitlines()
        do_not_do_lines = [l for l in lines if "DO_NOT_DO" in l]
        assert any("visma" in l.lower() for l in do_not_do_lines), (
            "Visma production write must be classified as DO_NOT_DO"
        )

    def test_no_monday_production_write_is_do_not_do(self):
        lines = self.text.splitlines()
        do_not_do_lines = [l for l in lines if "DO_NOT_DO" in l]
        assert any("monday" in l.lower() for l in do_not_do_lines), (
            "Monday production write must be classified as DO_NOT_DO"
        )

    def test_sheet_id_not_committed_is_required(self):
        lines = self.text.splitlines()
        required_or_do_not_do = [l for l in lines if "REQUIRED" in l or "DO_NOT_DO" in l]
        assert any("sheet" in l.lower() and ("commit" in l.lower() or "id" in l.lower())
                   for l in required_or_do_not_do), (
            "Google Sheet ID must not be committed — must appear in checklist as REQUIRED or DO_NOT_DO"
        )

    def test_no_real_customer_data_mentioned(self):
        assert "real customer" in self.lower or (
            "real" in self.lower and "customer" in self.lower and "data" in self.lower
        ), "Checklist must address no real customer data"

    def test_gmail_approval_first_mentioned(self):
        assert "approval" in self.lower, (
            "Checklist must mention Gmail approval-first"
        )

    def test_dry_run_or_demo_label_mentioned(self):
        assert "dry_run" in self.lower or "dry run" in self.lower or "krowolf-demo" in self.lower, (
            "Checklist must mention dry_run or demo label scope"
        )


# ─── google-sheets-leads-support-structure.md ─────────────────────────────────

class TestGoogleSheetsDoc:
    def setup_method(self):
        self.text = _read(SHEETS_DOC)
        self.lower = self.text.lower()

    def test_marks_as_manual_step(self):
        assert "manual" in self.lower, (
            "Sheets doc must mark this as a manual demo step (integration not yet implemented)"
        )

    def test_prohibits_committing_sheet_id(self):
        assert "commit" in self.lower and "sheet" in self.lower, (
            "Sheets doc must prohibit committing the Sheet ID"
        )

    def test_mentions_leads_tab(self):
        assert "leads" in self.lower, "Sheets doc must define a Leads tab"

    def test_mentions_support_tab(self):
        assert "support" in self.lower, "Sheets doc must define a Support tab"

    def test_mentions_isolation(self):
        assert "isolat" in self.lower, (
            "Sheets doc must document isolation — demo sheet only, no cross-tenant writes"
        )

    def test_has_column_headers(self):
        assert "datum" in self.lower or "job-id" in self.lower or "avsändare" in self.lower, (
            "Sheets doc must define column headers (in Swedish or English)"
        )

    def test_has_example_rows(self):
        assert "lars eriksson" in self.lower or "anna lindqvist" in self.lower or (
            "example" in self.lower and ("row" in self.lower or "scenario" in self.lower)
        ), "Sheets doc must include example rows"


# ─── martens-gmail-demo-scenarios.md ──────────────────────────────────────────

class TestGmailDemoScenarios:
    def setup_method(self):
        self.text = _read(SCENARIOS_DOC)
        self.lower = self.text.lower()

    def test_has_at_least_10_scenarios(self):
        scenario_count = self.text.count("## Scenario")
        assert scenario_count >= 10, (
            f"Demo scenarios must include at least 10 scenarios, found {scenario_count}"
        )

    def test_all_senders_are_placeholders(self):
        assert "example.com" in self.lower, (
            "All demo sender addresses must use @example.com placeholder domain"
        )

    def test_no_real_customer_emails(self):
        # Check that no real email domains appear as sender addresses (not URLs).
        # krowolf.se is allowed as an API URL but not as a sender email address.
        import re
        sender_emails = re.findall(r"[\w.\-+]+@([\w.\-]+)", self.text)
        forbidden_domains = ["gmail.com", "hotmail.com", "outlook.com"]
        for domain in forbidden_domains:
            assert domain not in sender_emails, (
                f"Demo scenarios must not use real email domain as sender: {domain}"
            )
        # All @-addresses in scenarios must be @example.com
        non_example = [e for e in sender_emails if e != "example.com"]
        assert non_example == [], (
            f"All demo sender addresses must use @example.com, found: {non_example}"
        )

    def test_has_expected_classification_field(self):
        assert "klassificering" in self.lower or "classification" in self.lower, (
            "Each scenario must document expected classification"
        )

    def test_has_expected_priority_field(self):
        assert "prioritet" in self.lower or "priority" in self.lower, (
            "Each scenario must document expected priority"
        )

    def test_has_google_sheets_tab_field(self):
        assert "google sheets" in self.lower or "sheets-flik" in self.lower, (
            "Each scenario must document expected Google Sheets tab"
        )

    def test_has_approval_required_field(self):
        assert "godkännande" in self.lower or "approval" in self.lower, (
            "Each scenario must document whether approval is required"
        )

    def test_warns_about_fictional_senders(self):
        assert "fiktiva" in self.lower or "fictional" in self.lower or "example.com" in self.lower, (
            "Scenarios doc must warn that all senders are fictional"
        )


# ─── martens-sales-talk-track.md ──────────────────────────────────────────────

class TestSalesTalkTrack:
    def setup_method(self):
        self.text = _read(TALK_TRACK_DOC)
        self.lower = self.text.lower()

    def test_has_short_demo_script(self):
        assert "2-minut" in self.lower or "2 minut" in self.lower, (
            "Talk track must include a 2-minute demo script"
        )

    def test_has_longer_demo_script(self):
        assert "5-minut" in self.lower or "5 minut" in self.lower, (
            "Talk track must include a 5-minute demo script"
        )

    def test_has_what_not_to_promise(self):
        assert "inte" in self.lower and ("lova" in self.lower or "promise" in self.lower or "ännu" in self.lower), (
            "Talk track must include a 'what not to promise yet' section"
        )

    def test_explains_approval_first(self):
        assert "godkänna" in self.lower or "godkännande" in self.lower or "approval" in self.lower, (
            "Talk track must explain the approval-first flow"
        )

    def test_explains_visma_sandbox(self):
        assert "visma" in self.lower, (
            "Talk track must explain the Visma sandbox/status framing"
        )

    def test_explains_google_sheets(self):
        assert "google sheet" in self.lower or "sheets" in self.lower, (
            "Talk track must explain Google Sheets for leads/support"
        )

    def test_has_objection_handling(self):
        assert "invändning" in self.lower or "objection" in self.lower or "frågar" in self.lower or (
            "om de frågar" in self.lower or "vanliga" in self.lower
        ), "Talk track must include objection handling"

    def test_written_in_swedish(self):
        swedish_markers = ["hej", "och", "att", "vi", "det", "är", "för", "inte"]
        found = sum(1 for marker in swedish_markers if marker in self.lower)
        assert found >= 5, (
            f"Talk track must be written in Swedish — only {found}/8 Swedish markers found"
        )


# ─── Niklas Demo file existence ───────────────────────────────────────────────

NIKLAS_SETUP_DOC = REPO_ROOT / "docs" / "NIKLAS_DEMO_SETUP.md"
NIKLAS_CHECKLIST_DOC = REPO_ROOT / "docs" / "NIKLAS_DEMO_READINESS_CHECKLIST.md"


class TestNiklasDemoDocsExist:
    def test_niklas_setup_doc_exists(self):
        assert NIKLAS_SETUP_DOC.exists(), f"Missing: {NIKLAS_SETUP_DOC}"

    def test_niklas_checklist_doc_exists(self):
        assert NIKLAS_CHECKLIST_DOC.exists(), f"Missing: {NIKLAS_CHECKLIST_DOC}"


# ─── NIKLAS_DEMO_SETUP.md safety properties ───────────────────────────────────

class TestNiklasDemoSetupSafetyProps:
    def setup_method(self):
        self.text = _read(NIKLAS_SETUP_DOC).lower()

    def test_mentions_auto_actions_false(self):
        assert "auto_actions" in self.text and "false" in self.text, (
            "NIKLAS_DEMO_SETUP.md must document auto_actions=false"
        )

    def test_mentions_approval_first(self):
        assert "approval" in self.text, (
            "NIKLAS_DEMO_SETUP.md must document approval-first Gmail send"
        )

    def test_mentions_demo_label_query(self):
        assert "krowolf-demo-niklas" in self.text, (
            "NIKLAS_DEMO_SETUP.md must reference the Gmail label krowolf-demo-niklas"
        )

    def test_mentions_label_query_with_unread(self):
        assert "is:unread" in self.text, (
            "NIKLAS_DEMO_SETUP.md must include the Gmail query with is:unread"
        )

    def test_mentions_no_visma_production_writes(self):
        assert "visma" in self.text and "production" in self.text, (
            "NIKLAS_DEMO_SETUP.md must document no Visma production writes"
        )

    def test_mentions_no_monday_production_writes(self):
        assert "monday" in self.text, (
            "NIKLAS_DEMO_SETUP.md must reference Monday (document no production writes)"
        )

    def test_mentions_no_real_customer_data(self):
        assert "real customer" in self.text or (
            "real" in self.text and "customer" in self.text and "data" in self.text
        ), "NIKLAS_DEMO_SETUP.md must document no real customer data"

    def test_mentions_no_commit_sheet_id(self):
        assert "commit" in self.text or "sheet id" in self.text, (
            "NIKLAS_DEMO_SETUP.md must document that Sheet ID must not be committed"
        )

    def test_mentions_external_writes_isolated(self):
        assert "isolated" in self.text or "external writes" in self.text, (
            "NIKLAS_DEMO_SETUP.md must document external writes isolation"
        )

    def test_mentions_dry_run(self):
        assert "dry_run" in self.text or "dry run" in self.text, (
            "NIKLAS_DEMO_SETUP.md must mention dry_run before real processing"
        )

    def test_mentions_rollback_or_cleanup(self):
        assert "rollback" in self.text or "cleanup" in self.text, (
            "NIKLAS_DEMO_SETUP.md must include rollback/cleanup steps"
        )

    def test_mentions_tenant_id(self):
        assert "t_niklas_demo_001" in self.text or "niklas_demo_001" in self.text, (
            "NIKLAS_DEMO_SETUP.md must reference tenant ID T_NIKLAS_DEMO_001"
        )

    def test_mentions_gmail_account(self):
        assert "niklas.palm@sol-f.se" in self.text or "niklas.palm" in self.text, (
            "NIKLAS_DEMO_SETUP.md must reference the Gmail account niklas.palm@sol-f.se"
        )

    def test_mentions_rehearsal_relationship_to_martens_demo(self):
        assert "mårten" in self.text or "martens" in self.text or "rehearsal" in self.text, (
            "NIKLAS_DEMO_SETUP.md must explain the relationship to Mårtens Demo"
        )


# ─── NIKLAS_DEMO_READINESS_CHECKLIST.md ──────────────────────────────────────

class TestNiklasDemoReadinessChecklist:
    def setup_method(self):
        self.text = _read(NIKLAS_CHECKLIST_DOC)
        self.lower = self.text.lower()

    def test_has_blocker_classification(self):
        assert "BLOCKER" in self.text, (
            "Niklas checklist must classify BLOCKER items"
        )

    def test_has_required_classification(self):
        assert "REQUIRED" in self.text, (
            "Niklas checklist must classify REQUIRED items"
        )

    def test_has_do_not_do_classification(self):
        assert "DO_NOT_DO" in self.text, (
            "Niklas checklist must classify DO_NOT_DO items"
        )

    def test_auto_actions_false_is_blocker(self):
        lines = self.text.splitlines()
        blocker_lines = [l for l in lines if "BLOCKER" in l]
        assert any("auto_actions" in l.lower() for l in blocker_lines), (
            "auto_actions=false must be classified as BLOCKER in Niklas checklist"
        )

    def test_dry_run_is_blocker(self):
        lines = self.text.splitlines()
        blocker_lines = [l for l in lines if "BLOCKER" in l]
        assert any("dry" in l.lower() for l in blocker_lines), (
            "Gmail dry_run must be classified as BLOCKER in Niklas checklist"
        )

    def test_visma_production_write_is_do_not_do(self):
        lines = self.text.splitlines()
        do_not_do_lines = [l for l in lines if "DO_NOT_DO" in l]
        assert any("visma" in l.lower() for l in do_not_do_lines), (
            "Visma production write must be classified as DO_NOT_DO in Niklas checklist"
        )

    def test_monday_production_write_is_do_not_do(self):
        lines = self.text.splitlines()
        do_not_do_lines = [l for l in lines if "DO_NOT_DO" in l]
        assert any("monday" in l.lower() for l in do_not_do_lines), (
            "Monday production write must be classified as DO_NOT_DO in Niklas checklist"
        )

    def test_demo_label_is_blocker(self):
        lines = self.text.splitlines()
        blocker_lines = [l for l in lines if "BLOCKER" in l]
        assert any("krowolf-demo-niklas" in l.lower() for l in blocker_lines), (
            "Gmail label krowolf-demo-niklas must be classified as BLOCKER"
        )

    def test_no_real_customer_data_mentioned(self):
        assert "real customer" in self.lower or (
            "real" in self.lower and "customer" in self.lower and "data" in self.lower
        ), "Niklas checklist must address no real customer data"

    def test_gmail_approval_first_mentioned(self):
        assert "approval" in self.lower, (
            "Niklas checklist must mention Gmail approval-first"
        )

    def test_sheet_id_not_committed(self):
        lines = self.text.splitlines()
        required_or_do_not_do = [l for l in lines if "REQUIRED" in l or "DO_NOT_DO" in l]
        assert any(
            "sheet" in l.lower() and ("commit" in l.lower() or "id" in l.lower())
            for l in required_or_do_not_do
        ), "Google Sheet ID must not be committed — must appear as REQUIRED or DO_NOT_DO"

    def test_mentions_martens_demo_relationship(self):
        assert "mårten" in self.lower or "martens" in self.lower, (
            "Niklas checklist must reference the relationship to Mårtens Demo"
        )
