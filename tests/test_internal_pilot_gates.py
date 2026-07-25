"""Hermetic tests for internal live pilot gates."""

from __future__ import annotations

import socket

import pytest
from fastapi import HTTPException

from app.internal_pilot.constants import (
    MAX_PILOT_BATCH_EMAILS,
    PILOT_GMAIL_QUERY,
    PILOT_TENANT_ID,
)
from app.internal_pilot.gates import (
    PilotGateViolation,
    enforce_pilot_inbox_gates,
    enforce_pilot_scheduler_sync,
    validate_pilot_batch_size,
    validate_pilot_query,
)
from app.internal_pilot.readiness import build_internal_pilot_readiness


def _safe_settings(**overrides) -> dict:
    base = {
        "auto_actions": {"lead": "semi", "customer_inquiry": "semi", "invoice": "semi"},
        "automation": {"automatic_gmail_replies": False, "demo_mode": False},
        "scheduler": {"run_mode": "manual"},
        "operations": {"paused": False},
        "internal_pilot": {"live_scan_enabled": False},
    }
    base.update(overrides)
    return base


def test_wrong_tenant_is_noop():
    query = enforce_pilot_inbox_gates(
        tenant_id="T_OTHER",
        query="is:unread",
        max_results=50,
        dry_run=False,
        settings=_safe_settings(),
    )
    assert query == "is:unread"


def test_pilot_requires_scoped_query():
    with pytest.raises(PilotGateViolation, match="explicit scoped Gmail query"):
        validate_pilot_query(None)
    with pytest.raises(PilotGateViolation, match="scoped label"):
        validate_pilot_query("is:unread")


def test_pilot_accepts_locked_query():
    assert validate_pilot_query(PILOT_GMAIL_QUERY) == PILOT_GMAIL_QUERY


def test_pilot_batch_budget():
    validate_pilot_batch_size(MAX_PILOT_BATCH_EMAILS)
    with pytest.raises(PilotGateViolation):
        validate_pilot_batch_size(MAX_PILOT_BATCH_EMAILS + 1)


def test_auto_send_flag_denied():
    settings = _safe_settings(auto_actions={"lead": "auto"})
    with pytest.raises(PilotGateViolation):
        enforce_pilot_inbox_gates(
            tenant_id=PILOT_TENANT_ID,
            query=PILOT_GMAIL_QUERY,
            max_results=3,
            dry_run=True,
            settings=settings,
        )


def test_external_write_policy_blocks_live_without_operator_gate():
    with pytest.raises(PilotGateViolation, match="live inbox sync is disabled"):
        enforce_pilot_inbox_gates(
            tenant_id=PILOT_TENANT_ID,
            query=PILOT_GMAIL_QUERY,
            max_results=3,
            dry_run=False,
            settings=_safe_settings(),
        )


def test_live_allowed_when_operator_gate_enabled():
    settings = _safe_settings(internal_pilot={"live_scan_enabled": True})
    query = enforce_pilot_inbox_gates(
        tenant_id=PILOT_TENANT_ID,
        query=PILOT_GMAIL_QUERY,
        max_results=3,
        dry_run=False,
        settings=settings,
    )
    assert query == PILOT_GMAIL_QUERY


def test_scheduler_pause_for_pilot_tenant():
    with pytest.raises(PilotGateViolation, match="scheduled inbox sync is forbidden"):
        enforce_pilot_scheduler_sync(
            tenant_id=PILOT_TENANT_ID,
            settings=_safe_settings(scheduler={"run_mode": "scheduled"}),
        )


def test_readiness_passes_without_live_enabled():
    report = build_internal_pilot_readiness(
        tenant_id=PILOT_TENANT_ID,
        settings=_safe_settings(),
    )
    assert report["overall_status"] == "ready_for_operator_activation"
    assert report["blockers"] == []


def test_readiness_fails_for_wrong_tenant():
    report = build_internal_pilot_readiness(
        tenant_id="T_OTHER",
        settings=_safe_settings(),
    )
    assert report["overall_status"] == "fail"
    assert "pilot_tenant_isolated" in report["blockers"]


def test_main_inbox_gate_maps_to_http_403():
    from unittest.mock import MagicMock, patch

    from app.main import _run_gmail_inbox_sync

    db = MagicMock()
    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=_safe_settings(),
        ),
        patch("app.main.get_integration_connection_config", side_effect=AssertionError("no gmail")),
    ):
        with pytest.raises(HTTPException) as exc:
            _run_gmail_inbox_sync(
                tenant_id=PILOT_TENANT_ID,
                db=db,
                max_results=3,
                query="is:unread",
                dry_run=False,
            )
        assert exc.value.status_code == 403


def test_no_network_socket_blocked_for_readiness_builder(monkeypatch):
    def _blocked(*_args, **_kwargs):
        raise OSError("network blocked")

    monkeypatch.setattr(socket, "socket", _blocked)
    report = build_internal_pilot_readiness(
        tenant_id=PILOT_TENANT_ID,
        settings=_safe_settings(),
    )
    assert report["overall_status"] == "ready_for_operator_activation"
