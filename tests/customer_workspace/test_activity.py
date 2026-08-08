"""Tests for GET /workspace/v1/activity."""

from __future__ import annotations

import pytest

from tests.customer_workspace.conftest import seed_job


def test_activity_requires_session(client):
    assert client.get("/workspace/v1/activity").status_code == 401


def test_activity_returns_normalized_items(authed_client, db):
    seed_job(db, job_id="job-lead", job_type="lead", status="completed")
    seed_job(db, job_id="job-invoice", job_type="invoice", status="completed")
    response = authed_client.get("/workspace/v1/activity")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    for item in body["items"]:
        assert "customer_status" in item
        assert "customer_status_label" in item
        assert "label" in item
        assert item["type"] in {"lead", "support", "invoice"}


def test_activity_type_filter(authed_client, db):
    seed_job(db, job_id="job-lead", job_type="lead")
    seed_job(db, job_id="job-invoice", job_type="invoice")
    response = authed_client.get("/workspace/v1/activity", params={"type": "invoice"})
    assert response.status_code == 200
    types = {item["type"] for item in response.json()["items"]}
    assert types <= {"invoice"}


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_activity_validation(authed_client, params):
    assert authed_client.get("/workspace/v1/activity", params=params).status_code == 422
