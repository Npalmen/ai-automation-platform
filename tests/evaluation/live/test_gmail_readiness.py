"""Gmail readiness route and offline mode tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.readiness import run_gmail_readiness_checks, run_offline_readiness_checks
from app.evaluation.live.readiness_report import build_readiness_report
from app.evaluation.live.routes import router as live_eval_router

_FORBIDDEN_ACTIONS = (
    "send_message",
    "create_label",
    "modify_labels",
    "mark_as_read",
    "mark_read",
    "archive",
    "delete",
)


def _mock_adapter(
    *,
    profile_email: str = "recipient@eval.test",
    labels: list[dict] | None = None,
):
    mock_adapter = MagicMock()
    label_rows = labels if labels is not None else [{"id": "lbl1", "name": "krowolf-live-eval"}]

    def _execute_action(*, action, payload=None):
        if action == "get_profile":
            return {"email_address": profile_email}
        if action == "list_labels":
            return {"labels": label_rows}
        raise AssertionError(f"unexpected gmail action: {action}")

    mock_adapter.execute_action.side_effect = _execute_action
    return mock_adapter


def _run_gmail_readiness(
    db,
    *,
    user_id: str,
    profile_email: str = "recipient@eval.test",
    labels: list[dict] | None = None,
):
    mock_adapter = _mock_adapter(profile_email=profile_email, labels=labels)
    with patch(
        "app.evaluation.live.readiness.get_integration_connection_config",
        return_value={"user_id": user_id, "access_token": "token"},
    ), patch(
        "app.evaluation.live.readiness.is_integration_enabled_for_tenant",
        return_value=True,
    ), patch(
        "app.evaluation.live.readiness.get_integration_adapter",
        return_value=mock_adapter,
    ):
        report = run_gmail_readiness_checks(db, "TENANT_LIVE_EVAL")
    called_actions = [call.kwargs["action"] for call in mock_adapter.execute_action.call_args_list]
    return report, called_actions


def test_offline_readiness_makes_no_network_calls(live_eval_env, monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("offline readiness must not perform network calls")

    monkeypatch.setattr("httpx.get", fail_network)
    report = run_offline_readiness_checks()
    assert report.checks["mode"] == "offline"


@pytest.fixture
def live_eval_client(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    app = FastAPI()
    app.include_router(live_eval_router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


def test_gmail_readiness_route_uses_read_only_adapter(db, live_eval_env, live_eval_client):
    mock_adapter = _mock_adapter()
    with patch(
        "app.evaluation.live.readiness.get_integration_connection_config",
        return_value={"user_id": "recipient@eval.test", "access_token": "x"},
    ), patch(
        "app.evaluation.live.readiness.is_integration_enabled_for_tenant",
        return_value=True,
    ), patch(
        "app.evaluation.live.readiness.get_integration_adapter",
        return_value=mock_adapter,
    ):
        response = live_eval_client.post(
            "/admin/live-eval/gmail-readiness",
            headers={"X-Admin-API-Key": "test-admin-key"},
            json={"tenant_id": "TENANT_LIVE_EVAL"},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is True
    called_actions = [
        call.kwargs.get("action") or call.args[0]
        for call in mock_adapter.execute_action.call_args_list
    ]
    assert called_actions == ["get_profile", "list_labels"]
    for forbidden in _FORBIDDEN_ACTIONS:
        assert forbidden not in called_actions


def test_gmail_readiness_service_read_only(db, live_eval_env):
    report, called_actions = _run_gmail_readiness(db, user_id="recipient@eval.test")
    assert report.ready is True
    assert report.checks["label_present"] is True
    assert report.checks["gmail_profile_email"] == "recipient@eval.test"
    assert set(called_actions) == {"get_profile", "list_labels"}


@pytest.mark.parametrize("user_id", ["me", "ME", " Me "])
def test_gmail_readiness_accepts_me_selector(db, live_eval_env, user_id):
    report, called_actions = _run_gmail_readiness(db, user_id=user_id)
    assert report.ready is True
    assert report.checks["connection_user_id"] == user_id.strip().lower()
    assert set(called_actions) == {"get_profile", "list_labels"}


def test_gmail_readiness_literal_email_matching_profile_passes(db, live_eval_env):
    report, _ = _run_gmail_readiness(db, user_id="recipient@eval.test")
    assert report.ready is True


def test_gmail_readiness_literal_email_mismatch_fails(db, live_eval_env):
    report, _ = _run_gmail_readiness(db, user_id="other@eval.test")
    assert report.ready is False
    assert "Gmail profile email does not match configured connection user_id" in report.issues


def test_gmail_readiness_profile_not_in_allowlist_fails(db, live_eval_env):
    report, _ = _run_gmail_readiness(
        db,
        user_id="me",
        profile_email="wrong@eval.test",
    )
    assert report.ready is False
    assert "Gmail profile email does not match LIVE_EVAL_RECIPIENT_EMAILS" in report.issues


def test_gmail_readiness_unknown_selector_fails(db, live_eval_env):
    report, _ = _run_gmail_readiness(db, user_id="primary")
    assert report.ready is False
    assert "configured connection user_id is not a valid Gmail selector or email address" in report.issues


@pytest.mark.parametrize("profile_email", ["", "not-an-email", "missing-at-sign"])
def test_gmail_readiness_missing_or_invalid_profile_fails(db, live_eval_env, profile_email):
    report, _ = _run_gmail_readiness(db, user_id="me", profile_email=profile_email)
    assert report.ready is False
    assert "Gmail profile email is missing" in report.issues


def test_gmail_readiness_allowlist_normalizes_casing_and_whitespace(db, live_eval_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", " Recipient@Eval.Test ")
    get_live_eval_config.cache_clear()
    report, _ = _run_gmail_readiness(
        db,
        user_id="me",
        profile_email="recipient@eval.test",
    )
    get_live_eval_config.cache_clear()
    assert report.ready is True


def test_gmail_readiness_missing_label_fails(db, live_eval_env):
    report, _ = _run_gmail_readiness(db, user_id="me", labels=[])
    assert report.ready is False
    assert any("not found" in issue for issue in report.issues)


def test_gmail_readiness_intake_query_missing_label_token_fails():
    label_name = "krowolf-live-eval"
    intake_query = "is:unread"
    query_token = f"label:{label_name}".replace(" ", "").lower()
    assert query_token not in intake_query.replace(" ", "").lower()


def test_readiness_report_keeps_zero_side_effect_counters(live_eval_env):
    report = build_readiness_report(
        tenant_id="TENANT_LIVE_EVAL",
        workflow_sha="abc123",
        environment_status="live-gmail-eval",
        sender_profile_match=True,
        recipient_profile_match=True,
        recipient_label_found=True,
        intake_query_valid=True,
        result="passed",
    )
    assert report["external_sends"] == 0
    assert report["gmail_mutations"] == 0
    assert report["live_llm_calls"] == 0
