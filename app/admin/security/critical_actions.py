"""
Declarative security contract registry for critical operator actions (Kapitel 11).

Backend source of truth for verification tests — does not auto-route requests in v1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Role = Literal["read_only", "operations", "admin"]
TenantScope = Literal["none", "path", "header", "platform"]
ConfirmationLevel = Literal["none", "dialog", "critical_dialog"]
ExternalEffect = Literal["none", "email", "integration", "scheduler", "credential"]


@dataclass(frozen=True)
class CriticalActionContract:
    action_key: str
    method: str
    path: str
    required_roles: frozenset[str]
    tenant_scope: TenantScope
    same_origin_required: bool
    optimistic_lock_required: bool
    reason_required: bool
    confirmation_level: ConfirmationLevel
    audit_event: str
    external_side_effect: ExternalEffect
    rate_limit_policy: str | None = None


_OPERATIONS = frozenset({"operations", "admin"})
_ADMIN = frozenset({"admin"})


CRITICAL_ACTIONS: tuple[CriticalActionContract, ...] = (
    # Operator safe writes (Kapitel 5)
    CriticalActionContract(
        action_key="tenant.pause_automation",
        method="POST",
        path="/admin/tenants/{tenant_id}/actions/pause",
        required_roles=_OPERATIONS,
        tenant_scope="path",
        same_origin_required=True,
        optimistic_lock_required=False,
        reason_required=True,
        confirmation_level="dialog",
        audit_event="operator_action",
        external_side_effect="none",
    ),
    CriticalActionContract(
        action_key="tenant.resume_automation",
        method="POST",
        path="/admin/tenants/{tenant_id}/actions/resume",
        required_roles=_OPERATIONS,
        tenant_scope="path",
        same_origin_required=True,
        optimistic_lock_required=False,
        reason_required=True,
        confirmation_level="dialog",
        audit_event="operator_action",
        external_side_effect="none",
    ),
    CriticalActionContract(
        action_key="approval.reject",
        method="POST",
        path="/admin/tenants/{tenant_id}/approvals/{approval_id}/reject",
        required_roles=_OPERATIONS,
        tenant_scope="path",
        same_origin_required=True,
        optimistic_lock_required=False,
        reason_required=True,
        confirmation_level="dialog",
        audit_event="operator_action",
        external_side_effect="none",
    ),
    CriticalActionContract(
        action_key="approval.approve",
        method="POST",
        path="/admin/tenants/{tenant_id}/approvals/{approval_id}/approve",
        required_roles=_OPERATIONS,
        tenant_scope="path",
        same_origin_required=True,
        optimistic_lock_required=False,
        reason_required=True,
        confirmation_level="dialog",
        audit_event="operator_action",
        external_side_effect="email",
    ),
    # Recovery (legacy console)
    *[
        CriticalActionContract(
            action_key=f"recovery.{suffix}",
            method="POST",
            path=f"/admin/recovery/{{job_id}}/{suffix}",
            required_roles=_OPERATIONS,
            tenant_scope="header",
            same_origin_required=True,
            optimistic_lock_required=False,
            reason_required=False,
            confirmation_level="none",
            audit_event="recovery",
            external_side_effect="integration",
            rate_limit_policy="recovery:20/h",
        )
        for suffix in (
            "retry",
            "replay-dispatch",
            "reclassify",
            "re-extract",
            "resend-approval",
            "reprocess-gmail",
        )
    ],
    # Support console
    *[
        CriticalActionContract(
            action_key=f"support.{suffix}",
            method="POST",
            path=f"/admin/support/{{tenant_id}}/{suffix}",
            required_roles=_OPERATIONS,
            tenant_scope="path",
            same_origin_required=True,
            optimistic_lock_required=False,
            reason_required=False,
            confirmation_level="none",
            audit_event="support",
            external_side_effect="scheduler" if "scheduler" in suffix else "none",
            rate_limit_policy="support:20/h",
        )
        for suffix in (
            "pause-automation",
            "resume-automation",
            "force-inbox-sync",
            "disable-scheduler",
            "enable-scheduler",
            "ack-needs-help",
            "clear-acknowledged",
        )
    ],
    # Tenant admin
    CriticalActionContract(
        action_key="tenant.rotate_key",
        method="POST",
        path="/admin/tenants/{tenant_id}/rotate-key",
        required_roles=_ADMIN,
        tenant_scope="path",
        same_origin_required=True,
        optimistic_lock_required=False,
        reason_required=False,
        confirmation_level="critical_dialog",
        audit_event="tenant_management.api_key_rotated",
        external_side_effect="credential",
    ),
    CriticalActionContract(
        action_key="tenant.set_status",
        method="PATCH",
        path="/admin/tenants/{tenant_id}/status",
        required_roles=_ADMIN,
        tenant_scope="path",
        same_origin_required=True,
        optimistic_lock_required=False,
        reason_required=False,
        confirmation_level="critical_dialog",
        audit_event="tenant_management.status_changed",
        external_side_effect="none",
    ),
    CriticalActionContract(
        action_key="tenant.demo_seed",
        method="POST",
        path="/admin/tenants/{tenant_id}/demo/seed",
        required_roles=_ADMIN,
        tenant_scope="path",
        same_origin_required=True,
        optimistic_lock_required=False,
        reason_required=False,
        confirmation_level="none",
        audit_event="demo.seed",
        external_side_effect="none",
    ),
    # Alerts
    CriticalActionContract(
        action_key="alerts.run_all",
        method="POST",
        path="/admin/alerts/run-all",
        required_roles=_OPERATIONS,
        tenant_scope="platform",
        same_origin_required=True,
        optimistic_lock_required=False,
        reason_required=False,
        confirmation_level="none",
        audit_event="alert.evaluation_started",
        external_side_effect="none",
        rate_limit_policy="alert_eval:10/min",
    ),
    CriticalActionContract(
        action_key="alerts.suppress",
        method="POST",
        path="/admin/alerts/{alert_id}/suppress",
        required_roles=_ADMIN,
        tenant_scope="platform",
        same_origin_required=True,
        optimistic_lock_required=True,
        reason_required=True,
        confirmation_level="critical_dialog",
        audit_event="alert.suppressed",
        external_side_effect="none",
    ),
    # Onboarding
    CriticalActionContract(
        action_key="onboarding.activate",
        method="POST",
        path="/admin/onboarding/{session_id}/activate",
        required_roles=_ADMIN,
        tenant_scope="platform",
        same_origin_required=True,
        optimistic_lock_required=True,
        reason_required=True,
        confirmation_level="critical_dialog",
        audit_event="onboarding.activated",
        external_side_effect="scheduler",
        rate_limit_policy="onboarding_activate:3/h",
    ),
    CriticalActionContract(
        action_key="onboarding.readiness",
        method="POST",
        path="/admin/onboarding/{session_id}/readiness",
        required_roles=_OPERATIONS,
        tenant_scope="platform",
        same_origin_required=True,
        optimistic_lock_required=False,
        reason_required=False,
        confirmation_level="none",
        audit_event="onboarding.readiness",
        external_side_effect="none",
    ),
)


def contracts_by_path_method() -> dict[tuple[str, str], CriticalActionContract]:
    out: dict[tuple[str, str], CriticalActionContract] = {}
    for contract in CRITICAL_ACTIONS:
        out[(contract.path, contract.method.upper())] = contract
    return out
