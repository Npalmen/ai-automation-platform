from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.main import (
    _extract_material_lines,
    _is_finance_draft_available,
    build_finance_invoice_draft,
    get_case,
)


def _invoice_record(**overrides) -> SimpleNamespace:
    defaults = dict(
        job_id="job_micro_1",
        tenant_id="TENANT_MICRO",
        job_type="invoice",
        status="completed",
        created_at=None,
        updated_at=None,
        input_data={
            "subject": "Faktura 2024-999",
            "message_text": "Exkl moms 2000 kr. Totalt 2500 kr.",
            "sender": {"name": "Test AB", "email": "test@test.se"},
            "operations_workspace": {
                "finance": {
                    "material_costs": [
                        {
                            "description": "Kabel 3x2.5",
                            "quantity": 10,
                            "unit_price": 45.0,
                        },
                        {
                            "description": "Dosa",
                            "quantity": 2,
                            "unit_price": 120.0,
                            "vat_rate": 25,
                        },
                    ]
                },
                "work_order": {"status": "completed"},
            },
        },
        result={},
        processor_history=[
            {
                "processor": "invoice_processor",
                "result": {
                    "payload": {
                        "invoice_data": {"invoice_number": "2024-999"}
                    }
                },
            }
        ],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Improvement 1: Material line normalization
# ---------------------------------------------------------------------------


def test_material_lines_extracted_with_data():
    input_data = _invoice_record().input_data
    lines = _extract_material_lines(input_data)

    assert len(lines) == 2
    assert lines[0]["description"] == "Kabel 3x2.5"
    assert lines[0]["quantity"] == 10.0
    assert lines[0]["unit_price"] == 45.0
    assert lines[0]["total"] == 450.0
    assert lines[0]["vat_rate"] == 25

    assert lines[1]["description"] == "Dosa"
    assert lines[1]["total"] == 240.0


def test_material_lines_empty_when_no_data():
    input_data = {"subject": "No workspace here"}
    assert _extract_material_lines(input_data) == []


def test_material_lines_empty_when_finance_has_no_materials():
    input_data = {"operations_workspace": {"finance": {"estimated_revenue": 5000}}}
    assert _extract_material_lines(input_data) == []


def test_material_lines_falls_back_to_materials_key():
    """When material_costs is absent, fall back to 'materials' key."""
    input_data = {
        "operations_workspace": {
            "finance": {
                "materials": [
                    {"name": "Wire", "cost": 300},
                ]
            }
        }
    }
    lines = _extract_material_lines(input_data)
    assert len(lines) == 1
    assert lines[0]["description"] == "Wire"
    assert lines[0]["unit_price"] == 300.0
    assert lines[0]["quantity"] == 1.0
    assert lines[0]["total"] == 300.0


def test_draft_endpoint_includes_material_lines():
    record = _invoice_record()
    with patch("app.main._get_invoice_record_or_422", return_value=record):
        response = build_finance_invoice_draft(
            "job_micro_1", db=MagicMock(), tenant_id="TENANT_MICRO"
        )
    assert response["status"] == "ok"
    assert "material_lines" in response
    assert len(response["material_lines"]) == 2


def test_draft_endpoint_material_lines_empty_without_workspace():
    record = _invoice_record(
        input_data={
            "subject": "Faktura enkel",
            "message_text": "Exkl moms 500 kr",
            "sender": {"name": "A"},
        }
    )
    with patch("app.main._get_invoice_record_or_422", return_value=record):
        response = build_finance_invoice_draft(
            "job_micro_1", db=MagicMock(), tenant_id="TENANT_MICRO"
        )
    assert response["material_lines"] == []


# ---------------------------------------------------------------------------
# Improvement 2: Draft-to-case link
# ---------------------------------------------------------------------------


def test_finance_draft_available_when_job_completed():
    record = SimpleNamespace(status="completed")
    assert _is_finance_draft_available(record, {}) is True


def test_finance_draft_available_when_work_order_completed():
    record = SimpleNamespace(status="in_progress")
    inp = {"operations_workspace": {"work_order": {"status": "completed"}}}
    assert _is_finance_draft_available(record, inp) is True


def test_finance_draft_not_available_when_incomplete():
    record = SimpleNamespace(status="in_progress")
    inp = {"operations_workspace": {"work_order": {"status": "new"}}}
    assert _is_finance_draft_available(record, inp) is False


def test_finance_draft_not_available_without_workspace():
    record = SimpleNamespace(status="queued")
    assert _is_finance_draft_available(record, {}) is False


def test_case_detail_includes_finance_draft_fields():
    record = _invoice_record()
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.first.return_value = record
    q.order_by.return_value = q
    q.all.return_value = []

    with patch("app.main.ApprovalRequestRepository") as mock_approval, \
         patch("app.workflows.scanners.routing_preview.resolve_routing_preview", return_value=None), \
         patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={}), \
         patch("app.main._get_memory", return_value={"routing_hints": {}}), \
         patch("app.main.build_automation_case_payload", return_value={
             "summary": None, "risks": [], "wow_flows": [],
         }):
        mock_approval.list_for_job.return_value = []
        response = get_case("job_micro_1", db=db, tenant_id="TENANT_MICRO")

    assert response["finance_draft_available"] is True
    assert response["finance_draft_url"] == "/finance/invoices/job_micro_1/draft"
