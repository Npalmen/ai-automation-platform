"""Contract tests: forbidden fields and GET-only workspace API."""

from __future__ import annotations

import json

import pytest

from tests.customer_workspace.conftest import seed_approval, seed_job

FORBIDDEN_SUBSTRINGS = [
    "password_hash",
    "request_payload",
    "delivery_payload",
    "processor_history",
    "auto_actions",
    "allowed_integrations",
    '"job_id"',
    "execution_id",
    "external_id",
]


def _walk_strings(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, path + "/" + str(key)
            yield from _walk_strings(child, path + "/" + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_strings(child, f"{path}[{index}]")


def test_workspace_openapi_is_get_only(client):
    schema = client.get("/openapi.json").json()
    workspace_paths = {
        path: methods
        for path, methods in schema.get("paths", {}).items()
        if path.startswith("/workspace/v1")
    }
    assert workspace_paths, "expected workspace paths in OpenAPI"
    for path, methods in workspace_paths.items():
        http_methods = {m.lower() for m in methods if m.lower() not in {"parameters"}}
        assert http_methods == {"get"}, f"{path} has {http_methods}"


@pytest.mark.parametrize(
    "url",
    [
        "/workspace/v1/context",
        "/workspace/v1/overview",
        "/workspace/v1/work-items",
        "/workspace/v1/approvals",
        "/workspace/v1/activity",
        "/workspace/v1/health",
    ],
)
def test_forbidden_fields_absent(authed_client, db, url):
    seed_job(db, job_id="scan-job-1")
    seed_approval(db, approval_id="scan-appr-1", job_id="scan-job-1")
    response = authed_client.get(url)
    assert response.status_code == 200
    text = json.dumps(response.json())
    for forbidden in FORBIDDEN_SUBSTRINGS:
        assert forbidden not in text, f"{forbidden} found in {url}"
    for key, path in _walk_strings(response.json()):
        assert key != "job_id", f"job_id at {path}"
        if key == "work_item_id":
            continue
        assert "work_item_id" not in str(key) or key == "work_item_id"
