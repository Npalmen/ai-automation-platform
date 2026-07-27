"""Cross-cutting evaluation controls (tenant, concurrency, flags, security)."""

from __future__ import annotations

import importlib
import json
import os
import threading
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.core.settings import get_settings
from app.domain.customer.api_schemas import (
    CreatePrivateEndCustomerRequest,
    OperatorCreateCustomerRequest,
    OperatorUpdateCustomerRequest,
)
from app.domain.customer.enums import CustomerType
from app.evaluation.customer_domain.actions import EvalContext, new_id
from app.evaluation.customer_domain.guards import EVAL_TENANT_PREFIX
from app.domain.customer.enums import DuplicateStatus
from app.repositories.postgres.end_customer_repository import EndCustomerRepository
from app.services.end_customer_command_service import EndCustomerCommandError, EndCustomerCommandService
from app.services.end_customer_read_service import EndCustomerReadService


def _audit_contains_raw_idempotency_key(details: Any) -> bool:
    if isinstance(details, str):
        try:
            parsed = json.loads(details)
        except json.JSONDecodeError:
            return "idempotency_key" in details.lower()
        details = parsed
    if isinstance(details, dict):
        return "idempotency_key" in details
    return False


def run_tenant_controls(engine, tenant_a: str, tenant_b: str) -> dict[str, Any]:
    session = sessionmaker(bind=engine)()
    failures: list[str] = []
    try:
        from app.evaluation.customer_domain.db import ensure_eval_tenant

        ensure_eval_tenant(session, tenant_a, "eval-a")
        ensure_eval_tenant(session, tenant_b, "eval-b")
        session.commit()

        ctx_a = EvalContext(engine=engine, tenant_id=tenant_a)
        ctx_b = EvalContext(engine=engine, tenant_id=tenant_b)
        email = "shared-isolation@example.invalid"
        phone = "+46708888888"
        thread_id = "shared-thread-001"
        idem_key = "shared-idem-key-001"

        create_a = ctx_a.act_create_private_customer(
            session,
            display_name="Tenant A",
            email=email,
            phone=phone,
            idempotency_key=idem_key,
        )
        create_b = ctx_b.act_create_private_customer(
            session,
            display_name="Tenant B",
            email=email,
            phone=phone,
            idempotency_key=idem_key,
        )
        customer_a = create_a["body"]["customer_id"]
        customer_b = create_b["body"]["customer_id"]
        if customer_a == customer_b:
            failures.append("cross-tenant customer ids equal")

        search_a = EndCustomerReadService.search(session, tenant_a, email, limit=10, offset=0)
        search_b = EndCustomerReadService.search(session, tenant_b, email, limit=10, offset=0)
        if search_a.total != 1 or search_b.total != 1:
            failures.append("search isolation failed")

        ctx_a.arrange_thread_link(session, customer_a, thread_id)
        ctx_b.arrange_thread_link(session, customer_b, thread_id)

        card_a = ctx_a.read_customer_card(session, customer_a)
        card_b = ctx_b.read_customer_card(session, customer_b)
        if card_a is None or card_b is None:
            failures.append("cross-tenant card read failed")
        elif card_a.card.customer_id == card_b.card.customer_id:
            failures.append("cross-tenant card ids leaked")

        cross_read = EndCustomerReadService.get_customer_card(session, tenant_a, customer_b)
        if cross_read is not None:
            failures.append("cross-tenant read should return None")

        return {
            "result": "PASS" if not failures else "FAIL",
            "failures": failures,
            "tenant_a_customer": customer_a,
            "tenant_b_customer": customer_b,
        }
    finally:
        session.close()


