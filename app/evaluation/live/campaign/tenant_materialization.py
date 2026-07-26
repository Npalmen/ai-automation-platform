"""Tenant-aware action materialization contract for semi-auto campaigns."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MATERIALIZED_PENDING = "materialized_pending"
NOT_MATERIALIZED = "not_materialized"
REMAIN_PENDING = "remain_pending"
RESOLVED_BY_OPERATOR = "resolved_by_operator"
REJECTED_BY_OPERATOR = "rejected_by_operator"
CANCELLED_BY_PRODUCT = "cancelled_by_product"

VALID_MATERIALIZATION_STATES = frozenset(
    {
        MATERIALIZED_PENDING,
        NOT_MATERIALIZED,
        REMAIN_PENDING,
        RESOLVED_BY_OPERATOR,
        REJECTED_BY_OPERATOR,
        CANCELLED_BY_PRODUCT,
    }
)

HANDOFF_ACTION = "send_internal_handoff"
CUSTOMER_REPLY_ACTION = "send_customer_auto_reply"

LIVE_EVAL_TENANT_ID = "TENANT_LIVE_EVAL"


@dataclass(frozen=True)
class ExpectedActionMaterialization:
    action_type: str
    materialization: str
    operator_role: str | None = None
    reason: str | None = None

    @property
    def is_target(self) -> bool:
        return self.operator_role == "target"


@dataclass(frozen=True)
class TenantMaterializationContext:
    tenant_id: str
    internal_notification_email: str | None
    service_profile: str | None = None

    @property
    def internal_handoff_enabled(self) -> bool:
        return bool((self.internal_notification_email or "").strip())


def resolve_live_eval_tenant_context(
    *,
    tenant_id: str = LIVE_EVAL_TENANT_ID,
    tenant_settings: dict[str, Any] | None = None,
) -> TenantMaterializationContext:
    """Resolve materialization context for live-eval tenant (offline-safe defaults)."""
    settings = tenant_settings or {}
    branding = dict(settings.get("branding") or {})
    internal_email = (
        branding.get("internal_notification_email")
        or settings.get("internal_notification_email")
        or None
    )
    if internal_email is not None:
        internal_email = str(internal_email).strip() or None
    return TenantMaterializationContext(
        tenant_id=tenant_id,
        internal_notification_email=internal_email,
        service_profile=settings.get("service_profile"),
    )


def default_handoff_materialization(
    context: TenantMaterializationContext,
) -> ExpectedActionMaterialization:
    if context.internal_handoff_enabled:
        return ExpectedActionMaterialization(
            action_type=HANDOFF_ACTION,
            materialization=REMAIN_PENDING,
            operator_role=None,
            reason=None,
        )
    return ExpectedActionMaterialization(
        action_type=HANDOFF_ACTION,
        materialization=NOT_MATERIALIZED,
        operator_role=None,
        reason="tenant_internal_notification_disabled",
    )


def resolve_expected_actions_for_semi_auto(
    *,
    target_action_type: str,
    context: TenantMaterializationContext,
    explicit_expected_actions: list[dict[str, Any]] | None = None,
) -> tuple[ExpectedActionMaterialization, ...]:
    """Build expected action materialization list for a semi-auto scenario."""
    if explicit_expected_actions:
        resolved: list[ExpectedActionMaterialization] = []
        for row in explicit_expected_actions:
            action_type = str(row.get("action_type") or "").strip()
            materialization = str(row.get("materialization") or "").strip()
            if materialization not in VALID_MATERIALIZATION_STATES:
                raise ValueError(f"invalid materialization {materialization!r}")
            resolved.append(
                ExpectedActionMaterialization(
                    action_type=action_type,
                    materialization=materialization,
                    operator_role=row.get("operator_role"),
                    reason=row.get("reason"),
                )
            )
        return tuple(resolved)

    return (
        ExpectedActionMaterialization(
            action_type=target_action_type,
            materialization=MATERIALIZED_PENDING,
            operator_role="target",
        ),
        default_handoff_materialization(context),
    )


def materialization_to_secondary_state(materialization: str) -> str:
    """Map expected_actions materialization to secondary_approvals expected_final_state."""
    if materialization == NOT_MATERIALIZED:
        return NOT_MATERIALIZED
    if materialization == MATERIALIZED_PENDING:
        return REMAIN_PENDING
    if materialization in (RESOLVED_BY_OPERATOR, REJECTED_BY_OPERATOR):
        return materialization
    if materialization == CANCELLED_BY_PRODUCT:
        return CANCELLED_BY_PRODUCT
    raise ValueError(f"unsupported materialization for secondary mapping: {materialization!r}")


def count_expected_materialized_pending(
    expected_actions: tuple[ExpectedActionMaterialization, ...],
) -> int:
    return sum(
        1
        for action in expected_actions
        if action.materialization == MATERIALIZED_PENDING
    )
