"""F1b HTTP contract tests for flag-gated end-customer routes on isolated PostgreSQL."""

from __future__ import annotations

import importlib
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db
from app.core.settings import get_settings
from app.evaluation.customer_domain.db import cleanup_eval_tenants, ensure_eval_tenant, initialize_database
from app.repositories.postgres.end_customer_repository import EndCustomerRepository
from tests.helpers.customer_domain_eval_pg import eval_engine


def _reload_app(read_enabled: bool, write_enabled: bool):
    os.environ["END_CUSTOMER_READ_API_ENABLED"] = "true" if read_enabled else "false"
    os.environ["END_CUSTOMER_WRITE_API_ENABLED"] = "true" if write_enabled else "false"
    get_settings.cache_clear()
    import app.main as main_mod

    importlib.reload(main_mod)
    return main_mod.app


@pytest.fixture()
def pg_engine():
    engine = eval_engine()
    initialize_database(engine)
    cleanup_eval_tenants(engine)
    yield engine
    cleanup_eval_tenants(engine)
    engine.dispose()


@pytest.fixture()
def http_client(pg_engine):
    tenant_id = "eval_cd_http_contract"
    session = sessionmaker(bind=pg_engine)()
    try:
        ensure_eval_tenant(session, tenant_id, tenant_id.lower())
        session.commit()
    finally:
        session.close()

    app = _reload_app(True, True)

    def override_get_db():
        db = sessionmaker(bind=pg_engine)()
        try:
            yield db
        finally:
            db.close()

    with (
        patch("app.main.Base.metadata.create_all"),
        patch("app.repositories.postgres.schema_migrations.ensure_runtime_schema"),
        patch("app.repositories.postgres.schema_migrations.provision_tenant_defaults"),
        patch("app.workflows.decision_trace_readiness.verify_decision_trace_readiness"),
        patch.dict(os.environ, {"ADMIN_ROLE": "admin", "ADMIN_API_KEY": "ci-admin-key"}, clear=False),
    ):
        get_settings.cache_clear()
        app.dependency_overrides[get_db] = override_get_db
        with TestClient(app) as client:
            yield client, tenant_id
        app.dependency_overrides.clear()
    get_settings.cache_clear()


@pytest.fixture()
def disabled_http_client(pg_engine):
    tenant_id = "eval_cd_http_disabled"
    app = _reload_app(False, False)
    with (
        patch("app.main.Base.metadata.create_all"),
        patch("app.repositories.postgres.schema_migrations.ensure_runtime_schema"),
        patch("app.repositories.postgres.schema_migrations.provision_tenant_defaults"),
        patch("app.workflows.decision_trace_readiness.verify_decision_trace_readiness"),
    ):
        with TestClient(app) as client:
            yield client, tenant_id
    get_settings.cache_clear()


def _admin_headers(idempotency_key: str = "http-idem-1") -> dict[str, str]:
    return {
        "X-Admin-API-Key": "ci-admin-key",
        "Origin": "http://testserver",
        "Idempotency-Key": idempotency_key,
    }


