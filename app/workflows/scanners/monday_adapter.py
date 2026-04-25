"""
Monday.com workflow scanner adapter.

Reads board structure (boards → groups + columns) from the Monday API.
Read-only: does NOT create boards, items, or groups. Does NOT auto-route.

Populated output (system_map.monday)
-------------------------------------
boards   : list of board objects with nested groups/columns + detected_purpose
groups   : flattened list of all groups across all boards (for easy lookup)
columns  : flattened list of all columns across all boards (for easy lookup)

Summary (workflow_scan.summary.monday)
---------------------------------------
boards_scanned         : int
groups_detected        : int
columns_detected       : int
detected_purposes      : sorted unique list of detected board purposes
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from app.workflows.scanners.base import BaseWorkflowScannerAdapter, ScanResult
from app.core.settings import get_settings

# ---------------------------------------------------------------------------
# Board purpose detection — deterministic, keyword-based
# ---------------------------------------------------------------------------

_PURPOSE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("lead",             ["lead", "leads", "sales", "sälj", "offert", "quote", "prospect", "prospekt"]),
    ("customer_inquiry", ["inquiry", "inquiries", "kundfråga", "request", "kontakt", "frågor", "ärende"]),
    ("invoice",          ["invoice", "invoices", "faktura", "fakturor", "ekonomi", "billing", "payment", "betalning"]),
    ("support",          ["support", "helpdesk", "service", "ticket", "tickets", "ärenden", "serviceärende"]),
    ("partnership",      ["partner", "partnership", "samarbete", "samarbeten", "collaboration"]),
    ("supplier",         ["supplier", "vendor", "leverantör", "purchase", "inköp", "order"]),
    ("internal",         ["internal", "intern", "admin", "operations", "drift", "internt"]),
]


def detect_board_purpose(board: dict) -> str:
    """
    Deterministic keyword scan of board name, description, group titles,
    and column titles.  Returns first matching purpose or "unknown".
    """
    tokens: list[str] = []
    tokens.append((board.get("name") or "").lower())
    tokens.append((board.get("description") or "").lower())
    for g in board.get("groups") or []:
        tokens.append((g.get("title") or "").lower())
    for c in board.get("columns") or []:
        tokens.append((c.get("title") or "").lower())

    combined = " ".join(tokens)

    for purpose, keywords in _PURPOSE_KEYWORDS:
        if any(kw in combined for kw in keywords):
            return purpose

    return "unknown"


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

BOARDS_LIMIT = 50


def _build_monday_client(settings):
    """Construct a MondayClient from app settings. Returns None if not configured."""
    from app.integrations.monday.client import MondayClient

    api_key = getattr(settings, "MONDAY_API_KEY", "") or ""
    api_url = getattr(settings, "MONDAY_API_URL", "https://api.monday.com/v2") or "https://api.monday.com/v2"

    if not api_key.strip():
        return None

    return MondayClient(api_key=api_key, api_url=api_url)


def analyse_boards(raw_boards: list[dict]) -> tuple[dict, dict]:
    """
    Pure analysis function — no network or DB I/O.
    Returns (monday_system_map, monday_summary).
    Public so it can be tested and imported without the adapter.
    """
    boards_out: list[dict] = []
    flat_groups: list[dict] = []
    flat_columns: list[dict] = []
    detected_purposes: list[str] = []

    for b in raw_boards:
        board_id   = str(b.get("id") or "")
        board_name = b.get("name") or ""
        board_desc = b.get("description") or ""
        groups     = b.get("groups") or []
        columns    = b.get("columns") or []

        purpose = detect_board_purpose(b)
        if purpose not in detected_purposes:
            detected_purposes.append(purpose)

        boards_out.append({
            "id":               board_id,
            "name":             board_name,
            "description":      board_desc,
            "groups":           [{"id": g.get("id", ""), "title": g.get("title", "")} for g in groups],
            "columns":          [{"id": c.get("id", ""), "title": c.get("title", ""), "type": c.get("type", "")} for c in columns],
            "detected_purpose": purpose,
        })

        for g in groups:
            flat_groups.append({
                "board_id":   board_id,
                "board_name": board_name,
                "id":         g.get("id", ""),
                "title":      g.get("title", ""),
            })

        for c in columns:
            flat_columns.append({
                "board_id":   board_id,
                "board_name": board_name,
                "id":         c.get("id", ""),
                "title":      c.get("title", ""),
                "type":       c.get("type", ""),
            })

    monday_map = {
        "boards":  boards_out,
        "groups":  flat_groups,
        "columns": flat_columns,
    }

    monday_summary = {
        "boards_scanned":    len(boards_out),
        "groups_detected":   len(flat_groups),
        "columns_detected":  len(flat_columns),
        "detected_purposes": sorted(detected_purposes),
    }

    return monday_map, monday_summary


class MondayWorkflowScannerAdapter(BaseWorkflowScannerAdapter):
    system_key = "monday"

    def run(self, db: Any, tenant_id: str) -> ScanResult:
        scanned_at = datetime.now(timezone.utc).isoformat()
        settings = get_settings()

        client = _build_monday_client(settings)
        if client is None:
            return ScanResult(
                system="monday",
                status="failed",
                scanned_at=scanned_at,
                error="Monday API key not configured (MONDAY_API_KEY is empty).",
            )

        raw_boards = client.get_boards(limit=BOARDS_LIMIT)
        monday_map, monday_summary = analyse_boards(raw_boards)

        return ScanResult(
            system="monday",
            status="completed",
            scanned_at=scanned_at,
            data=monday_map,
            summary=monday_summary,
        )
