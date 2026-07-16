"""Focused tests for Visma write-safety (mocked HTTP only)."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi import HTTPException

# Lightweight DB stubs for imports that pull psycopg2.
import types as _types

_pg_mock = _types.ModuleType("psycopg2")
sys.modules.setdefault("psycopg2", _pg_mock)
sys.modules.setdefault("psycopg2.extensions", MagicMock())
sys.modules.setdefault("psycopg2.extras", MagicMock())
_db_mod = _types.ModuleType("app.repositories.postgres.database")
_db_mod.Base = MagicMock()
_db_mod.SessionLocal = MagicMock()
_db_mod.engine = MagicMock()
sys.modules.setdefault("app.repositories.postgres.database", _db_mod)
_session_mod = _types.ModuleType("app.repositories.postgres.session")
_session_mod.engine = MagicMock()
_session_mod.SessionLocal = MagicMock()
sys.modules.setdefault("app.repositories.postgres.session", _session_mod)

from app.integrations.dispatcher import IntegrationDispatcher
from app.integrations.enums import IntegrationType
from app.integrations.visma.token_resolver import (
    VismaNotConnectedError,
    VismaProviderDisabledError,
    VismaRefreshFailedError,
    VismaTenantMismatchError,
    resolve_visma_access_token,
)
from app.main import (
    FinanceVismaExportRequest,
    VISMA_EXPORT_ACTION,
    _execute_finance_visma_export,
    _resolve_finance_visma_approval,
    finance_visma_export,
    finance_visma_export_preview,
)


def _invoice_record() -> SimpleNamespace:
    return SimpleNamespace(
        job_id="job_visma_1",
        tenant_id="TENANT_A",
        job_type="invoice",
        input_data={
            "subject": "Faktura 2024-2001",
            "message_text": "Belopp exkl moms 1000 kr. Moms 250 kr. Totalt 1250 kr.",
            "sender": {"name": "Leverantor AB", "email": "ekonomi@leverantor.se"},
        },
        processor_history=[
            {
                "processor": "invoice_processor",
                "result": {
                    "payload": {
                        "invoice_data": {
                            "invoice_number": "2024-2001",
                            "due_date": "2026-05-30",
                        }
                    }
                },
            }
        ],
    )


def _oauth_record(
    *,
    tenant_id: str = "TENANT_A",
    access_token: str = "tenant-at",
    refresh_token: str = "tenant-rt",
    expires_at: datetime | None = None,
):
    return SimpleNamespace(
        tenant_id=tenant_id,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at or datetime.now(timezone.utc) + timedelta(hours=1),
        scopes="ea:api offline_access",
    )


def _approved_approval():
    return SimpleNamespace(
        approval_id="finance_visma_export:TENANT_A:job_visma_1",
        tenant_id="TENANT_A",
        job_id="job_visma_1",
        job_type="invoice",
        request_payload={
            "state": "approved",
            "next_on_approve": VISMA_EXPORT_ACTION,
            "finance_context": {
                "job_id": "job_visma_1",
                "action": VISMA_EXPORT_ACTION,
            },
        },
        delivery_payload={
            "draft": {},
            "visma_payload": {
                "customer": {"name": "Leverantor AB"},
                    "invoice": {
                        "CustomerNumber": "C-1",
                        "Rows": [{"Text": "Line", "Quantity": 1, "UnitPrice": 100}],
                    },
            },
            "create_customer_if_missing": True,
        },
    )


class TestVismaTokenResolver:
    @patch("app.integrations.visma.token_resolver.OAuthCredentialRepository")
    def test_uses_tenant_oauth_credential(self, mock_repo):
        mock_repo.get.return_value = _oauth_record()
        token = resolve_visma_access_token(MagicMock(), "TENANT_A")
        assert token == "tenant-at"
        mock_repo.get.assert_called_once()
        assert mock_repo.get.call_args.args[1:] == ("TENANT_A", "visma")

    @patch("app.integrations.visma.token_resolver.OAuthCredentialRepository")
    def test_never_uses_global_env_token(self, mock_repo):
        mock_repo.get.return_value = None
        with pytest.raises(VismaNotConnectedError):
            resolve_visma_access_token(MagicMock(), "TENANT_A")

    @patch("app.integrations.visma.token_resolver.refresh_access_token")
    @patch("app.integrations.visma.token_resolver.OAuthCredentialRepository")
    def test_refreshes_expired_token_and_persists(self, mock_repo, mock_refresh):
        expired = _oauth_record(
            access_token="old-at",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        mock_repo.get.return_value = expired
        mock_refresh.return_value = {
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "scopes": "ea:api",
        }
        token = resolve_visma_access_token(MagicMock(), "TENANT_A")
        assert token == "new-at"
        mock_repo.upsert.assert_called_once()

    @patch("app.integrations.visma.token_resolver.OAuthCredentialRepository")
    def test_missing_credential_fails_closed(self, mock_repo):
        mock_repo.get.return_value = None
        with pytest.raises(VismaNotConnectedError):
            resolve_visma_access_token(MagicMock(), "TENANT_A")

    @patch("app.integrations.visma.token_resolver.OAuthCredentialRepository")
    def test_tenant_isolation(self, mock_repo):
        mock_repo.get.return_value = _oauth_record(tenant_id="TENANT_B")
        with pytest.raises(VismaTenantMismatchError):
            resolve_visma_access_token(MagicMock(), "TENANT_A")

    @patch("app.integrations.policies.is_integration_enabled_for_tenant", return_value=False)
    def test_visma_disabled_in_allowlist(self, _mock_enabled):
        with pytest.raises(VismaProviderDisabledError):
            resolve_visma_access_token(
                MagicMock(),
                "TENANT_A",
                check_allowlist=True,
            )

    @patch("app.integrations.visma.token_resolver.refresh_access_token", side_effect=RuntimeError("refresh"))
    @patch("app.integrations.visma.token_resolver.OAuthCredentialRepository")
    def test_refresh_failure_classified(self, mock_repo, _mock_refresh):
        mock_repo.get.return_value = _oauth_record(
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        with pytest.raises(VismaRefreshFailedError):
            resolve_visma_access_token(MagicMock(), "TENANT_A")


class TestVismaFinanceExportGates:
    def test_preview_does_not_write(self):
        record = _invoice_record()
        with patch("app.main._get_invoice_record_or_422", return_value=record):
            response = finance_visma_export_preview(
                "job_visma_1",
                db=MagicMock(),
                tenant_id="TENANT_A",
            )
        assert response["status"] == "preview"
        assert "visma_payload" in response

    def test_export_dry_run_avoids_external_calls(self):
        record = _invoice_record()
        with patch("app.main._get_invoice_record_or_422", return_value=record), patch(
            "app.main._get_visma_adapter_for_tenant"
        ) as mock_adapter:
            response = finance_visma_export(
                "job_visma_1",
                body=FinanceVismaExportRequest(dry_run=True),
                db=MagicMock(),
                tenant_id="TENANT_A",
            )
        assert response["status"] == "dry_run"
        mock_adapter.assert_not_called()

    def test_missing_approval_queues_approval_required(self):
        record = _invoice_record()
        approval = SimpleNamespace(approval_id="finance_visma_export:TENANT_A:job_visma_1")
        with patch("app.main._get_invoice_record_or_422", return_value=record), patch(
            "app.main._require_visma_enabled_for_tenant"
        ), patch("app.main._get_successful_finance_visma_export_event", return_value=None), patch(
            "app.main._get_finance_visma_approval_record", return_value=None
        ), patch(
            "app.main._create_finance_visma_approval",
            return_value=approval,
        ) as create_mock, patch("app.main._get_visma_adapter_for_tenant") as adapter_mock:
            response = finance_visma_export(
                "job_visma_1",
                body=FinanceVismaExportRequest(),
                db=MagicMock(),
                tenant_id="TENANT_A",
            )
        assert response["status"] == "approval_required"
        create_mock.assert_called_once()
        adapter_mock.assert_not_called()

    def test_pending_approval_rejected(self):
        record = _invoice_record()
        pending = SimpleNamespace(
            request_payload={"state": "pending", "next_on_approve": VISMA_EXPORT_ACTION}
        )
        with patch("app.main._get_invoice_record_or_422", return_value=record), patch(
            "app.main._require_visma_enabled_for_tenant"
        ), patch("app.main._get_successful_finance_visma_export_event", return_value=None), patch(
            "app.main._get_finance_visma_approval_record", return_value=pending
        ):
            with pytest.raises(HTTPException) as exc:
                finance_visma_export(
                    "job_visma_1",
                    body=FinanceVismaExportRequest(),
                    db=MagicMock(),
                    tenant_id="TENANT_A",
                )
        assert exc.value.status_code == 409

    def test_rejected_approval_blocks_export(self):
        record = _invoice_record()
        rejected = SimpleNamespace(
            request_payload={"state": "rejected", "next_on_approve": VISMA_EXPORT_ACTION}
        )
        with patch("app.main._get_invoice_record_or_422", return_value=record), patch(
            "app.main._require_visma_enabled_for_tenant"
        ), patch("app.main._get_successful_finance_visma_export_event", return_value=None), patch(
            "app.main._get_finance_visma_approval_record", return_value=rejected
        ):
            with pytest.raises(HTTPException) as exc:
                finance_visma_export(
                    "job_visma_1",
                    body=FinanceVismaExportRequest(),
                    db=MagicMock(),
                    tenant_id="TENANT_A",
                )
        assert exc.value.status_code == 403

    def test_wrong_action_approval_rejected_on_execute(self):
        approval = _approved_approval()
        approval.request_payload["next_on_approve"] = "finance_fortnox_export"
        with patch("app.main._require_visma_enabled_for_tenant"), patch(
            "app.main._execute_finance_visma_export"
        ) as execute_mock, patch("app.main.ApprovalRequestRepository.upsert_from_payload"):
            with pytest.raises(HTTPException) as exc:
                _resolve_finance_visma_approval(
                    db=MagicMock(),
                    approval=approval,
                    approved=True,
                    actor="operator",
                    note=None,
                )
        assert exc.value.status_code == 403
        execute_mock.assert_not_called()

    def test_visma_disabled_blocks_export(self):
        record = _invoice_record()
        with patch("app.main._get_invoice_record_or_422", return_value=record), patch(
            "app.main._require_visma_enabled_for_tenant",
            side_effect=HTTPException(status_code=403, detail="disabled"),
        ):
            with pytest.raises(HTTPException) as exc:
                finance_visma_export(
                    "job_visma_1",
                    body=FinanceVismaExportRequest(),
                    db=MagicMock(),
                    tenant_id="TENANT_A",
                )
        assert exc.value.status_code == 403


class TestVismaExportExecution:
    def test_approved_export_uses_tenant_token_and_stores_external_id(self):
        db = MagicMock()
        adapter = MagicMock()
        adapter.execute_action.side_effect = [
            {"result": {"id": "INV-77"}},
        ]
        event = SimpleNamespace(id=11, payload={}, status="executing", idempotency_key="k")
        with patch("app.main._get_successful_finance_visma_export_event", return_value=None), patch(
            "app.main._get_visma_adapter_for_tenant",
            return_value=adapter,
        ), patch("app.main._claim_finance_visma_export_event", return_value=(event, None)), patch(
            "app.main._finalize_finance_visma_event"
        ), patch("app.main._record_finance_visma_audit"):
            response = _execute_finance_visma_export(
                db=db,
                tenant_id="TENANT_A",
                job_id="job_visma_1",
                draft={},
                export_payload={
                    "customer": {"Name": "Leverantor AB"},
                    "invoice": {
                        "CustomerNumber": "C-1",
                        "Rows": [{"Text": "Line", "Quantity": 1, "UnitPrice": 100}],
                    },
                },
                create_customer_if_missing=False,
            )
        assert response["status"] == "exported"
        assert response["external_invoice_id"] == "INV-77"
        adapter.execute_action.assert_called_once_with(
            action="create_invoice",
            payload={"invoice": {"CustomerNumber": "C-1", "Rows": [{"Text": "Line", "Quantity": 1, "UnitPrice": 100}]}},
        )

    def test_duplicate_export_rejected(self):
        existing = SimpleNamespace(
            id=1,
            status="success",
            idempotency_key="finance:visma_export:TENANT_A:job_visma_1",
            payload={"result": {"external_invoice_id": "INV-1"}},
        )
        with patch(
            "app.main._get_successful_finance_visma_export_event",
            return_value=existing,
        ):
            response = _execute_finance_visma_export(
                db=MagicMock(),
                tenant_id="TENANT_A",
                job_id="job_visma_1",
                draft={},
                export_payload={
                    "customer": {"name": "A"},
                    "invoice": {"CustomerNumber": "C-1", "Rows": [{"Text": "x"}]},
                },
                create_customer_if_missing=False,
            )
        assert response["status"] == "already_exported"

    def test_concurrent_export_rejected(self):
        with patch("app.main._get_successful_finance_visma_export_event", return_value=None), patch(
            "app.main._get_visma_adapter_for_tenant",
            return_value=MagicMock(),
        ), patch(
            "app.main._claim_finance_visma_export_event",
            side_effect=HTTPException(status_code=409, detail="in progress"),
        ):
            with pytest.raises(HTTPException) as exc:
                _execute_finance_visma_export(
                    db=MagicMock(),
                    tenant_id="TENANT_A",
                    job_id="job_visma_1",
                    draft={},
                    export_payload={
                        "customer": {"name": "A"},
                        "invoice": {"CustomerNumber": "C-1", "Rows": [{"Text": "x"}]},
                    },
                    create_customer_if_missing=False,
                )
        assert exc.value.status_code == 409

    def test_api_failure_audited(self):
        event = SimpleNamespace(id=3, payload={}, status="executing")
        adapter = MagicMock()
        adapter.execute_action.side_effect = requests.HTTPError("502")
        with patch("app.main._get_successful_finance_visma_export_event", return_value=None), patch(
            "app.main._get_visma_adapter_for_tenant",
            return_value=adapter,
        ), patch("app.main._claim_finance_visma_export_event", return_value=(event, None)), patch(
            "app.main._finalize_finance_visma_event"
        ) as finalize_mock, patch("app.main._record_finance_visma_audit") as audit_mock:
            with pytest.raises(HTTPException):
                _execute_finance_visma_export(
                    db=MagicMock(),
                    tenant_id="TENANT_A",
                    job_id="job_visma_1",
                    draft={},
                    export_payload={
                        "customer": {"name": "A"},
                        "invoice": {"CustomerNumber": "C-1", "Rows": [{"Text": "x"}]},
                    },
                    create_customer_if_missing=False,
                )
        finalize_mock.assert_called()
        audit_mock.assert_called()
        assert finalize_mock.call_args.kwargs["status"] == "failed"

    def test_unknown_network_result_requires_reconciliation(self):
        event = SimpleNamespace(id=4, payload={}, status="executing")
        adapter = MagicMock()
        adapter.execute_action.side_effect = requests.Timeout("timeout")
        with patch("app.main._get_successful_finance_visma_export_event", return_value=None), patch(
            "app.main._get_visma_adapter_for_tenant",
            return_value=adapter,
        ), patch("app.main._claim_finance_visma_export_event", return_value=(event, None)), patch(
            "app.main._finalize_finance_visma_event"
        ) as finalize_mock:
            with pytest.raises(HTTPException) as exc:
                _execute_finance_visma_export(
                    db=MagicMock(),
                    tenant_id="TENANT_A",
                    job_id="job_visma_1",
                    draft={},
                    export_payload={
                        "customer": {"name": "A"},
                        "invoice": {"CustomerNumber": "C-1", "Rows": [{"Text": "x"}]},
                    },
                    create_customer_if_missing=False,
                )
        assert exc.value.status_code == 503
        assert finalize_mock.call_args.kwargs["status"] == "reconciliation_required"

    def test_rejected_approval_does_not_export(self):
        approval = _approved_approval()
        approval.request_payload["state"] = "pending"
        with patch("app.main._execute_finance_visma_export") as execute_mock, patch(
            "app.main.ApprovalRequestRepository.upsert_from_payload"
        ):
            response = _resolve_finance_visma_approval(
                db=MagicMock(),
                approval=approval,
                approved=False,
                actor="operator",
                note="no",
            )
        assert response["status"] == "rejected"
        execute_mock.assert_not_called()


class TestDispatcherVismaSafety:
    def test_dispatcher_does_not_auto_write_visma(self):
        import asyncio

        db = MagicMock()
        repo = MagicMock()
        event = SimpleNamespace(
            integration_type="visma",
            status="failed",
            attempts=0,
            tenant_id="TENANT_A",
            job_id="job-1",
            payload={},
            last_error=None,
        )
        dispatcher = IntegrationDispatcher(db)
        dispatcher.repo = repo
        asyncio.run(dispatcher._execute(event))
        assert event.status == "dead"
        assert "finance_export" in event.last_error
        repo.update.assert_called()

    def test_invoice_processing_skips_visma_dispatch(self):
        import asyncio
        from unittest.mock import AsyncMock

        job = SimpleNamespace(
            tenant_id="TENANT_A",
            job_type="invoice_processing",
            id="job-1",
            processor_history=[],
            input_data={},
        )
        dispatcher = IntegrationDispatcher(MagicMock())
        dispatcher._handle = AsyncMock()

        with patch(
            "app.integrations.dispatcher.is_integration_enabled_for_tenant",
            return_value=True,
        ):
            asyncio.run(dispatcher.dispatch(job))

        called_types = [
            call.args[1]
            for call in dispatcher._handle.call_args_list
        ]
        assert IntegrationType.VISMA not in called_types


class TestGenericVismaExecuteBlocked:
    def test_integrations_execute_blocks_visma(self):
        from app.integrations.schemas import IntegrationActionRequest
        from app.main import execute_integration_action

        with pytest.raises(HTTPException) as exc:
            execute_integration_action(
                IntegrationType.VISMA,
                IntegrationActionRequest(action="create_invoice", payload={}),
                db=MagicMock(),
                tenant_id="TENANT_A",
            )
        assert exc.value.status_code == 403
