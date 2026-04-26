"""
Monday Lead Dispatch Adapter.

Dispatches a lead job to a Monday.com board identified by routing_hint.target.board_id.
Creates one item per job — idempotency is handled by the engine layer.

Item name priority:
  1. company_name  (from entity extraction)
  2. customer_name (from entity extraction)
  3. sender_name   (from input_data.sender.name)
  4. sender_email  (from input_data.sender.email)
  5. subject       (from input_data.subject)
  6. "New lead"
"""

from __future__ import annotations

from typing import Any

from app.core.settings import get_settings
from app.workflows.dispatchers.base import BaseDispatchAdapter, DispatchResult


def _derive_item_name(job: Any) -> str:
    """Extract the best available label for the Monday item name."""
    inp    = getattr(job, "input_data", None) or {}
    result = getattr(job, "result", None) or {}

    # Walk processor_history for entity extraction output
    history = (result.get("processor_history") or []) if isinstance(result, dict) else []
    entities: dict = {}
    for entry in history:
        p = (entry.get("result") or {}).get("payload") or {}
        if "entities" in p:
            entities = p["entities"] or {}
            break

    company_name  = entities.get("company_name") or ""
    customer_name = entities.get("customer_name") or ""

    sender = inp.get("sender") or {} if isinstance(inp, dict) else {}
    sender_name  = sender.get("name") or (inp.get("sender_name") or "") if isinstance(inp, dict) else ""
    sender_email = sender.get("email") or (inp.get("sender_email") or "") if isinstance(inp, dict) else ""
    subject      = (inp.get("subject") or "") if isinstance(inp, dict) else ""

    for candidate in (company_name, customer_name, sender_name, sender_email, subject):
        if candidate and candidate.strip():
            return candidate.strip()

    return "New lead"


def _derive_column_values(job: Any) -> dict:
    """Build a minimal column_values dict from available job data."""
    inp    = getattr(job, "input_data", None) or {}
    result = getattr(job, "result", None) or {}

    history = (result.get("processor_history") or []) if isinstance(result, dict) else []
    entities: dict = {}
    for entry in history:
        p = (entry.get("result") or {}).get("payload") or {}
        if "entities" in p:
            entities = p["entities"] or {}
            break

    sender = inp.get("sender") or {} if isinstance(inp, dict) else {}
    email  = (entities.get("email") or sender.get("email") or inp.get("sender_email") or "") if isinstance(inp, dict) else ""
    phone  = entities.get("phone") or ""

    cv: dict = {}
    if email:
        cv["email"] = {"email": email, "text": email}
    if phone:
        cv["phone"] = {"phone": phone, "countryShortName": "SE"}

    return cv


class MondayLeadDispatchAdapter(BaseDispatchAdapter):
    system_key   = "monday"
    job_type_key = "lead"

    def dispatch(
        self,
        job: Any,
        routing_hint: dict,
        settings: Any,
        dry_run: bool = False,
    ) -> DispatchResult:
        from app.core.settings import get_settings

        target    = routing_hint.get("target") or {}
        board_id  = str(target.get("board_id") or "")
        board_name = target.get("board_name") or board_id
        group_id  = target.get("group_id") or None

        item_name     = _derive_item_name(job)
        column_values = _derive_column_values(job)

        if dry_run:
            return DispatchResult(
                status="dry_run",
                system="monday",
                job_type="lead",
                target=target,
                message=f"Skulle skapa ärende i Monday board {board_name}: '{item_name}'",
                details={
                    "board_id":   board_id,
                    "board_name": board_name,
                    "item_name":  item_name,
                    "group_id":   group_id,
                },
            )

        cfg = get_settings()
        api_key = getattr(cfg, "MONDAY_API_KEY", "") or ""
        api_url = getattr(cfg, "MONDAY_API_URL", "https://api.monday.com/v2") or "https://api.monday.com/v2"

        if not api_key.strip():
            return DispatchResult(
                status="failed",
                system="monday",
                job_type="lead",
                target=target,
                message="Monday API key not configured (MONDAY_API_KEY is empty)",
            )

        from app.integrations.monday.client import MondayClient
        client = MondayClient(api_key=api_key, api_url=api_url)

        try:
            resp = client.create_item(
                board_id=int(board_id),
                item_name=item_name,
                group_id=group_id,
                column_values=column_values or None,
            )
        except Exception as exc:
            return DispatchResult(
                status="failed",
                system="monday",
                job_type="lead",
                target=target,
                message=f"Monday API error: {str(exc)[:200]}",
            )

        created = (resp.get("data") or {}).get("create_item") or {}
        external_id = str(created.get("id") or "") or None

        return DispatchResult(
            status="success",
            system="monday",
            job_type="lead",
            target=target,
            external_id=external_id,
            message=f"Skapad i externt system: Monday board {board_name}, item '{item_name}'",
            details={
                "board_id":   board_id,
                "board_name": board_name,
                "item_name":  item_name,
                "item":       created,
            },
        )