def _concurrent_create(engine, tenant_id: str) -> dict[str, Any]:
    from app.evaluation.customer_domain.db import ensure_eval_tenant

    idempotency_key = "concurrent-create-key"

    session = sessionmaker(bind=engine)()
    try:
        ensure_eval_tenant(session, tenant_id, tenant_id.lower())
        session.commit()
    finally:
        session.close()

    barrier = threading.Barrier(2)
    outcomes: list[str] = []
    errors: list[str] = []

    def worker() -> None:
        session = sessionmaker(bind=engine)()
        try:
            barrier.wait()
            request = OperatorCreateCustomerRequest(
                customer_type=CustomerType.PRIVATE,
                private=CreatePrivateEndCustomerRequest(display_name="Concurrent"),
                reason="concurrency",
            )
            EndCustomerCommandService.create_customer(
                session,
                tenant_id,
                {"id": "op", "display_name": "Op", "role": "admin"},
                request,
                idempotency_key,
            )
            session.commit()
            outcomes.append("ok")
        except Exception as exc:
            errors.append(str(exc))
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    session = sessionmaker(bind=engine)()
    try:
        count = session.execute(
            text("SELECT COUNT(*) FROM end_customers WHERE tenant_id = :tenant_id"),
            {"tenant_id": tenant_id},
        ).scalar()
        timeline = session.execute(
            text(
                "SELECT COUNT(*) FROM end_customer_timeline_events "
                "WHERE tenant_id = :tenant_id"
            ),
            {"tenant_id": tenant_id},
        ).scalar()
        replay_timeline = session.execute(
            text(
                "SELECT COUNT(*) FROM end_customer_timeline_events "
                "WHERE tenant_id = :tenant_id AND replay_identity_key LIKE :replay"
            ),
            {"tenant_id": tenant_id, "replay": f"%create:{idempotency_key}"},
        ).scalar()
        ok = (
            int(count or 0) == 1
            and int(timeline or 0) >= 1
            and int(replay_timeline or 0) == 1
            and len(outcomes) >= 1
        )
        return {
            "result": "PASS" if ok else "FAIL",
            "customer_count": int(count or 0),
            "timeline_count": int(timeline or 0),
            "timeline_replay_count": int(replay_timeline or 0),
            "errors": errors,
        }
    finally:
        session.close()


def _concurrent_update(engine, tenant_id: str) -> dict[str, Any]:
    from app.evaluation.customer_domain.db import ensure_eval_tenant

    session = sessionmaker(bind=engine)()
    try:
        ensure_eval_tenant(session, tenant_id, tenant_id.lower())
        session.commit()
        ctx = EvalContext(engine=engine, tenant_id=tenant_id)
        create = ctx.act_create_private_customer(
            session,
            display_name="Before",
            idempotency_key=new_id(),
        )
        customer_id = create["body"]["customer_id"]
        version = create["body"]["version"]
    finally:
        session.close()

    barrier = threading.Barrier(2)
    results: list[str] = []

    def worker() -> None:
        db = sessionmaker(bind=engine)()
        try:
            barrier.wait()
            request = OperatorUpdateCustomerRequest(
                expected_version=version,
                reason="concurrent update",
                display_name="After",
            )
            EndCustomerCommandService.update_customer(
                db,
                tenant_id,
                customer_id,
                {"id": "op", "display_name": "Op", "role": "admin"},
                request,
                new_id(),
            )
            db.commit()
            results.append("ok")
        except Exception as exc:
            results.append(type(exc).__name__)
        finally:
            db.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    session = sessionmaker(bind=engine)()
    try:
        row = session.execute(
            text(
                "SELECT version, display_name FROM end_customers "
                "WHERE tenant_id = :tenant_id AND customer_id = :customer_id"
            ),
            {"tenant_id": tenant_id, "customer_id": customer_id},
        ).mappings().first()
        final_version = int(row["version"]) if row else 0
        ok = final_version == version + 1 and sum(1 for r in results if r == "ok") == 1
        return {
            "result": "PASS" if ok else "FAIL",
            "final_version": final_version,
            "worker_results": results,
        }
    finally:
        session.close()


