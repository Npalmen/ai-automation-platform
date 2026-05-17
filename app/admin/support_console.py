"""
Admin Support Action Console — per-tenant operational control.

Admin-only.  No tenant API key required — all actions use admin auth + explicit
tenant_id.  All writes go through existing settings/control infrastructure
(TenantConfigRepository.update_settings) so the control panel, scheduler,
and inbox-sync behavior remain consistent.

Every action emits a category="support_action" audit event.

Actions
-------
pause_automation          – set automation.demo_mode=True (blocks live sends/sync)
resume_automation         – set automation.demo_mode=False
disable_scheduler         – set scheduler.run_mode="paused"
enable_scheduler          – set scheduler.run_mode="scheduled"
force_inbox_sync          – run _run_gmail_inbox_sync immediately for the tenant
ack_needs_help            – mark a specific needs-help triage item acknowledged
clear_acknowledged        – clear all acknowledged markers for the tenant
get_tenant_ops_state      – aggregate operational state for the support console view
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event
from app.health.integration_health import get_integration_health
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.job_models import JobRecord

logger = logging.getLogger(__name__)

_ACTION_CATEGORY = "support_action"
_ACK_SETTINGS_KEY = "support_acknowledged_items"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ok(action: str, tenant_id: str, message: str, details: dict | None = None) -> dict:
    return {
        "status": "success",
        "action": action,
        "tenant_id": tenant_id,
        "message": message,
        "details": details or {},
    }


def _fail(action: str, tenant_id: str, message: str, details: dict | None = None) -> dict:
    return {
        "status": "failed",
        "action": action,
        "tenant_id": tenant_id,
        "message": message,
        "details": details or {},
    }


def _audit(db: Session, tenant_id: str, action: str, status: str, details: dict) -> None:
    try:
        create_audit_event(
            db=db,
            tenant_id=tenant_id,
            category=_ACTION_CATEGORY,
            action=action,
            status=status,
            details=details,
        )
    except Exception:
        logger.exception("Failed to write support_action audit event: %s/%s", tenant_id, action)


def _get_settings(db: Session, tenant_id: str) -> dict:
    return TenantConfigRepository.get_settings(db, tenant_id)


def _save_settings(db: Session, tenant_id: str, settings: dict) -> None:
    TenantConfigRepository.update_settings(db, tenant_id, settings)


def _get_automation(settings: dict) -> dict:
    return dict(settings.get("automation") or {})


def _get_scheduler(settings: dict) -> dict:
    return dict(settings.get("scheduler") or {})


def _tenant_exists(db: Session, tenant_id: str) -> bool:
    record = TenantConfigRepository.get(db, tenant_id)
    return record is not None


# ---------------------------------------------------------------------------
# Action 1: Pause tenant automation
# ---------------------------------------------------------------------------

def pause_automation(db: Session, tenant_id: str, actor: str = "admin") -> dict[str, Any]:
    """
    Enable demo_mode for the tenant, which blocks live inbox sync and
    automated external sends (same guard used by the scheduler and inbox sync).
    """
    action_name = "pause_automation"
    if not _tenant_exists(db, tenant_id):
        return _fail(action_name, tenant_id, "Tenant not found.")

    settings = _get_settings(db, tenant_id)
    automation = _get_automation(settings)
    automation["demo_mode"] = True
    settings["automation"] = automation
    _save_settings(db, tenant_id, settings)

    _audit(db, tenant_id, action_name, "success", {
        "actor": actor,
        "note": "demo_mode enabled — automation paused",
    })

    return _ok(action_name, tenant_id, "Tenant automation paused (demo_mode=true). Live inbox sync and automated sends are blocked.")


# ---------------------------------------------------------------------------
# Action 2: Resume tenant automation
# ---------------------------------------------------------------------------

def resume_automation(db: Session, tenant_id: str, actor: str = "admin") -> dict[str, Any]:
    """Disable demo_mode, re-enabling live processing."""
    action_name = "resume_automation"
    if not _tenant_exists(db, tenant_id):
        return _fail(action_name, tenant_id, "Tenant not found.")

    settings = _get_settings(db, tenant_id)
    automation = _get_automation(settings)
    automation["demo_mode"] = False
    settings["automation"] = automation
    _save_settings(db, tenant_id, settings)

    _audit(db, tenant_id, action_name, "success", {
        "actor": actor,
        "note": "demo_mode disabled — automation resumed",
    })

    return _ok(action_name, tenant_id, "Tenant automation resumed (demo_mode=false). Live processing re-enabled.")


# ---------------------------------------------------------------------------
# Action 3: Force inbox sync
# ---------------------------------------------------------------------------

def force_inbox_sync(
    db: Session,
    tenant_id: str,
    actor: str = "admin",
    app_settings: Any = None,
) -> dict[str, Any]:
    """
    Trigger an immediate Gmail inbox sync for the specified tenant, bypassing
    the scheduler's demo_mode guard (admin action is explicit and intentional).

    Returns the sync result summary or an error shape.
    """
    action_name = "force_inbox_sync"
    if not _tenant_exists(db, tenant_id):
        return _fail(action_name, tenant_id, "Tenant not found.")

    _audit(db, tenant_id, action_name, "initiated", {"actor": actor})

    try:
        # Late import to avoid circular dependency with app.main
        from app.main import _run_gmail_inbox_sync as _sync_fn
        result = _sync_fn(
            db=db,
            tenant_id=tenant_id,
            app_settings=app_settings,
        )
    except Exception:
        logger.exception("force_inbox_sync failed for tenant %s", tenant_id)
        _audit(db, tenant_id, action_name, "failed", {"actor": actor, "error": "sync_error"})
        return _fail(action_name, tenant_id, "Inbox sync failed. Check Gmail credentials and server logs.")

    _audit(db, tenant_id, action_name, "success", {
        "actor": actor,
        "processed": result.get("processed", 0),
        "created_jobs": len(result.get("created_jobs") or []),
    })

    return _ok(action_name, tenant_id, "Inbox sync completed.", {
        "processed": result.get("processed", 0),
        "created_jobs": len(result.get("created_jobs") or []),
        "deduped": result.get("deduped", 0),
        "errors": result.get("errors", []),
    })


# ---------------------------------------------------------------------------
# Action 4: Disable scheduler per tenant
# ---------------------------------------------------------------------------

def disable_scheduler(db: Session, tenant_id: str, actor: str = "admin") -> dict[str, Any]:
    """Set scheduler.run_mode to 'paused' — stops automated inbox sync for this tenant."""
    action_name = "disable_scheduler"
    if not _tenant_exists(db, tenant_id):
        return _fail(action_name, tenant_id, "Tenant not found.")

    settings = _get_settings(db, tenant_id)
    scheduler = _get_scheduler(settings)
    scheduler["run_mode"] = "paused"
    settings["scheduler"] = scheduler
    _save_settings(db, tenant_id, settings)

    _audit(db, tenant_id, action_name, "success", {"actor": actor, "run_mode": "paused"})
    return _ok(action_name, tenant_id, "Scheduler paused for tenant. Automatic inbox sync is stopped.")


# ---------------------------------------------------------------------------
# Action 5: Enable scheduler per tenant
# ---------------------------------------------------------------------------

def enable_scheduler(db: Session, tenant_id: str, actor: str = "admin") -> dict[str, Any]:
    """Set scheduler.run_mode to 'scheduled'."""
    action_name = "enable_scheduler"
    if not _tenant_exists(db, tenant_id):
        return _fail(action_name, tenant_id, "Tenant not found.")

    settings = _get_settings(db, tenant_id)
    scheduler = _get_scheduler(settings)
    scheduler["run_mode"] = "scheduled"
    settings["scheduler"] = scheduler
    _save_settings(db, tenant_id, settings)

    _audit(db, tenant_id, action_name, "success", {"actor": actor, "run_mode": "scheduled"})
    return _ok(action_name, tenant_id, "Scheduler enabled for tenant. Automatic inbox sync will resume.")


# ---------------------------------------------------------------------------
# Action 6: Acknowledge / clear needs-help items
# ---------------------------------------------------------------------------

def ack_needs_help(
    db: Session,
    tenant_id: str,
    item_key: str,
    actor: str = "admin",
    note: str = "",
) -> dict[str, Any]:
    """
    Mark a triage item as acknowledged by support.

    item_key is a stable string identifying the item, e.g. "{area}:{job_id}" or
    "{area}:{approval_id}".  Persisted in settings so it survives restarts.
    """
    action_name = "ack_needs_help"
    if not _tenant_exists(db, tenant_id):
        return _fail(action_name, tenant_id, "Tenant not found.")

    settings = _get_settings(db, tenant_id)
    acks: dict = dict(settings.get(_ACK_SETTINGS_KEY) or {})
    acks[item_key] = {
        "acknowledged_by": actor,
        "acknowledged_at": _utcnow().isoformat(),
        "note": note,
    }
    settings[_ACK_SETTINGS_KEY] = acks
    _save_settings(db, tenant_id, settings)

    _audit(db, tenant_id, action_name, "success", {
        "actor": actor,
        "item_key": item_key,
        "note": note,
    })

    return _ok(action_name, tenant_id, f"Item '{item_key}' acknowledged.", {
        "item_key": item_key,
        "acknowledged_by": actor,
    })


def clear_acknowledged(db: Session, tenant_id: str, actor: str = "admin") -> dict[str, Any]:
    """Clear all acknowledged markers for the tenant."""
    action_name = "clear_acknowledged"
    if not _tenant_exists(db, tenant_id):
        return _fail(action_name, tenant_id, "Tenant not found.")

    settings = _get_settings(db, tenant_id)
    cleared_count = len(settings.get(_ACK_SETTINGS_KEY) or {})
    settings.pop(_ACK_SETTINGS_KEY, None)
    _save_settings(db, tenant_id, settings)

    _audit(db, tenant_id, action_name, "success", {"actor": actor, "cleared_count": cleared_count})
    return _ok(action_name, tenant_id, f"Cleared {cleared_count} acknowledged items.")


# ---------------------------------------------------------------------------
# Action 7: Inspect tenant operational state
# ---------------------------------------------------------------------------

def get_tenant_ops_state(
    db: Session,
    tenant_id: str,
    app_settings: Any = None,
) -> dict[str, Any]:
    """
    Aggregate operational state for the support console.

    Returns:
      automation_enabled  – bool (inverse of demo_mode)
      scheduler_mode      – run_mode string
      integrations_health – from integration_health service
      failed_jobs_count   – count of failed jobs last 48h
      stale_approvals     – count of pending approvals > 24h
      acknowledged_items  – dict of acked items
      recent_audit_events – last 10 events (safe fields only)
    """
    from datetime import timedelta

    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        return {
            "error": "Tenant not found",
            "tenant_id": tenant_id,
        }

    settings = record.settings or {}
    automation = settings.get("automation") or {}
    scheduler = settings.get("scheduler") or {}
    demo_mode = bool(automation.get("demo_mode", False))
    scheduler_mode = scheduler.get("run_mode") or "manual"

    # Integration health
    integrations_health: dict = {}
    try:
        if app_settings:
            integrations_health = get_integration_health(db, tenant_id, app_settings=app_settings)
    except Exception:
        integrations_health = {"error": "Could not load integration health"}

    # Failed jobs (last 48h)
    failed_jobs_count = 0
    try:
        cutoff = _utcnow() - timedelta(hours=48)
        failed_jobs_count = (
            db.query(JobRecord)
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.status == "failed",
                JobRecord.updated_at >= cutoff,
            )
            .count()
        )
    except Exception:
        pass

    # Stale approvals (pending > 24h)
    stale_approvals = 0
    try:
        cutoff_appr = _utcnow() - timedelta(hours=24)
        stale_approvals = (
            db.query(ApprovalRequestRecord)
            .filter(
                ApprovalRequestRecord.tenant_id == tenant_id,
                ApprovalRequestRecord.state == "pending",
                ApprovalRequestRecord.created_at < cutoff_appr,
            )
            .count()
        )
    except Exception:
        pass

    # Recent audit events
    recent_events: list[dict] = []
    try:
        events = (
            db.query(AuditEventRecord)
            .filter(AuditEventRecord.tenant_id == tenant_id)
            .order_by(AuditEventRecord.created_at.desc())
            .limit(10)
            .all()
        )
        recent_events = [
            {
                "action": e.action,
                "category": e.category,
                "status": e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]
    except Exception:
        pass

    return {
        "tenant_id": tenant_id,
        "automation_enabled": not demo_mode,
        "scheduler_mode": scheduler_mode,
        "integrations_health": integrations_health,
        "failed_jobs_48h": failed_jobs_count,
        "stale_approvals_24h": stale_approvals,
        "acknowledged_items": settings.get(_ACK_SETTINGS_KEY) or {},
        "recent_audit_events": recent_events,
    }
