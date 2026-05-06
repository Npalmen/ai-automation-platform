from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.automation.wow_flows import build_automation_case_payload
from app.main import get_case_automation_wow


def _record(
    *,
    job_type: str = "lead",
    status: str = "completed",
    input_data: dict | None = None,
    history: list[dict] | None = None,
):
    return SimpleNamespace(
        job_id="job_wow_1",
        tenant_id="TENANT_1001",
        job_type=job_type,
        status=status,
        input_data=input_data or {
            "subject": "Ny offertforfragan",
            "sender": {"name": "Kund AB", "email": "kund@example.com"},
        },
        result={"processor_history": history or []},
        created_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
        updated_at=datetime(2026, 5, 6, tzinfo=timezone.utc),
    )


def _lead_history(missing_fields: list[str] | None = None):
    return [
        {
            "processor": "lead_analyzer_processor",
            "result": {
                "payload": {
                    "lead_analysis": {"lead_type": "solar", "intent": "ready_to_buy"},
                    "missing_info": {
                        "missing_fields": missing_fields or [],
                        "completeness_score": 0.8,
                    },
                    "lead_score": {"score": 82, "category": "hot"},
                    "next_action": "create_offer_draft",
                }
            },
        },
        {
            "processor": "action_dispatch_processor",
            "result": {"payload": {"ai_reply_suggestions": [{"subject": "Re: offert"}]}},
        },
    ]


def test_automation_payload_builds_summary_risks_and_three_wow_flows():
    record = _record(history=_lead_history())
    action = SimpleNamespace(status="success", action_type="send_customer_auto_reply", error_message=None)

    payload = build_automation_case_payload(record, action_records=[action], approval_records=[])

    assert payload["summary"]["status"] == "ready"
    assert payload["summary"]["next_step"] == "create offer draft"
    assert payload["risks"]["status"] == "ok"
    assert [f["id"] for f in payload["wow_flows"]] == [
        "approved_customer_reply",
        "case_to_project_handoff",
        "project_to_invoice_ready",
    ]
    assert all(flow["external_writes"] is False for flow in payload["wow_flows"])


def test_risk_detection_flags_failed_action_and_missing_customer_info():
    record = _record(history=_lead_history(missing_fields=["budget", "address"]))
    failed_action = SimpleNamespace(
        status="failed",
        action_type="create_monday_item",
        error_message="timeout",
    )

    payload = build_automation_case_payload(record, action_records=[failed_action])
    codes = {risk["code"] for risk in payload["risks"]["risks"]}

    assert payload["summary"]["status"] == "needs_attention"
    assert payload["risks"]["status"] == "risk"
    assert {"action_failed", "missing_customer_info"}.issubset(codes)


def test_project_invoice_flow_is_ready_only_after_completed_delivery_and_revenue():
    record = _record(
        job_type="lead",
        input_data={
            "subject": "Projekt klart",
            "sender": {"email": "kund@example.com"},
            "operations_workspace": {
                "work_order": {"status": "completed"},
                "delivery_package": {"status": "ready"},
                    "documentation": {"documents": [{"name": "Leveransunderlag"}]},
                "finance": {"estimated_revenue": 50000, "material_cost": 10000},
            },
        },
    )

    payload = build_automation_case_payload(record)
    invoice_flow = next(flow for flow in payload["wow_flows"] if flow["id"] == "project_to_invoice_ready")

    assert invoice_flow["status"] == "ready"
    assert invoice_flow["requires_approval"] is True


def test_project_risk_flags_low_margin():
    record = _record(
        input_data={
            "subject": "Svagt projekt",
            "sender": {"email": "kund@example.com"},
            "operations_workspace": {
                "finance": {"estimated_revenue": 10000, "material_cost": 9500},
            },
        },
    )

    payload = build_automation_case_payload(record)

    assert any(risk["code"] == "low_margin" for risk in payload["risks"]["risks"])


def test_case_automation_wow_endpoint_returns_preview_payload():
    record = _record(history=_lead_history())
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.order_by.return_value = q
    q.first.return_value = record
    q.all.return_value = []

    with patch("app.main.ApprovalRequestRepository.list_for_job", return_value=[]):
        response = get_case_automation_wow("job_wow_1", db=db, tenant_id="TENANT_1001")

    assert response["job_id"] == "job_wow_1"
    assert "summary" in response
    assert "risks" in response
    assert len(response["wow_flows"]) == 3


def test_case_automation_wow_endpoint_404_for_missing_case():
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.first.return_value = None

    with pytest.raises(HTTPException) as exc:
        get_case_automation_wow("missing", db=db, tenant_id="TENANT_1001")

    assert exc.value.status_code == 404
