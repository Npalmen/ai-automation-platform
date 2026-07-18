"""
Tests for operator panel safe-write actions (Kapitel 5).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.admin.operator_actions import (
    OperatorActionConflictError,
    OperatorActionNotFoundError,
    OperatorActionValidationError,
    execute_approve_approval,
    execute_pause_automation,
    execute_reject_approval,
    execute_resume_automation,
    resolve_available_actions,
    tenant_detail_candidate_actions,
)
from app.core.audit_models import AuditEvent


def _operator(role: str = "operations") -> dict:
    return {
        "id": "operator-test",
        "display_name": "Test Operator",
        "role": role,
    }


def _mock_tenant_record(
    tenant_id: str = "T_TEST",
    *,
    demo_mode: bool = False,
    scheduler_mode: str = "scheduled",
) -> MagicMock:
    record = MagicMock()
    record.settings = {
        "automation": {"demo_mode": demo_mode},
        "scheduler": {"run_mode": scheduler_mode},
    }
    return record


def _valid_body(**overrides):
    body = {
        "reason": "OAuth-anslutningen måste återställas innan fortsatt drift.",
        "confirmation": True,
        "idempotency_key": "idem-1",
    }
    body.update(overrides)
    return body


class TestResolveAvailableActions:
    def test_read_only_gets_disabled_entries(self):
        actions = resolve_available_actions(
            tenant_detail_candidate_actions(False, False),
            "read_only",
            {"automation_paused": False, "scheduler_paused": False},
        )
        assert len(actions) == 2
        assert all(action.allowed is False for action in actions)
        assert all(action.blocked_reason == "insufficient_role" for action in actions)

    def test_state_invalid_actions_omitted(self):
        actions = resolve_available_actions(
            ["tenant.pause_automation"],
            "operations",
            {"automation_paused": True, "scheduler_paused": False},
        )
        assert actions == []

    def test_operations_allowed_for_applicable_actions(self):
        actions = resolve_available_actions(
            ["tenant.pause_automation"],
            "operations",
            {"automation_paused": False, "scheduler_paused": False},
        )
        assert len(actions) == 1
        assert actions[0].allowed is True
        assert actions[0].action_id == "tenant.pause_automation"


class TestPauseAutomation:
    def test_unknown_tenant_raises(self):
        db = MagicMock()
        with patch(
            "app.admin.operator_actions.TenantConfigRepository.get",
            return_value=None,
        ):
            with pytest.raises(OperatorActionNotFoundError):
                execute_pause_automation(
                    db,
                    "T_UNKNOWN",
                    operator=_operator(),
                    reason="test",
                    idempotency_key="k1",
                )

    def test_already_paused_returns_no_change(self):
        db = MagicMock()
        record = _mock_tenant_record(demo_mode=True)
        audit = AuditEvent(
            tenant_id="T_TEST",
            category="operator_action",
            action="tenant.pause_automation",
            status="no_change",
            details={},
        )
        with patch(
            "app.admin.operator_actions.TenantConfigRepository.get",
            return_value=record,
        ), patch(
            "app.admin.operator_actions.create_audit_event",
            return_value=audit,
        ), patch(
            "app.admin.operator_actions.TenantConfigRepository.update_settings",
        ) as update_mock:
            result = execute_pause_automation(
                db,
                "T_TEST",
                operator=_operator(),
                reason="test",
                idempotency_key="k1",
            )
        update_mock.assert_not_called()
        assert result.status == "no_change"
        assert result.changed is False

    def test_pause_writes_state_and_audit(self):
        db = MagicMock()
        record = _mock_tenant_record(demo_mode=False)
        audit = AuditEvent(
            tenant_id="T_TEST",
            category="operator_action",
            action="tenant.pause_automation",
            status="completed",
            details={},
        )
        with patch(
            "app.admin.operator_actions.TenantConfigRepository.get",
            return_value=record,
        ), patch(
            "app.admin.operator_actions.TenantConfigRepository.update_settings",
        ) as update_mock, patch(
            "app.admin.operator_actions.create_audit_event",
            return_value=audit,
        ) as audit_mock:
            result = execute_pause_automation(
                db,
                "T_TEST",
                operator=_operator(),
                reason="test reason",
                idempotency_key="k1",
            )
        update_mock.assert_called_once()
        assert result.status == "completed"
        assert result.changed is True
        details = audit_mock.call_args.kwargs["details"]
        assert details["operator_id"] == "operator-test"
        assert details["reason"] == "test reason"
        assert "password" not in str(details).lower()


class TestResumeAutomation:
    def test_already_active_returns_no_change(self):
        db = MagicMock()
        record = _mock_tenant_record(demo_mode=False)
        audit = AuditEvent(
            tenant_id="T_TEST",
            category="operator_action",
            action="tenant.resume_automation",
            status="no_change",
            details={},
        )
        with patch(
            "app.admin.operator_actions.TenantConfigRepository.get",
            return_value=record,
        ), patch(
            "app.admin.operator_actions.create_audit_event",
            return_value=audit,
        ), patch(
            "app.admin.operator_actions.TenantConfigRepository.update_settings",
        ) as update_mock:
            result = execute_resume_automation(
                db,
                "T_TEST",
                operator=_operator(),
                reason="test",
                idempotency_key="k1",
            )
        update_mock.assert_not_called()
        assert result.status == "no_change"


class TestRejectApproval:
    def _approval(self, **kwargs):
        defaults = {
            "approval_id": "appr-1",
            "tenant_id": "T_TEST",
            "state": "pending",
            "next_on_approve": "controlled_dispatch",
            "request_payload": {},
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_cross_tenant_not_found(self):
        db = MagicMock()
        with patch(
            "app.admin.operator_actions.ApprovalRequestRepository.get_by_approval_id",
            return_value=None,
        ):
            with pytest.raises(OperatorActionNotFoundError):
                execute_reject_approval(
                    db,
                    "T_TEST",
                    "appr-1",
                    operator=_operator(),
                    reason="stale",
                    idempotency_key="k1",
                )

    def test_wrong_approval_type_rejected(self):
        db = MagicMock()
        with patch(
            "app.admin.operator_actions.ApprovalRequestRepository.get_by_approval_id",
            return_value=self._approval(next_on_approve="email_send"),
        ):
            with pytest.raises(OperatorActionValidationError):
                execute_reject_approval(
                    db,
                    "T_TEST",
                    "appr-1",
                    operator=_operator(),
                    reason="stale",
                    idempotency_key="k1",
                )

    def test_already_resolved_conflict(self):
        db = MagicMock()
        with patch(
            "app.admin.operator_actions.ApprovalRequestRepository.get_by_approval_id",
            return_value=self._approval(state="rejected"),
        ):
            with pytest.raises(OperatorActionConflictError):
                execute_reject_approval(
                    db,
                    "T_TEST",
                    "appr-1",
                    operator=_operator(),
                    reason="stale",
                    idempotency_key="k1",
                )

    def test_reject_does_not_call_dispatch_engine(self):
        db = MagicMock()
        audit = AuditEvent(
            tenant_id="T_TEST",
            category="operator_action",
            action="approval.reject",
            status="completed",
            details={},
        )
        with patch(
            "app.admin.operator_actions.ApprovalRequestRepository.get_by_approval_id",
            return_value=self._approval(),
        ), patch(
            "app.admin.operator_actions.resolve_dispatch_approval",
            return_value={"status": "rejected"},
        ) as reject_mock, patch(
            "app.admin.operator_actions.create_audit_event",
            return_value=audit,
        ), patch(
            "app.workflows.dispatchers.engine.ControlledDispatchEngine",
        ) as engine_mock:
            result = execute_reject_approval(
                db,
                "T_TEST",
                "appr-1",
                operator=_operator(),
                reason="stale",
                idempotency_key="k1",
            )
        reject_mock.assert_called_once()
        engine_mock.assert_not_called()
        assert result.status == "completed"


class TestOperatorActionEndpoints:
    def _client(self):
        from fastapi.testclient import TestClient
        from app.main import app

        return TestClient(app, raise_server_exceptions=False)

    def _settings(self, **kwargs):
        defaults = {
            "ADMIN_API_KEY": "test-admin-key",
            "ADMIN_ROLE": "operations",
            "APP_NAME": "Test",
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_pause_requires_auth(self):
        client = self._client()
        with patch("app.core.admin_auth.get_settings", return_value=self._settings()):
            response = client.post(
                "/admin/tenants/T_TEST/actions/pause",
                json=_valid_body(),
            )
        assert response.status_code == 401

    def test_read_only_forbidden(self):
        client = self._client()
        with patch("app.core.admin_auth.get_settings", return_value=self._settings(ADMIN_ROLE="read_only")):
            response = client.post(
                "/admin/tenants/T_TEST/actions/pause",
                json=_valid_body(),
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
        assert response.status_code == 403

    def test_confirmation_false_rejected(self):
        client = self._client()
        with patch("app.core.admin_auth.get_settings", return_value=self._settings()):
            response = client.post(
                "/admin/tenants/T_TEST/actions/pause",
                json=_valid_body(confirmation=False),
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
        assert response.status_code == 422

    def test_unknown_tenant_404(self):
        client = self._client()
        with patch("app.core.admin_auth.get_settings", return_value=self._settings()), patch(
            "app.admin.operator_actions.TenantConfigRepository.get",
            return_value=None,
        ):
            response = client.post(
                "/admin/tenants/T_UNKNOWN/actions/pause",
                json=_valid_body(),
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
        assert response.status_code == 404

    def test_audit_failure_returns_500(self):
        client = self._client()
        record = _mock_tenant_record(demo_mode=False)
        with patch("app.core.admin_auth.get_settings", return_value=self._settings()), patch(
            "app.admin.operator_actions.TenantConfigRepository.get",
            return_value=record,
        ), patch(
            "app.admin.operator_actions.TenantConfigRepository.update_settings",
        ), patch(
            "app.admin.operator_actions.create_audit_event",
            side_effect=RuntimeError("audit down"),
        ):
            response = client.post(
                "/admin/tenants/T_TEST/actions/pause",
                json=_valid_body(),
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
        assert response.status_code == 500


class TestNeedsHelpAvailableActions:
    def test_approval_item_exposes_reject_for_operations(self):
        from app.admin.operations_needs_help import _attach_available_actions

        db = MagicMock()
        item = {
            "source_type": "approval",
            "_approval_id": "appr-1",
            "_tenant_id": "T_A",
            "tenant_id": "T_A",
        }
        with patch(
            "app.admin.operations_needs_help.load_approval_resource_state",
            return_value={
                "approval_state": "pending",
                "approval_kind": "controlled_dispatch",
            },
        ):
            actions = _attach_available_actions(db, item, "operations")
        assert len(actions) == 2
        ids = {a["action_id"] for a in actions}
        assert ids == {"approval.approve", "approval.reject"}
        assert all(a["allowed"] is True for a in actions)

    def test_read_only_approval_action_disabled(self):
        from app.admin.operations_needs_help import _attach_available_actions

        db = MagicMock()
        item = {
            "source_type": "approval",
            "_approval_id": "appr-1",
            "_tenant_id": "T_A",
            "tenant_id": "T_A",
        }
        with patch(
            "app.admin.operations_needs_help.load_approval_resource_state",
            return_value={
                "approval_state": "pending",
                "approval_kind": "controlled_dispatch",
            },
        ):
            actions = _attach_available_actions(db, item, "read_only")
        assert len(actions) == 2
        assert all(a["allowed"] is False for a in actions)
        assert all(a["blocked_reason"] == "insufficient_role" for a in actions)


class TestApproveApproval:
    def _approval(self, **kwargs):
        return SimpleNamespace(
            approval_id="appr-1",
            tenant_id="T_TEST",
            job_id="job-1",
            job_type="lead",
            state="pending",
            next_on_approve="controlled_dispatch",
            request_payload={},
            delivery_payload=None,
            **kwargs,
        )

    def test_approve_dispatch_success(self):
        db = MagicMock()
        with patch(
            "app.admin.operator_actions.ApprovalRequestRepository.get_by_approval_id",
            return_value=self._approval(),
        ), patch(
            "app.admin.operator_actions.resolve_dispatch_approval",
            return_value={"status": "approved"},
        ), patch(
            "app.admin.operator_actions._write_operator_audit",
            return_value="audit-1",
        ):
            result = execute_approve_approval(
                db,
                "T_TEST",
                "appr-1",
                operator=_operator(),
                reason="Verifierad dispatch",
                idempotency_key="k1",
            )
        assert result.status == "completed"
        assert "godkänt" in result.message.lower()
