"""
Auto-dispatch hook for full_auto pipeline integration.

Called after a job completes (status=COMPLETED) to automatically
dispatch it to the configured external system when all conditions are met.

Supported paths: lead → monday (only)

Conditions to dispatch:
1. job_type == "lead"
2. dispatch policy == "full_auto"
3. routing hint is present and valid (status == "ready")
4. routing hint system == "monday"
5. dispatch adapter exists for (monday, lead)
6. duplicate protection passes (integration_events idempotency_key)

All conditions are checked before any external write.
A failure in auto-dispatch must not crash the job's own pipeline flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_tenant_config
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.workflows.dispatchers.engine import ControlledDispatchEngine, DISPATCH_REGISTRY
from app.workflows.dispatchers.policy import resolve_dispatch_policy
from app.workflows.scanners.routing_preview import resolve_routing_preview

SUPPORTED_JOB_TYPE   = "lead"
SUPPORTED_SYSTEM     = "monday"


@dataclass
class AutoDispatchResult:
    status: str          # "success" | "skipped" | "failed"
    reason: str          # human-readable explanation
    dispatch_result: dict[str, Any] | None = field(default=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status":          self.status,
            "reason":          self.reason,
            "dispatch_result": self.dispatch_result,
        }


def maybe_auto_dispatch_job(
    db: Session,
    tenant_id: str,
    job: Any,           # JobRecord or domain Job — duck-typed for flexibility
    settings: Any,
) -> AutoDispatchResult:
    """
    Attempt automatic dispatch for a completed job.

    Returns AutoDispatchResult — never raises.
    """
    try:
        # --- 1. Check job_type ---
        raw_job_type = getattr(job, "job_type", None)
        if hasattr(raw_job_type, "value"):
            job_type_str = raw_job_type.value
        else:
            job_type_str = str(raw_job_type) if raw_job_type else ""

        if job_type_str != SUPPORTED_JOB_TYPE:
            return AutoDispatchResult(
                status="skipped",
                reason=f"job_type '{job_type_str}' not supported for auto-dispatch (only 'lead')",
            )

        # --- 2. Check policy ---
        tenant_cfg = get_tenant_config(tenant_id, db=db)
        policy = resolve_dispatch_policy(tenant_cfg, job_type_str)

        if policy["policy_mode"] != "full_auto":
            return AutoDispatchResult(
                status="skipped",
                reason=f"policy_mode is '{policy['policy_mode']}'; full_auto required for auto-dispatch",
            )

        # --- 3. Check routing hint/readiness ---
        s = TenantConfigRepository.get_settings(db, tenant_id)
        memory = s.get("memory") or {}
        routing_hints = memory.get("routing_hints") or {}

        preview = resolve_routing_preview(routing_hints, job_type_str)
        if preview["status"] != "ready":
            return AutoDispatchResult(
                status="skipped",
                reason=f"routing preview status is '{preview['status']}'; must be 'ready'",
            )

        # --- 4. Check system ---
        system = preview.get("system") or ""
        if system != SUPPORTED_SYSTEM:
            return AutoDispatchResult(
                status="skipped",
                reason=f"routing target system '{system}' not supported for auto-dispatch (only 'monday')",
            )

        # --- 5. Check adapter exists ---
        if (SUPPORTED_SYSTEM, SUPPORTED_JOB_TYPE) not in DISPATCH_REGISTRY:
            return AutoDispatchResult(
                status="skipped",
                reason="No dispatch adapter registered for (monday, lead)",
            )

        # --- 6. Run dispatch (engine handles duplicate guard internally) ---
        engine = ControlledDispatchEngine(db=db, tenant_id=tenant_id, settings=settings)
        result = engine.run(job=job, memory=memory, dry_run=False, dispatch_mode="full_auto")

        return AutoDispatchResult(
            status=result.status,
            reason=result.message or result.status,
            dispatch_result=result.to_dict(),
        )

    except Exception as exc:
        return AutoDispatchResult(
            status="failed",
            reason=f"auto-dispatch error: {type(exc).__name__}",
        )