@pytest.mark.pg_eval
class TestTbfHttpContract:
    def test_create_read_update_flow(self, http_client):
        client, tenant_id = http_client
        create = client.post(
            f"/admin/tenants/{tenant_id}/end-customers",
            headers=_admin_headers("http-create-1"),
            json={
                "customer_type": "private",
                "private": {
                    "display_name": "HTTP Private",
                    "email": "http-private@eval.test",
                    "phone": "+46701111001",
                },
                "reason": "F1b contract",
            },
        )
        assert create.status_code == 201
        customer_id = create.json()["customer_id"]
        version = create.json()["version"]

        card = client.get(
            f"/admin/tenants/{tenant_id}/end-customers/{customer_id}",
            headers={"X-Admin-API-Key": "ci-admin-key"},
        )
        assert card.status_code == 200
        assert card.json()["card"]["customer_id"] == customer_id

        patch = client.patch(
            f"/admin/tenants/{tenant_id}/end-customers/{customer_id}",
            headers=_admin_headers("http-patch-1"),
            json={
                "expected_version": version,
                "display_name": "HTTP Private Updated",
                "reason": "F1b update",
            },
        )
        assert patch.status_code == 200

    def test_fact_verify_and_job_link(self, http_client, pg_engine):
        client, tenant_id = http_client
        create = client.post(
            f"/admin/tenants/{tenant_id}/end-customers",
            headers=_admin_headers("http-create-2"),
            json={
                "customer_type": "private",
                "private": {"display_name": "Fact Flow", "email": "fact-flow@eval.test"},
                "reason": "F1b contract",
            },
        )
        customer_id = create.json()["customer_id"]
        contact_id = create.json().get("primary_contact_id")

        fact = client.post(
            f"/admin/tenants/{tenant_id}/end-customers/{customer_id}/facts",
            headers=_admin_headers("http-fact-1"),
            json={
                "subject_type": "contact",
                "subject_id": contact_id,
                "field_name": "phone",
                "raw_value": "+46701111002",
                "normalized_value": "+46701111002",
                "fact_state": "proposed",
                "source_type": "ai_extraction",
                "confidence": 0.7,
                "reason": "AI proposed phone",
            },
        )
        assert fact.status_code == 201
        fact_id = fact.json()["fact_id"]

        verify = client.post(
            f"/admin/tenants/{tenant_id}/end-customers/{customer_id}/facts/{fact_id}/verify",
            headers=_admin_headers("http-verify-1"),
            json={
                "verified_raw_value": "+46701111002",
                "normalized_value": "+46701111002",
                "reason": "Operator verify",
            },
        )
        assert verify.status_code in (200, 201)

        from datetime import datetime, timezone

        from app.repositories.postgres.job_models import JobRecord

        job_session = sessionmaker(bind=pg_engine)()
        try:
            job_id = "job-http-contract-1"
            now = datetime.now(timezone.utc)
            job_session.add(
                JobRecord(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    job_type="lead",
                    status="pending",
                    input_data={},
                    result={},
                    created_at=now,
                    updated_at=now,
                )
            )
            job_session.commit()
        finally:
            job_session.close()

        job_link = client.post(
            f"/admin/tenants/{tenant_id}/end-customers/{customer_id}/job-links",
            headers=_admin_headers("http-job-1"),
            json={"job_id": job_id, "link_type": "manual", "reason": "F1b job link"},
        )
        assert job_link.status_code == 201

    def test_duplicate_decision_and_idempotency(self, http_client, pg_engine):
        client, tenant_id = http_client
        first = client.post(
            f"/admin/tenants/{tenant_id}/end-customers",
            headers=_admin_headers("http-dup-a"),
            json={
                "customer_type": "private",
                "private": {"display_name": "Dup A", "email": "dup-a@eval.test"},
                "reason": "F1b duplicate",
            },
        )
        second = client.post(
            f"/admin/tenants/{tenant_id}/end-customers",
            headers=_admin_headers("http-dup-b"),
            json={
                "customer_type": "private",
                "private": {"display_name": "Dup B", "email": "dup-b@eval.test"},
                "reason": "F1b duplicate",
            },
        )
        customer_a = first.json()["customer_id"]
        customer_b = second.json()["customer_id"]

        db = sessionmaker(bind=pg_engine)()
        try:
            candidate, _ = EndCustomerRepository.create_duplicate_candidate(
                db, tenant_id, customer_a, customer_b, 0.9
            )
            db.commit()
            candidate_id = candidate.candidate_id
            version = candidate.version
        finally:
            db.close()

        headers = _admin_headers("http-dup-decision-1")
        decision = client.post(
            f"/admin/tenants/{tenant_id}/end-customer-duplicates/{candidate_id}/decision",
            headers=headers,
            json={
                "decision": "resolve_without_merge",
                "expected_version": version,
                "reason": "F1b resolve",
            },
        )
        assert decision.status_code == 200
        replay = client.post(
            f"/admin/tenants/{tenant_id}/end-customer-duplicates/{candidate_id}/decision",
            headers=headers,
            json={
                "decision": "resolve_without_merge",
                "expected_version": version,
                "reason": "F1b resolve",
            },
        )
        assert replay.status_code == 200

    def test_disabled_flags_fail_closed(self, disabled_http_client):
        client, tenant_id = disabled_http_client
        response = client.post(
            f"/admin/tenants/{tenant_id}/end-customers",
            headers=_admin_headers("disabled-create"),
            json={
                "customer_type": "private",
                "private": {"display_name": "Disabled"},
                "reason": "should fail",
            },
        )
        assert response.status_code in {404, 405}

    def test_approve_merge_blocked_via_http(self, http_client, pg_engine):
        client, tenant_id = http_client
        db = sessionmaker(bind=pg_engine)()
        try:
            first = client.post(
                f"/admin/tenants/{tenant_id}/end-customers",
                headers=_admin_headers("http-merge-a"),
                json={
                    "customer_type": "private",
                    "private": {"display_name": "Merge A", "email": "merge-a@eval.test"},
                    "reason": "merge block",
                },
            )
            second = client.post(
                f"/admin/tenants/{tenant_id}/end-customers",
                headers=_admin_headers("http-merge-b"),
                json={
                    "customer_type": "private",
                    "private": {"display_name": "Merge B", "email": "merge-b@eval.test"},
                    "reason": "merge block",
                },
            )
            candidate, _ = EndCustomerRepository.create_duplicate_candidate(
                db,
                tenant_id,
                first.json()["customer_id"],
                second.json()["customer_id"],
                0.9,
            )
            db.commit()
            response = client.post(
                f"/admin/tenants/{tenant_id}/end-customer-duplicates/{candidate.candidate_id}/decision",
                headers=_admin_headers("http-merge-block"),
                json={
                    "decision": "approve_merge",
                    "expected_version": candidate.version,
                    "reason": "must block",
                },
            )
            assert response.status_code == 422
            body = response.json()
            detail = body.get("detail")
            if isinstance(detail, dict):
                assert detail.get("code") in {None, "AUTOMATIC_MERGE_FORBIDDEN"}
            else:
                assert any("approve_merge" in str(item).lower() for item in detail)
        finally:
            db.close()
