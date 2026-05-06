from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.finance.pre_accounting import build_invoice_draft
from app.main import (
    FinanceFortnoxExportRequest,
    _resolve_finance_fortnox_approval,
    build_finance_invoice_draft,
    finance_fortnox_export,
    finance_fortnox_export_preview,
    finance_project_profitability,
)


def _invoice_record() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job_fin_1",
        tenant_id="TENANT_1001",
        job_type="invoice",
        input_data={
            "subject": "Faktura 2024-1001",
            "message_text": (
                "Belopp exkl moms 1000 kr. Moms 250 kr. Totalt 1250 kr. "
                "Material och komponenter."
            ),
            "sender": {
                "name": "Leverantor AB",
                "email": "ekonomi@leverantor.se",
            },
        },
        processor_history=[
            {
                "processor": "invoice_processor",
                "result": {
                    "payload": {
                        "invoice_data": {
                            "invoice_number": "2024-1001",
                            "due_date": "2026-05-30",
                        }
                    }
                },
            }
        ],
    )


def test_build_invoice_draft_adds_vat_category_and_account():
    draft = build_invoice_draft(
        tenant_id="TENANT_1001",
        job_id="job_fin_1",
        input_data=_invoice_record().input_data,
        invoice_payload={"invoice_number": "2024-1001", "due_date": "2026-05-30"},
    )
    assert draft["invoice_number"] == "2024-1001"
    assert draft["amount_ex_vat"] == 1000.0
    assert draft["vat_amount"] == 250.0
    assert draft["amount_inc_vat"] == 1250.0
    assert draft["expense_category"] == "materials"
    assert draft["account_code_suggestion"] == "4010"
    assert draft["vat_rate"] == 25


def test_finance_draft_endpoint_returns_draft():
    record = _invoice_record()
    with patch("app.main._get_invoice_record_or_422", return_value=record):
        response = build_finance_invoice_draft("job_fin_1", db=MagicMock(), tenant_id="TENANT_1001")
    assert response["status"] == "ok"
    assert response["draft"]["invoice_number"] == "2024-1001"


def test_fortnox_preview_endpoint_returns_payload_without_write():
    record = _invoice_record()
    with patch("app.main._get_invoice_record_or_422", return_value=record):
        response = finance_fortnox_export_preview("job_fin_1", db=MagicMock(), tenant_id="TENANT_1001")
    assert response["status"] == "preview"
    assert "fortnox_payload" in response
    assert "invoice" in response["fortnox_payload"]
    assert "customer" in response["fortnox_payload"]


def test_fortnox_export_dry_run_avoids_external_calls():
    record = _invoice_record()
    with patch("app.main._get_invoice_record_or_422", return_value=record), patch(
        "app.main._get_fortnox_client_or_raise"
    ) as mock_client_builder:
        response = finance_fortnox_export(
            "job_fin_1",
            body=FinanceFortnoxExportRequest(dry_run=True),
            db=MagicMock(),
            tenant_id="TENANT_1001",
        )
    assert response["status"] == "dry_run"
    mock_client_builder.assert_not_called()


def test_fortnox_export_creates_customer_and_invoice_when_missing():
    record = _invoice_record()
    mock_client = MagicMock()
    mock_client.find_customer_by_email.return_value = None
    mock_client.find_customer_by_name.return_value = None
    mock_client.create_customer.return_value = {"Customer": {"CustomerNumber": "C100"}}
    mock_client.create_invoice.return_value = {"Invoice": {"DocumentNumber": "INV-1"}}

    with patch("app.main._get_invoice_record_or_422", return_value=record), patch(
        "app.main._get_fortnox_client_or_raise", return_value=mock_client
    ):
        response = finance_fortnox_export(
            "job_fin_1",
            body=FinanceFortnoxExportRequest(
                create_customer_if_missing=True,
                approval_required=False,
                dry_run=False,
            ),
            db=MagicMock(),
            tenant_id="TENANT_1001",
        )

    assert response["status"] == "exported"
    assert response["customer_created"] is True
    assert response["customer_number"] == "C100"
    mock_client.create_customer.assert_called_once()
    mock_client.create_invoice.assert_called_once()