def _concurrent_duplicate_decision(engine, tenant_id: str) -> dict[str, Any]:
    from app.evaluation.customer_domain.actions import EvalContext, new_id
    from app.evaluation.customer_domain.db import ensure_eval_tenant

    session = sessionmaker(bind=engine)()
    try:
        ensure_eval_tenant(session, tenant_id, tenant_id.lower())
        session.commit()
        ctx = EvalContext(engine=engine, tenant_id=tenant_id)
        first = ctx.act_create_private_customer(
            session,
            display_name="Dup A",
            email="dup-a@example.invalid",
            idempotency_key=new_id(),
        )
        second = ctx.act_create_private_customer(
            session,
            display_name="Dup B",
            email="dup-b@example.invalid",
            idempotency_key=new_id(),
        )
        customer_a = first["body"]["customer_id"]
        customer_b = second["body"]["customer_id"]
        candidate_id = ctx.arrange_duplicate_candidate(session, customer_a, customer_b)
        candidate = EndCustomerRepository.get_duplicate_candidate(session, tenant_id, candidate_id)
        if candidate is None:
            return {"result": "FAIL", "error": "candidate missing"}
        expected_version = candidate.version
    finally:
        session.close()

    barrier = threading.Barrier(2)
    results: list[str] = []

    def worker(idempotency_key: str) -> None:
        db = sessionmaker(bind=engine)()
        try:
            barrier.wait()
            EndCustomerCommandService.duplicate_decision(
                db,
                tenant_id,
                candidate_id,
                {"id": "op", "display_name": "Op", "role": "admin"},
                "reject_merge",
                expected_version,
                "concurrent duplicate decision",
                idempotency_key,
            )
            db.commit()
            results.append("ok")
        except EndCustomerCommandError as exc:
            results.append(exc.code)
        except Exception as exc:
            results.append(type(exc).__name__)
        finally:
            db.close()

    threads = [
        threading.Thread(target=worker, args=(new_id(),)),
        threading.Thread(target=worker, args=(new_id(),)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    session = sessionmaker(bind=engine)()
    try:
        candidate = EndCustomerRepository.get_duplicate_candidate(session, tenant_id, candidate_id)
        resolved = candidate is not None and candidate.status == DuplicateStatus.REJECTED
        ok = (
            resolved
            and sum(1 for result in results if result == "ok") == 1
            and sum(1 for result in results if result == "DUPLICATE_DECISION_CONFLICT") == 1
        )
        return {
            "result": "PASS" if ok else "FAIL",
            "candidate_status": candidate.status.value if candidate else None,
            "worker_results": results,
        }
    finally:
        session.close()


def run_concurrency_controls(engine, tenant_id: str) -> dict[str, Any]:
    create_result = _concurrent_create(engine, tenant_id)
    update_result = _concurrent_update(engine, f"{tenant_id}_update")
    duplicate_result = _concurrent_duplicate_decision(engine, f"{tenant_id}_dup")
    overall = (
        "PASS"
        if create_result.get("result") == "PASS"
        and update_result.get("result") == "PASS"
        and duplicate_result.get("result") == "PASS"
        else "FAIL"
    )
    return {
        "result": overall,
        "concurrent_create": create_result,
        "concurrent_update": update_result,
        "concurrent_duplicate_decision": duplicate_result,
        "concurrent_timeline_replay": {
            "result": create_result.get("result"),
            "timeline_replay_count": create_result.get("timeline_replay_count"),
        },
    }


def run_feature_flag_controls() -> dict[str, Any]:
    os.environ["END_CUSTOMER_READ_API_ENABLED"] = "false"
    os.environ["END_CUSTOMER_WRITE_API_ENABLED"] = "false"
    get_settings.cache_clear()
    import app.main as main_mod

    with (
        patch("app.main.Base.metadata.create_all"),
        patch("app.repositories.postgres.schema_migrations.ensure_runtime_schema"),
        patch("app.repositories.postgres.schema_migrations.provision_tenant_defaults"),
        patch("app.workflows.decision_trace_readiness.verify_decision_trace_readiness"),
    ):
        importlib.reload(main_mod)
        paths = [route.path for route in main_mod.app.routes]
        read_disabled = not any("/end-customers" in p for p in paths)

    os.environ["END_CUSTOMER_READ_API_ENABLED"] = "true"
    os.environ["END_CUSTOMER_WRITE_API_ENABLED"] = "false"
    get_settings.cache_clear()
    with (
        patch("app.main.Base.metadata.create_all"),
        patch("app.repositories.postgres.schema_migrations.ensure_runtime_schema"),
        patch("app.repositories.postgres.schema_migrations.provision_tenant_defaults"),
        patch("app.workflows.decision_trace_readiness.verify_decision_trace_readiness"),
    ):
        importlib.reload(main_mod)
        read_paths = [route.path for route in main_mod.app.routes]
        read_enabled = any("/end-customers" in p for p in read_paths)
        write_routes = [
            route
            for route in main_mod.app.routes
            if hasattr(route, "methods")
            and "/admin/tenants" in route.path
            and "/end-customers" in route.path
            and "POST" in route.methods
        ]
        write_disabled = len(write_routes) == 0

    os.environ["END_CUSTOMER_READ_API_ENABLED"] = "true"
    os.environ["END_CUSTOMER_WRITE_API_ENABLED"] = "true"
    get_settings.cache_clear()
    with (
        patch("app.main.Base.metadata.create_all"),
        patch("app.repositories.postgres.schema_migrations.ensure_runtime_schema"),
        patch("app.repositories.postgres.schema_migrations.provision_tenant_defaults"),
        patch("app.workflows.decision_trace_readiness.verify_decision_trace_readiness"),
    ):
        importlib.reload(main_mod)
        write_enabled = any(
            hasattr(route, "methods")
            and "/admin/tenants" in route.path
            and "/end-customers" in route.path
            and "POST" in route.methods
            for route in main_mod.app.routes
        )
        tenant_write = any(
            hasattr(route, "methods")
            and route.path.startswith("/tenants/")
            and "/end-customers" in route.path
            and "POST" in route.methods
            for route in main_mod.app.routes
        )

    get_settings.cache_clear()
    ok = read_disabled and read_enabled and write_disabled and write_enabled and not tenant_write
    return {
        "result": "PASS" if ok else "FAIL",
        "read_disabled": read_disabled,
        "read_enabled": read_enabled,
        "write_disabled_when_flag_false": write_disabled,
        "write_enabled_when_flag_true": write_enabled,
        "tenant_facing_writes_absent": not tenant_write,
    }


def run_security_controls(engine, tenant_id: str) -> dict[str, Any]:
    session = sessionmaker(bind=engine)()
    try:
        from app.evaluation.customer_domain.db import ensure_eval_tenant

        ensure_eval_tenant(session, tenant_id, tenant_id.lower())
        session.commit()
        ctx = EvalContext(engine=engine, tenant_id=tenant_id)
        create = ctx.act_create_private_customer(
            session,
            display_name="Security",
            email="security@example.invalid",
            idempotency_key=new_id(),
        )
        card = ctx.read_customer_card(session, create["body"]["customer_id"])
        dumped = card.model_dump(mode="json") if card else {}
        forbidden_tokens = ("password", "api_key", "access_token", "body_text", "refresh_token")
        leaked = any(token in str(dumped).lower() for token in forbidden_tokens)
        audit_rows = session.execute(
            text(
                "SELECT details FROM audit_events WHERE tenant_id = :tenant_id LIMIT 20"
            ),
            {"tenant_id": tenant_id},
        ).fetchall()
        raw_idem_in_audit = any(
            _audit_contains_raw_idempotency_key(row[0]) for row in audit_rows
        )
        return {
            "result": "PASS" if not leaked and not raw_idem_in_audit else "FAIL",
            "response_leaked_secrets": leaked,
            "raw_idempotency_in_audit": raw_idem_in_audit,
        }
    finally:
        session.close()


def tenant_control_ids(suffix: str) -> tuple[str, str]:
    return (
        f"{EVAL_TENANT_PREFIX}tenant_{suffix}_a",
        f"{EVAL_TENANT_PREFIX}tenant_{suffix}_b",
    )
