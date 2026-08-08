"""Cross-tenant adversarial tests for customer workspace API."""

from __future__ import annotations

import pytest

from tests.customer_workspace.conftest import TENANT_A, seed_user, login
from tests.customer_workspace.security_helpers import (
    CROSS_TENANT_SENTINEL_B,
    SECRET_SENTINELS,
    TENANT_B,
    WORK_ITEM_ID_ATTACKS,
    WorkspaceSeedContext,
    assert_404_enumeration_safe,
    assert_json_free_of,
    collect_string_values,
    get_workspace,
    seed_tenant_a_canary_bundle,
    seed_tenant_b_canary_bundle,
    workspace_endpoint_specs,
    TENANT_OVERRIDE_VECTORS,
)
from app.core.customer_session import CUSTOMER_SESSION_COOKIE


@pytest.fixture()
def ctx():
    return WorkspaceSeedContext()


@pytest.fixture()
def seeded_db(db, ctx):
    seed_tenant_a_canary_bundle(db, ctx)
    seed_tenant_b_canary_bundle(db, ctx)
    return ctx


@pytest.fixture()
def authed_a(client, db, seeded_db):
    seed_user(db, tenant_id=TENANT_A, email="viewer-a@example.com")
    response = login(client, email="viewer-a@example.com")
    assert response.status_code == 200
    client.cookies.set(CUSTOMER_SESSION_COOKIE, response.cookies[CUSTOMER_SESSION_COOKIE])
    return client


def test_detail_own_tenant_returns_200(authed_a, seeded_db):
    response = authed_a.get(f"/workspace/v1/work-items/{seeded_db.work_item_a_id}")
    assert response.status_code == 200
    assert response.json()["work_item_id"] == seeded_db.work_item_a_id


def test_detail_cross_tenant_and_missing_are_enumeration_safe(authed_a, seeded_db):
    own = authed_a.get(f"/workspace/v1/work-items/{seeded_db.work_item_a_id}")
    cross = authed_a.get(f"/workspace/v1/work-items/{seeded_db.work_item_b_id}")
    missing = authed_a.get("/workspace/v1/work-items/does-not-exist-xyz")
    assert own.status_code == 200
    assert_404_enumeration_safe(cross, missing)


@pytest.mark.parametrize("work_item_id", WORK_ITEM_ID_ATTACKS)
def test_work_item_id_attacks_fail_closed(authed_a, work_item_id):
    response = authed_a.get(f"/workspace/v1/work-items/{work_item_id}")
    assert response.status_code in {404, 422}
    assert CROSS_TENANT_SENTINEL_B not in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize("spec", workspace_endpoint_specs(), ids=lambda spec: spec.name)
def test_list_endpoints_never_leak_tenant_b_sentinel(authed_a, seeded_db, spec):
    response = get_workspace(authed_a, spec, seeded_db)
    assert response.status_code == 200
    assert CROSS_TENANT_SENTINEL_B not in response.text
    assert seeded_db.work_item_b_id not in collect_string_values(response.json())
    assert seeded_db.approval_b_id not in collect_string_values(response.json())
    assert_json_free_of(response.json(), forbidden_values=list(SECRET_SENTINELS.values()))


@pytest.mark.parametrize(
    "vector_name,headers,query",
    TENANT_OVERRIDE_VECTORS,
    ids=[name for name, _, _ in TENANT_OVERRIDE_VECTORS],
)
@pytest.mark.parametrize("spec", workspace_endpoint_specs(), ids=lambda spec: spec.name)
def test_tenant_override_vectors_ignored(authed_a, seeded_db, spec, vector_name, headers, query):
    response = authed_a.get(
        spec.build_path(seeded_db),
        params={**spec.query_params(seeded_db), **query},
        headers=headers,
    )
    assert response.status_code == 200
    if spec.name == "context":
        assert response.json()["tenant_id"] == TENANT_A
    assert CROSS_TENANT_SENTINEL_B not in response.text
    assert seeded_db.work_item_b_id not in collect_string_values(response.json())


@pytest.mark.parametrize(
    "params,expected_status",
    [
        ({"type": "bogus"}, 422),
        ({"limit": 0}, 422),
        ({"limit": 101}, 422),
        ({"offset": -1}, 422),
        ({"from": "not-a-date"}, 422),
        ({"from": "2026-01-10", "to": "2026-01-01"}, 422),
        ({"q": "' OR 1=1 --"}, 200),
    ],
)
def test_work_items_filter_manipulation(authed_a, seeded_db, params, expected_status):
    response = authed_a.get("/workspace/v1/work-items", params=params)
    assert response.status_code == expected_status
    if expected_status == 200:
        assert CROSS_TENANT_SENTINEL_B not in response.text


def test_approvals_only_return_tenant_a(authed_a, seeded_db):
    response = authed_a.get("/workspace/v1/approvals")
    assert response.status_code == 200
    body = response.json()
    approval_ids = {item["approval_id"] for item in body["items"]}
    work_item_ids = {item["work_item_id"] for item in body["items"]}
    assert seeded_db.approval_a_id in approval_ids
    assert seeded_db.approval_b_id not in approval_ids
    assert seeded_db.work_item_b_id not in work_item_ids
    assert_json_free_of(body)


def test_timeline_does_not_leak_tenant_b_history(authed_a, seeded_db):
    response = authed_a.get(f"/workspace/v1/work-items/{seeded_db.work_item_a_id}")
    assert response.status_code == 200
    body = response.json()
    timeline_text = str(body.get("timeline"))
    assert SECRET_SENTINELS["timeline_b"] not in timeline_text
    assert SECRET_SENTINELS["gmail_metadata"] not in timeline_text
    assert SECRET_SENTINELS["processor_history"] not in timeline_text
    for event in body["timeline"]:
        assert set(event.keys()) <= {"at", "kind", "label", "detail"}