def test_fortnox_export_uses_existing_customer_without_create():
    record = _invoice_record()
    mock_client = MagicMock()
    mock_client.find_customer_by_email.return_value = {"CustomerNumber": "EX-1"}
    mock_client.create_invoice.return_value = {"Invoice": {"DocumentNumber": "INV-2"}}

    with patch("app.main._get_invoice_record_or_422", return_value=record), patch(
        "app.main._get_fortnox_client_or_raise", return_value=mock_client
    ):
        response = finance_fortnox_export(
            "job_fin_1",
            body=FinanceFortnoxExportRequest(
                create_customer_if_missing=True,
                approval_required=False,
                dry_run=False,
            ),
            db=MagicMock(),
            tenant_id="TENANT_1001",
        )

    assert response["status"] == "exported"
    assert response["customer_created"] is False
    assert response["customer_number"] == "EX-1"
    mock_client.create_customer.assert_not_called()
    mock_client.create_invoice.assert_called_once()


def test_fortnox_export_defaults_to_approval_required_without_external_write():
    record = _invoice_record()
    db = MagicMock()
    approval = SimpleNamespace(approval_id="finance_fortnox_export:TENANT_1001:job_fin_1")
    with patch("app.main._get_invoice_record_or_422", return_value=record), patch(
        "app.main._create_finance_fortnox_approval", return_value=approval
    ) as approval_mock, patch("app.main._get_fortnox_client_or_raise") as mock_client_builder:
        response = finance_fortnox_export(
            "job_fin_1",
            body=FinanceFortnoxExportRequest(),
            db=db,
            tenant_id="TENANT_1001",
        )

    assert response["status"] == "approval_required"
    assert response["approval_id"] == "finance_fortnox_export:TENANT_1001:job_fin_1"
    approval_mock.assert_called_once()
    mock_client_builder.assert_not_called()


def test_project_profitability_calculates_margin_from_operations_workspace():
    record = SimpleNamespace(
        job_id="job_ops_fin_1",
        tenant_id="TENANT_1001",
        job_type="lead",
        input_data={
            "operations_workspace": {
                "finance": {
                    "estimated_revenue": 50000,
                    "materials": [{"cost": 12000}, {"cost": "3 000 kr"}],
                    "labor_hours": 20,
                    "labor_rate": 650,
                    "external_costs": [{"amount": 4000}],
                    "other_cost": 1000,
                }
            }
        },
        processor_history=[],
    )
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.first.return_value = record

    response = finance_project_profitability("job_ops_fin_1", db=db, tenant_id="TENANT_1001")

    profitability = response["profitability"]
    assert response["status"] == "ok"
    assert profitability["revenue"] == 50000.0
    assert profitability["costs"]["total"] == 33000.0
    assert profitability["margin_amount"] == 17000.0
    assert profitability["margin_percent"] == 34.0
    assert profitability["status"] == "healthy"


def test_finance_fortnox_approval_reject_does_not_export():
    approval = SimpleNamespace(
        approval_id="approval_fin_1",
        tenant_id="TENANT_1001",
        job_id="job_fin_1",
        job_type="invoice",
        request_payload={
            "approval_id": "approval_fin_1",
            "state": "pending",
            "next_on_approve": "finance_fortnox_export",
        },
        delivery_payload={"draft": {}, "fortnox_payload": {}},
    )
    db = MagicMock()
    with patch("app.main._execute_finance_fortnox_export") as execute_mock, patch(
        "app.main.ApprovalRequestRepository.upsert_from_payload"
    ) as upsert_mock:
        response = _resolve_finance_fortnox_approval(
            db=db,
            approval=approval,
            approved=False,
            actor="operator",
            note="Inte redo",
        )

    assert response["status"] == "rejected"
    assert response["export_result"] is None
    execute_mock.assert_not_called()
    saved_payload = upsert_mock.call_args.kwargs["approval_request"]
    assert saved_payload["state"] == "rejected"
    assert saved_payload["resolved_by"] == "operator"
