"""Reusable security helpers for customer workspace adversarial tests."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.job_models import JobRecord

TENANT_A = "TENANT_1001"
TENANT_B = "TENANT_2002"
CROSS_TENANT_SENTINEL_B = "CROSS_TENANT_SENTINEL_B"

SECRET_SENTINELS = {
    "password": "SECRET_SENTINEL_PASSWORD_9f3a",
    "password_hash": "SECRET_SENTINEL_PASSWORD_HASH_9f3a",
    "token": "SECRET_SENTINEL_TOKEN_9f3a",
    "token_hash": "SECRET_SENTINEL_TOKEN_HASH_9f3a",
    "session_id": "SECRET_SENTINEL_SESSION_ID_9f3a",
    "api_key": "SECRET_SENTINEL_API_KEY_9f3a",
    "access_token": "SECRET_SENTINEL_ACCESS_TOKEN_9f3a",
    "refresh_token": "SECRET_SENTINEL_REFRESH_TOKEN_9f3a",
    "client_secret": "SECRET_SENTINEL_CLIENT_SECRET_9f3a",
    "authorization": "SECRET_SENTINEL_AUTHORIZATION_9f3a",
    "job_id": "SECRET_SENTINEL_JOB_ID_9f3a",
    "input_data": "SECRET_SENTINEL_INPUT_DATA_9f3a",
    "result_payload": "SECRET_SENTINEL_RESULT_PAYLOAD_9f3a",
    "processor_history": "SECRET_SENTINEL_PROCESSOR_HISTORY_9f3a",
    "request_payload": "SECRET_SENTINEL_REQUEST_PAYLOAD_9f3a",
    "delivery_payload": "SECRET_SENTINEL_DELIVERY_PAYLOAD_9f3a",
    "execution_id": "SECRET_SENTINEL_EXECUTION_ID_9f3a",
    "external_id": "SECRET_SENTINEL_EXTERNAL_ID_9f3a",
    "auto_actions": "SECRET_SENTINEL_AUTO_ACTIONS_9f3a",
    "allowed_integrations": "SECRET_SENTINEL_ALLOWED_INTEGRATIONS_9f3a",
    "decision": "SECRET_SENTINEL_DECISION_9f3a",
    "recommendation": "SECRET_SENTINEL_RECOMMENDATION_9f3a",
    "policy": "SECRET_SENTINEL_POLICY_9f3a",
    "dispatch": "SECRET_SENTINEL_DISPATCH_9f3a",
    "provider": "SECRET_SENTINEL_PROVIDER_9f3a",
    "llm_output": "SECRET_SENTINEL_LLM_OUTPUT_9f3a",
    "gmail_metadata": "SECRET_SENTINEL_GMAIL_METADATA_9f3a",
    "timeline_b": "SECRET_SENTINEL_TIMELINE_B_9f3a",
}

FORBIDDEN_JSON_KEYS = frozenset(
    {
        "password",
        "password_hash",
        "token",
        "token_hash",
        "session_id",
        "api_key",
        "x-api-key",
        "access_token",
        "refresh_token",
        "client_secret",
        "secret",
        "authorization",
        "cookie",
        "job_id",
        "input_data",
        "result",
        "result_payload",
        "processor_history",
        "request_payload",
        "delivery_payload",
        "execution_id",
        "external_id",
        "auto_actions",
        "allowed_integrations",
        "channel",
        "requested_by",
        "next_on_approve",
        "next_on_reject",
    }
)

ALLOWED_JSON_KEYS = frozenset({"work_item_id", "approval_id"})

ENUMERATION_FORBIDDEN_SUBSTRINGS = (
    TENANT_B,
    "job_id",
    "resource owner",
    "other tenant",
    "wrong tenant",
    "Traceback",
    "sqlalchemy",
    "SELECT ",
)

TENANT_OVERRIDE_VECTORS: tuple[tuple[str, dict[str, str], dict[str, str]], ...] = (
    ("x_tenant_header", {"X-Tenant-ID": TENANT_B}, {}),
    ("api_key", {"X-API-Key": "tenant-b-secret-key"}, {}),
    ("admin_api_key", {"X-Admin-API-Key": "admin-secret-key"}, {}),
    ("query_tenant_id", {}, {"tenant_id": TENANT_B}),
    ("query_tenant", {}, {"tenant": TENANT_B}),
    ("query_company_id", {}, {"company_id": "company-b-123"}),
    ("query_organization_id", {}, {"organization_id": "org-b-123"}),
    (
        "combined_override",
        {"X-Tenant-ID": TENANT_B, "X-API-Key": "tenant-b-secret-key"},
        {"tenant_id": TENANT_B},
    ),
)


@dataclass(frozen=True)
class WorkspaceSeedContext:
    work_item_a_id: str = "job-a-canary"
    work_item_b_id: str = "job-b-canary"
    approval_a_id: str = "appr-a-canary"
    approval_b_id: str = "appr-b-canary"
    execution_a_id: str = "exec-a-canary"
    execution_b_id: str = "exec-b-canary"


@dataclass(frozen=True)
class WorkspaceEndpointSpec:
    name: str
    build_path: Callable[[WorkspaceSeedContext], str]
    query_params: Callable[[WorkspaceSeedContext], dict[str, str]] = field(
        default=lambda _ctx: {}
    )


def workspace_endpoint_specs() -> tuple[WorkspaceEndpointSpec, ...]:
    return (
        WorkspaceEndpointSpec("context", lambda _ctx: "/workspace/v1/context"),
        WorkspaceEndpointSpec("overview", lambda _ctx: "/workspace/v1/overview"),
        WorkspaceEndpointSpec("work_items_list", lambda _ctx: "/workspace/v1/work-items"),
        WorkspaceEndpointSpec(
            "work_item_detail",
            lambda ctx: f"/workspace/v1/work-items/{ctx.work_item_a_id}",
        ),
        WorkspaceEndpointSpec("approvals", lambda _ctx: "/workspace/v1/approvals"),
        WorkspaceEndpointSpec("activity", lambda _ctx: "/workspace/v1/activity"),
        WorkspaceEndpointSpec("health", lambda _ctx: "/workspace/v1/health"),
    )


def iter_json_keys(value: Any, *, path: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}/{key}" if path else str(key)
            yield str(key), child_path
            yield from iter_json_keys(child, path=child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_json_keys(child, path=f"{path}[{index}]")


def assert_json_free_of(
    value: Any,
    *,
    forbidden_keys: frozenset[str] | set[str] | None = None,
    forbidden_values: Iterable[str] | None = None,
    allowed_keys: frozenset[str] | set[str] | None = None,
) -> None:
    keys = forbidden_keys or FORBIDDEN_JSON_KEYS
    allowed = allowed_keys or ALLOWED_JSON_KEYS
    for key, path in iter_json_keys(value):
        if key in allowed:
            continue
        assert key not in keys, f"forbidden key {key!r} at {path}"
    if forbidden_values:
        text = json.dumps(value)
        for sentinel in forbidden_values:
            assert sentinel not in text, f"forbidden value {sentinel!r} found in JSON"


def assert_404_enumeration_safe(*responses) -> None:
    bodies: list[Any] = []
    for response in responses:
        assert response.status_code == 404
        bodies.append(response.json())
        text = response.text
        for forbidden in ENUMERATION_FORBIDDEN_SUBSTRINGS:
            assert forbidden not in text, f"enumeration hint {forbidden!r} in {text}"
    assert bodies[0] == bodies[1], "404 bodies must be indistinguishable"


def collect_string_values(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, str):
        found.add(value)
    elif isinstance(value, Mapping):
        for child in value.values():
            found.update(collect_string_values(child))
    elif isinstance(value, list):
        for child in value:
            found.update(collect_string_values(child))
    return found


def get_workspace(client: TestClient, spec: WorkspaceEndpointSpec, ctx: WorkspaceSeedContext):
    return client.get(spec.build_path(ctx), params=spec.query_params(ctx))


def seed_rich_job(
    db: Session,
    *,
    job_id: str,
    tenant_id: str,
    subject: str,
    customer_name: str,
    customer_email: str,
    internal_sentinels: Mapping[str, str] | None = None,
    conversation_messages: list[dict[str, Any]] | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    sentinels = dict(internal_sentinels or {})
    db.add(
        JobRecord(
            job_id=job_id,
            tenant_id=tenant_id,
            job_type="lead",
            status="processing",
            input_data={
                "subject": subject,
                "sender": {"name": customer_name, "email": customer_email},
                "received_at": now.isoformat(),
                "conversation_messages": conversation_messages
                or [
                    {
                        "source": "gmail",
                        "received_at": now.isoformat(),
                        "subject": subject,
                        "message_text": sentinels.get("gmail_metadata", "safe"),
                    }
                ],
            },
            result={
                "payload": {
                    "recommended_status": "needs_customer_info",
                    "decision": sentinels.get("decision", "safe"),
                    "recommendation": sentinels.get("recommendation", "safe"),
                    "policy": sentinels.get("policy", "safe"),
                    "llm_output": sentinels.get("llm_output", "safe"),
                },
                "processor_history": [
                    {
                        "processor": "action_dispatch_processor",
                        "result": {
                            "payload": {
                                "actions_requested": [],
                                "dispatch": sentinels.get("dispatch", "safe"),
                            }
                        },
                    }
                ],
            },
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def seed_rich_approval(
    db: Session,
    *,
    approval_id: str,
    job_id: str,
    tenant_id: str,
    title: str,
    summary: str,
) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        ApprovalRequestRecord(
            approval_id=approval_id,
            tenant_id=tenant_id,
            job_id=job_id,
            job_type="lead",
            state="pending",
            channel="email",
            title=title,
            summary=summary,
            requested_at=now,
            requested_by="operator@internal.example",
            request_payload={
                "secret": SECRET_SENTINELS["request_payload"],
                "job_id": SECRET_SENTINELS["job_id"],
            },
            delivery_payload={"secret": SECRET_SENTINELS["delivery_payload"]},
            next_on_approve="dispatch_step",
            next_on_reject="reject_step",
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def seed_action_execution(
    db: Session,
    *,
    execution_id: str,
    job_id: str,
    tenant_id: str,
    result_payload: dict[str, Any] | None = None,
) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        ActionExecutionRecord(
            execution_id=execution_id,
            tenant_id=tenant_id,
            job_id=job_id,
            action_type="send_email",
            status="completed",
            provider=SECRET_SENTINELS["provider"],
            external_id=SECRET_SENTINELS["external_id"],
            request_payload={"secret": SECRET_SENTINELS["request_payload"]},
            result_payload=result_payload or {"secret": SECRET_SENTINELS["result_payload"]},
            executed_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


def seed_tenant_b_canary_bundle(db: Session, ctx: WorkspaceSeedContext | None = None) -> WorkspaceSeedContext:
    ctx = ctx or WorkspaceSeedContext()
    seed_rich_job(
        db,
        job_id=ctx.work_item_b_id,
        tenant_id=TENANT_B,
        subject=f"B subject {CROSS_TENANT_SENTINEL_B}",
        customer_name=f"B Customer {CROSS_TENANT_SENTINEL_B}",
        customer_email="b-sentinel@example.com",
        internal_sentinels=SECRET_SENTINELS,
        conversation_messages=[
            {
                "source": "gmail",
                "received_at": datetime.now(timezone.utc).isoformat(),
                "subject": SECRET_SENTINELS["timeline_b"],
                "message_text": SECRET_SENTINELS["gmail_metadata"],
            }
        ],
    )
    seed_rich_approval(
        db,
        approval_id=ctx.approval_b_id,
        job_id=ctx.work_item_b_id,
        tenant_id=TENANT_B,
        title=f"B approval {CROSS_TENANT_SENTINEL_B}",
        summary=CROSS_TENANT_SENTINEL_B,
    )
    seed_action_execution(
        db,
        execution_id=ctx.execution_b_id,
        job_id=ctx.work_item_b_id,
        tenant_id=TENANT_B,
    )
    return ctx


def seed_tenant_a_canary_bundle(db: Session, ctx: WorkspaceSeedContext | None = None) -> WorkspaceSeedContext:
    ctx = ctx or WorkspaceSeedContext()
    seed_rich_job(
        db,
        job_id=ctx.work_item_a_id,
        tenant_id=TENANT_A,
        subject="A subject safe",
        customer_name="A Customer",
        customer_email="a-safe@example.com",
        internal_sentinels={key: "safe-internal" for key in SECRET_SENTINELS},
    )
    seed_rich_approval(
        db,
        approval_id=ctx.approval_a_id,
        job_id=ctx.work_item_a_id,
        tenant_id=TENANT_A,
        title="A approval safe",
        summary="A summary safe",
    )
    seed_action_execution(
        db,
        execution_id=ctx.execution_a_id,
        job_id=ctx.work_item_a_id,
        tenant_id=TENANT_A,
        result_payload={"note": "safe"},
    )
    return ctx


WORK_ITEM_ID_ATTACKS = (
    "nonexistent-work-item",
    "job-b-canary",
    "%2e%2e%2fjob-b-canary",
    "job-b-canary%20",
    "' OR 1=1 --",
    "x" * 256,
    "../job-b-canary",
)


def assert_partial_errors_sanitized(body: Mapping[str, Any]) -> None:
    errors = body.get("partial_errors") or []
    for item in errors:
        assert set(item.keys()) <= {"section", "code", "message"}
        blob = json.dumps(item)
        for forbidden in ("Traceback", "sqlalchemy", SECRET_SENTINELS["request_payload"]):
            assert forbidden not in blob


def assert_error_body_sanitized(response) -> None:
    text = response.text
    for forbidden in ("Traceback", "sqlalchemy", "SECRET_SENTINEL", "RuntimeError"):
        assert forbidden not in text


def workspace_openapi_methods(client: TestClient) -> dict[str, set[str]]:
    schema = client.get("/openapi.json").json()
    workspace_paths = {
        path: methods
        for path, methods in schema.get("paths", {}).items()
        if path.startswith("/workspace/v1")
    }
    result: dict[str, set[str]] = {}
    for path, methods in workspace_paths.items():
        result[path] = {
            method.lower()
            for method in methods
            if method.lower() not in {"parameters"}
        }
    return result


def is_write_sql(statement: str) -> bool:
    normalized = re.sub(r"\s+", " ", statement.strip().lower())
    return normalized.startswith(("insert ", "update ", "delete "))
