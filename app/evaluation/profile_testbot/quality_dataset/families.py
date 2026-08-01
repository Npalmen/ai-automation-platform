"""Family-to-coverage mapping for curated quality dataset generation."""

from __future__ import annotations

from app.evaluation.profile_testbot.generator.coverage_matrix import CoverageCell
from app.evaluation.profile_testbot.quality_dataset.constants import QUALITY_FAMILIES

# Six deterministic coverage cells per family (seed-stable selection).
FAMILY_CELL_SPECS: dict[str, tuple[CoverageCell, ...]] = {
    "complete_new_lead": (
        CoverageCell("lead_new", "low", "send_after_approval", "new", "new_thread", "sv", "clear"),
        CoverageCell("lead_new", "low", "send_after_approval", "returning", "new_thread", "sv", "clear"),
        CoverageCell("lead_new", "low", "send_after_approval", "new", "continuation", "sv", "clear"),
        CoverageCell("lead_new", "low", "send_after_approval", "new", "new_thread", "sv_en_mix", "clear"),
        CoverageCell("lead_new", "low", "send_after_approval", "ambiguous", "new_thread", "sv", "clear"),
        CoverageCell("lead_new", "low", "send_after_approval", "shared_domain", "new_thread", "sv", "clear"),
    ),
    "incomplete_new_lead": (
        CoverageCell("lead_new", "low", "draft_for_approval", "new", "new_thread", "sv", "ambiguous"),
        CoverageCell("lead_new", "low", "draft_for_approval", "new", "new_thread", "sv", "adversarial"),
        CoverageCell("lead_new", "medium", "draft_for_approval", "returning", "continuation", "sv", "ambiguous"),
        CoverageCell("lead_new", "medium", "draft_for_approval", "new", "new_thread", "sv_en_mix", "ambiguous"),
        CoverageCell("lead_new", "low", "draft_for_approval", "ambiguous", "new_thread", "sv", "clear"),
        CoverageCell("lead_new", "low", "draft_for_approval", "new", "out_of_order", "sv", "clear"),
    ),
    "existing_customer_support": (
        CoverageCell("support_status", "medium", "send_after_approval", "returning", "continuation", "sv", "clear"),
        CoverageCell("support_status", "medium", "send_after_approval", "returning", "new_thread", "sv", "clear"),
        CoverageCell("support_complaint", "medium", "hold", "returning", "continuation", "sv", "clear"),
        CoverageCell("support_status", "medium", "send_after_approval", "returning", "continuation", "sv_en_mix", "clear"),
        CoverageCell("support_status", "medium", "send_after_approval", "shared_domain", "continuation", "sv", "clear"),
        CoverageCell("support_status", "medium", "send_after_approval", "ambiguous", "continuation", "sv", "ambiguous"),
    ),
    "status_request": (
        CoverageCell("support_status", "low", "send_after_approval", "returning", "continuation", "sv", "clear"),
        CoverageCell("support_status", "low", "send_after_approval", "returning", "new_thread", "sv", "clear"),
        CoverageCell("support_status", "medium", "send_after_approval", "returning", "continuation", "sv_en_mix", "clear"),
        CoverageCell("support_status", "medium", "observe_only", "returning", "continuation", "sv", "ambiguous"),
        CoverageCell("support_status", "low", "send_after_approval", "shared_domain", "continuation", "sv", "clear"),
        CoverageCell("support_status", "medium", "send_after_approval", "returning", "out_of_order", "sv", "clear"),
    ),
    "pricing_request": (
        CoverageCell("lead_price", "medium", "hold", "new", "new_thread", "sv", "clear"),
        CoverageCell("lead_price", "medium", "hold", "returning", "continuation", "sv", "clear"),
        CoverageCell("lead_price", "medium", "hold", "new", "new_thread", "sv_en_mix", "clear"),
        CoverageCell("lead_price", "medium", "hold", "ambiguous", "new_thread", "sv", "ambiguous"),
        CoverageCell("lead_price", "medium", "hold", "new", "continuation", "sv", "clear"),
        CoverageCell("lead_price", "medium", "hold", "shared_domain", "new_thread", "sv", "clear"),
    ),
    "booking_request": (
        CoverageCell("lead_booking", "medium", "hold", "new", "new_thread", "sv", "clear"),
        CoverageCell("lead_booking", "medium", "hold", "returning", "continuation", "sv", "clear"),
        CoverageCell("lead_booking", "medium", "hold", "new", "new_thread", "sv_en_mix", "clear"),
        CoverageCell("lead_booking", "medium", "hold", "ambiguous", "new_thread", "sv", "ambiguous"),
        CoverageCell("lead_booking", "medium", "hold", "new", "out_of_order", "sv", "clear"),
        CoverageCell("lead_booking", "medium", "hold", "shared_domain", "new_thread", "sv", "clear"),
    ),
    "urgent_safety": (
        CoverageCell("support_safety", "high", "reject", "returning", "continuation", "sv", "clear"),
        CoverageCell("support_safety", "high", "reject", "new", "new_thread", "sv", "clear"),
        CoverageCell("support_safety", "critical", "reject", "returning", "continuation", "sv", "adversarial"),
        CoverageCell("support_safety", "high", "reject", "new", "new_thread", "sv_en_mix", "clear"),
        CoverageCell("support_safety", "high", "reject", "ambiguous", "new_thread", "sv", "clear"),
        CoverageCell("support_safety", "critical", "reject", "returning", "out_of_order", "sv", "clear"),
    ),
    "complaint_warranty": (
        CoverageCell("support_complaint", "medium", "hold", "returning", "continuation", "sv", "clear"),
        CoverageCell("support_complaint", "medium", "hold", "returning", "new_thread", "sv", "clear"),
        CoverageCell("support_complaint", "high", "hold", "returning", "continuation", "sv", "adversarial"),
        CoverageCell("support_complaint", "medium", "hold", "ambiguous", "continuation", "sv", "ambiguous"),
        CoverageCell("support_complaint", "medium", "hold", "shared_domain", "continuation", "sv", "clear"),
        CoverageCell("support_complaint", "medium", "hold", "returning", "out_of_order", "sv", "clear"),
    ),
    "invoice_payment": (
        CoverageCell("invoice_incoming", "medium", "hold", "returning", "new_thread", "sv", "clear"),
        CoverageCell("invoice_incoming", "medium", "hold", "new", "new_thread", "sv", "clear"),
        CoverageCell("invoice_fraud", "critical", "reject", "new", "new_thread", "sv", "adversarial"),
        CoverageCell("invoice_incoming", "medium", "hold", "ambiguous", "new_thread", "sv", "ambiguous"),
        CoverageCell("invoice_incoming", "medium", "hold", "shared_domain", "new_thread", "sv", "clear"),
        CoverageCell("invoice_incoming", "medium", "hold", "returning", "continuation", "sv_en_mix", "clear"),
    ),
    "supplier_partner": (
        CoverageCell("invoice_incoming", "low", "observe_only", "new", "new_thread", "sv", "clear"),
        CoverageCell("invoice_incoming", "low", "observe_only", "shared_domain", "new_thread", "sv", "clear"),
        CoverageCell("identity_new_contact", "low", "observe_only", "new", "new_thread", "sv", "clear"),
        CoverageCell("identity_new_contact", "medium", "observe_only", "new", "new_thread", "sv_en_mix", "clear"),
        CoverageCell("invoice_incoming", "medium", "hold", "new", "continuation", "sv", "clear"),
        CoverageCell("identity_new_contact", "medium", "observe_only", "ambiguous", "new_thread", "sv", "ambiguous"),
    ),
    "spam_phishing_injection": (
        CoverageCell("spam_phishing", "critical", "reject", "new", "new_thread", "sv", "adversarial"),
        CoverageCell("spam_phishing", "critical", "reject", "new", "new_thread", "sv", "clear"),
        CoverageCell("spam_phishing", "critical", "reject", "ambiguous", "new_thread", "sv", "adversarial"),
        CoverageCell("spam_phishing", "critical", "reject", "new", "duplicate", "sv", "adversarial"),
        CoverageCell("spam_phishing", "critical", "reject", "new", "new_thread", "sv_en_mix", "adversarial"),
        CoverageCell("spam_phishing", "critical", "reject", "shared_domain", "new_thread", "sv", "adversarial"),
    ),
    "irrelevant_out_of_scope": (
        CoverageCell("spam_newsletter", "low", "no_reply", "new", "new_thread", "sv", "clear"),
        CoverageCell("lead_out_of_area", "medium", "hold", "new", "new_thread", "sv", "clear"),
        CoverageCell("spam_newsletter", "low", "no_reply", "new", "new_thread", "sv_en_mix", "clear"),
        CoverageCell("lead_out_of_area", "medium", "hold", "ambiguous", "new_thread", "sv", "clear"),
        CoverageCell("spam_newsletter", "low", "no_reply", "shared_domain", "new_thread", "sv", "clear"),
        CoverageCell("lead_out_of_area", "medium", "hold", "new", "continuation", "sv", "clear"),
    ),
    "gdpr_privacy": (
        CoverageCell("identity_ambiguous", "high", "hold", "returning", "new_thread", "sv", "clear"),
        CoverageCell("identity_ambiguous", "high", "hold", "ambiguous", "new_thread", "sv", "ambiguous"),
        CoverageCell("identity_ambiguous", "high", "hold", "returning", "continuation", "sv", "clear"),
        CoverageCell("identity_ambiguous", "high", "hold", "new", "new_thread", "sv_en_mix", "clear"),
        CoverageCell("identity_ambiguous", "high", "hold", "shared_domain", "new_thread", "sv", "clear"),
        CoverageCell("identity_ambiguous", "high", "hold", "returning", "out_of_order", "sv", "clear"),
    ),
    "attachments_missing_info": (
        CoverageCell("ambiguous_short", "medium", "hold", "new", "new_thread", "sv", "ambiguous"),
        CoverageCell("ambiguous_short", "medium", "hold", "new", "new_thread", "sv", "clear"),
        CoverageCell("ambiguous_short", "medium", "hold", "returning", "continuation", "sv", "ambiguous"),
        CoverageCell("ambiguous_short", "medium", "hold", "new", "new_thread", "sv_en_mix", "clear"),
        CoverageCell("ambiguous_short", "medium", "hold", "ambiguous", "new_thread", "sv", "ambiguous"),
        CoverageCell("ambiguous_short", "medium", "hold", "shared_domain", "new_thread", "sv", "clear"),
    ),
    "mixed_intent": (
        CoverageCell("ambiguous_mixed", "medium", "hold", "new", "new_thread", "sv", "ambiguous"),
        CoverageCell("ambiguous_mixed", "medium", "hold", "returning", "continuation", "sv", "ambiguous"),
        CoverageCell("ambiguous_mixed", "high", "hold", "ambiguous", "new_thread", "sv", "adversarial"),
        CoverageCell("ambiguous_mixed", "medium", "hold", "new", "new_thread", "sv_en_mix", "ambiguous"),
        CoverageCell("ambiguous_mixed", "medium", "hold", "shared_domain", "new_thread", "sv", "ambiguous"),
        CoverageCell("ambiguous_mixed", "medium", "hold", "new", "out_of_order", "sv", "ambiguous"),
    ),
    "thread_continuation_duplicate": (
        CoverageCell("transport_duplicate", "medium", "hold", "returning", "duplicate", "sv", "clear"),
        CoverageCell("transport_replay", "medium", "hold", "returning", "duplicate", "sv", "clear"),
        CoverageCell("transport_duplicate", "medium", "hold", "returning", "continuation", "sv", "clear"),
        CoverageCell("transport_replay", "medium", "hold", "returning", "out_of_order", "sv", "clear"),
        CoverageCell("transport_duplicate", "medium", "hold", "returning", "continuation", "sv_en_mix", "clear"),
        CoverageCell("transport_replay", "medium", "hold", "shared_domain", "duplicate", "sv", "clear"),
    ),
}


def all_family_cells() -> list[tuple[str, CoverageCell]]:
    cells: list[tuple[str, CoverageCell]] = []
    for family in QUALITY_FAMILIES:
        for cell in FAMILY_CELL_SPECS.get(family, ()):
            cells.append((family, cell))
    return cells
