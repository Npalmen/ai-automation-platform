"""Tests for workspace work-items endpoints."""

from __future__ import annotations

import pytest

from tests.customer_workspace.conftest import TENANT_A, TENANT_B, seed_job, seed_user, login

FORBIDDEN_KEYS = {
    "job_id",
    "input_data",
    "result",
    "processor_history",
    "request_payload",
    "execution_id",
}


def test_work_items_requires_session(client):
    assert client.get("/workspace/v1/work-items").status_code == 401


def test_work_items_lists_tenant_jobs(authed_client, db):
    seed_job(db, job_id="job-lead-1", job_type="lead", subject="Offert")
    seed_job(db, job_id="job-support-1", job_type="customer_inquiry", subject="Fråga")
    response = authed_client.get("/workspace/v1/work-items")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert body["limit"] == 50
    ids = {item["work_item_id"] for item in body["items"]}
    assert ids == {"job-lead-1", "job-support-1"}
    for item in body["items"]:
        assert "customer_status_label" in item
        for key in FORBIDDEN_KEYS:
            assert key not in item


@pytest.mark.parametrize(
    "params,expected_id",
    [
        ({"type": "lead"}, "job-lead-1"),
        ({"type": "support"}, "job-support-1"),
        ({"status": "new"}, "job-lead-1"),
        ({"q": "Erik"}, "job-lead-1"),
    ],
)
def test_work_items_filters(authed_client, db, params, expected_id):
    seed_job(db, job_id="job-lead-1", job_type="lead", customer_name="Erik Johansson")
    seed_job(db, job_id="job-support-1", job_type="customer_inquiry", customer_name="Maria")
    response = authed_client.get("/workspace/v1/work-items", params=params)
    assert response.status_code == 200
    ids = {item["work_item_id"] for item in response.json()["items"]}
    assert expected_id in ids


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"from": "not-a-date"},
        {"from": "2026-01-10", "to": "2026-01-01"},
    ],
)
def test_work_items_validation_errors(authed_client, params):
    response = authed_client.get("/workspace/v1/work-items", params=params)
    assert response.status_code == 422


def test_work_item_detail_own_tenant(authed_client, db):
    seed_job(db, job_id="job-detail-1", subject="Detalj")
    response = authed_client.get("/workspace/v1/work-items/job-detail-1")
    assert response.status_code == 200
    body = response.json()
    assert body["work_item_id"] == "job-detail-1"
    assert "timeline" in body
    for key in FORBIDDEN_KEYS:
        assert key not in body


def test_work_item_detail_missing_returns_404(authed_client):
    assert authed_client.get("/workspace/v1/work-items/missing-id").status_code == 404


def test_work_item_detail_other_tenant_returns_404(authed_client, db):
    seed_job(db, job_id="job-other", tenant_id=TENANT_B)
    assert authed_client.get("/workspace/v1/work-items/job-other").status_code == 404


def test_whitespace_only_q_treated_as_empty(authed_client, db):
    seed_job(db, job_id="job-1")
    response = authed_client.get("/workspace/v1/work-items", params={"q": "   "})
    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_x_tenant_id_cannot_override_session(client, db):
    seed_user(db, tenant_id=TENANT_A)
    seed_job(db, job_id="job-a", tenant_id=TENANT_A)
    seed_job(db, job_id="job-b", tenant_id=TENANT_B)
    login_resp = login(client)
    client.cookies.set("customer_session", login_resp.cookies["customer_session"])
    response = client.get(
        "/workspace/v1/work-items",
        headers={"X-Tenant-ID": TENANT_B},
    )
    assert response.status_code == 200
    ids = {item["work_item_id"] for item in response.json()["items"]}
    assert "job-b" not in ids
    assert "job-a" in ids
