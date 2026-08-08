"""Tests for GET /workspace/v1/approvals."""

from __future__ import annotations

import pytest

from tests.customer_workspace.conftest import seed_approval, seed_job

FORBIDDEN_KEYS = {
    "job_id",
    "request_payload",
    "delivery_payload",
    "next_on_approve",
    "next_on_reject",
    "channel",
    "requested_by",
}


def test_approvals_requires_session(client):
    assert client.get("/workspace/v1/approvals").status_code == 401


def test_approvals_pending_only(authed_client, db):
    seed_job(db, job_id="job-1")
    seed_approval(db, approval_id="appr-1", job_id="job-1")
    response = authed_client.get("/workspace/v1/approvals")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["approval_id"] == "appr-1"
    assert item["work_item_id"] == "job-1"
    for key in FORBIDDEN_KEYS:
        assert key not in item


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 200}, {"offset": -1}])
def test_approvals_validation(authed_client, params):
    assert authed_client.get("/workspace/v1/approvals", params=params).status_code == 422


def test_workspace_openapi_has_no_approval_writes(client):
    schema = client.get("/openapi.json").json()
    for path, methods in schema.get("paths", {}).items():
        if not path.startswith("/workspace/v1"):
            continue
        for method in methods:
            assert method.lower() in {"get", "parameters"}, f"{method.upper()} on {path}"
