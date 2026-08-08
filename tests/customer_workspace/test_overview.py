"""Tests for GET /workspace/v1/overview."""

from __future__ import annotations

from tests.customer_workspace.conftest import seed_job


def test_overview_requires_session(client):
    assert client.get("/workspace/v1/overview").status_code == 401


def test_overview_returns_summary(authed_client, db):
    seed_job(db, job_id="job-1", status="completed")
    response = authed_client.get("/workspace/v1/overview")
    assert response.status_code == 200
    body = response.json()
    assert "summary" in body
    assert "priority_work_items" in body
    assert isinstance(body["priority_work_items"], list)
    assert len(body["priority_work_items"]) <= 20
    assert "partial_errors" in body
    assert "job_id" not in response.text


def test_overview_partial_error_on_needs_help_failure(authed_client, db, monkeypatch):
    seed_job(db, job_id="job-1")

    def boom(*_args, **_kwargs):
        raise RuntimeError("triage down")

    monkeypatch.setattr("app.customer_workspace.adapters.overview.needs_help_job_ids", boom)
    response = authed_client.get("/workspace/v1/overview")
    assert response.status_code == 200
    assert any(err["section"] == "needs_help" for err in response.json()["partial_errors"])
