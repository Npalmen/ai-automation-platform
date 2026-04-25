"""
Routing hint draft generator.

Deterministic, read-only.  Inspects tenant_memory.system_map and produces
draft routing hints keyed by job type.  The operator must explicitly apply
hints via POST /tenant/routing-hints/apply — nothing is auto-saved here.

Output shape per job type
--------------------------
{
  "system": "monday",
  "target": {
    "board_id": "123",
    "board_name": "Leads",
    "group_id": null,
    "group_name": null
  },
  "confidence": "high" | "medium" | "low",
  "reason": "<human-readable explanation>"
}

or null when no suitable candidate is found.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Supported job types (all types the platform knows about)
# ---------------------------------------------------------------------------

SUPPORTED_JOB_TYPES: list[str] = [
    "lead",
    "customer_inquiry",
    "invoice",
    "partnership",
    "supplier",
    "support",
    "internal",
]

# ---------------------------------------------------------------------------
# Keyword fallback — board name matching when detected_purpose == "unknown"
# Maps job_type → keywords that strongly suggest that board handles the type
# ---------------------------------------------------------------------------

_NAME_KEYWORDS: dict[str, list[str]] = {
    "lead":             ["lead", "leads", "sales", "sälj", "offert", "prospect", "prospekt", "quote"],
    "customer_inquiry": ["inquiry", "inquiries", "kundfråga", "request", "kontakt", "frågor", "ärende"],
    "invoice":          ["invoice", "faktura", "fakturor", "ekonomi", "billing", "payment", "betalning"],
    "partnership":      ["partner", "partnership", "samarbete", "collaboration"],
    "supplier":         ["supplier", "vendor", "leverantör", "inköp", "order"],
    "support":          ["support", "helpdesk", "service", "ticket", "ärenden"],
    "internal":         ["internal", "intern", "admin", "operations", "drift"],
}


def _board_name_matches(board_name: str, job_type: str) -> bool:
    name_lower = board_name.lower()
    return any(kw in name_lower for kw in _NAME_KEYWORDS.get(job_type, []))


def _board_hint(board: dict, confidence: str, reason: str) -> dict:
    return {
        "system": "monday",
        "target": {
            "board_id":   str(board.get("id") or ""),
            "board_name": board.get("name") or "",
            "group_id":   None,
            "group_name": None,
        },
        "confidence": confidence,
        "reason":     reason,
    }


def _best_monday_candidate(
    boards: list[dict],
    job_type: str,
) -> dict | None:
    """
    Return the best board for this job_type, or None.

    Priority order:
    1. detected_purpose exact match → high confidence
    2. board name keyword match     → medium confidence (first match wins)
    3. No match                     → None
    """
    purpose_matches = [b for b in boards if b.get("detected_purpose") == job_type]
    if purpose_matches:
        board = purpose_matches[0]
        confidence = "high" if len(purpose_matches) == 1 else "medium"
        reason = (
            f"Board '{board.get('name')}' detected purpose matched {job_type}"
            if len(purpose_matches) == 1
            else f"Multiple boards matched {job_type} by purpose; chose '{board.get('name')}'"
        )
        return _board_hint(board, confidence, reason)

    name_matches = [b for b in boards if _board_name_matches(b.get("name") or "", job_type)]
    if name_matches:
        board = name_matches[0]
        confidence = "medium" if len(name_matches) == 1 else "low"
        reason = (
            f"Board name '{board.get('name')}' keyword-matched {job_type}"
            if len(name_matches) == 1
            else f"Multiple board names keyword-matched {job_type}; chose '{board.get('name')}'"
        )
        return _board_hint(board, confidence, reason)

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_routing_hint_drafts(tenant_memory: dict) -> dict:
    """
    Inspect tenant_memory and return draft routing hints for all supported
    job types.  Returns null for job types where no candidate was found.

    Pure function — no network or DB calls.
    """
    system_map = tenant_memory.get("system_map") or {}
    monday_data = system_map.get("monday") or {}
    boards: list[dict] = monday_data.get("boards") or []

    drafts: dict = {}
    for job_type in SUPPORTED_JOB_TYPES:
        if boards:
            drafts[job_type] = _best_monday_candidate(boards, job_type)
        else:
            drafts[job_type] = None

    return drafts
