"""
Generic Controlled Dispatch Engine.

Resolves the correct adapter for (system, job_type), validates the routing
hint, checks for duplicate dispatches, and delegates to the adapter.

Adding a new adapter:
  1. Implement BaseDispatchAdapter in its own module.
  2. Register an instance in DISPATCH_REGISTRY.

The engine never writes externally in dry_run mode.
"""

from __future__ import annotations

from typing import Any

from app.workflows.dispatchers.base import BaseDispatchAdapter, DispatchResult
from app.workflows.dispatchers.monday_lead_adapter import MondayLeadDispatchAdapter
from app.workflows.scanners.routing_preview import resolve_routing_preview, SUPPORTED_JOB_TYPES

# ---------------------------------------------------------------------------
# Registry  key = (system, job_type)
# ---------------------------------------------------------------------------

DISPATCH_REGISTRY: dict[tuple[str, str], BaseDispatchAdapter] = {
    ("monday", "lead"): MondayLeadDispatchAdapter(),
    # ("hubspot",  "lead"):             HubSpotLeadDispatchAdapter(),   # future
    # ("pipedrive","lead"):             PipedriveLeadDispatchAdapter(), # future
    # ("monday",   "customer_inquiry"): MondayInquiryDispatchAdapter(), # future
}


def list_supported_dispatches() -> list[dict]:
    return [{"system": s, "job_type": jt} for s, jt in sorted(DISPATCH_REGISTRY)]


# ---------------------------------------------------------------------------
# Duplicate check helpers
# ---------------------------------------------------------------------------

_DISPATCH_INTEGRATION_TYPE = "controlled_dispatch"


def _idempotency_key(tenant_id: str, job_id: str, system: str, job_type: str) -> str:
    return f"dispatch:{tenant_id}:{job_id}:{system}:{job_type}"


def _find_existing_dispatch(db: Any, tenant_id: str, job_id: str, system: str, job_type: str):
    """Return an existing successful IntegrationEvent for this dispatch, or None."""
    from app.domain.integrations.models import IntegrationEvent

    ikey = _idempotency_key(tenant_id, job_id, system, job_type)
    return (
        db.query(IntegrationEvent)
        .filter(
            IntegrationEvent.idempotency_key == ikey,
            IntegrationEvent.tenant_id == tenant_id,
            IntegrationEvent.status == "success",
        )
        .first()
    )


def _persist_dispatch(
    db: Any,
    tenant_id: str,
    job_id: str,
    result: DispatchResult,
) -> None:
    """Persist a dispatch attempt as an IntegrationEvent (best-effort)."""
    from app.domain.integrations.models import IntegrationEvent
    from app.repositories.postgres.integration_repository import IntegrationRepository

    ikey = _idempotency_key(tenant_id, job_id, result.system, result.job_type)
    record = IntegrationEvent(
        tenant_id=tenant_id,
        job_id=job_id,
        integration_type=_DISPATCH_INTEGRATION_TYPE,
        payload={
            "system":       result.system,
            "job_type":     result.job_type,
            "target":       result.target,
            "external_id":  result.external_id,
            "message":      result.message,
            "details":      result.details,
        },
        status=result.status,
        attempts=1,
        idempotency_key=ikey,
    )
    repo = IntegrationRepository(db)
    try:
        repo.create(record)
    except Exception:
        pass  # idempotency_key unique constraint hit → already recorded


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ControlledDispatchEngine:
    """
    Orchestrates dispatch: hint validation → duplicate check → adapter → persist.

    Usage
    -----
    engine = ControlledDispatchEngine(db, tenant_id, settings)
    result = engine.run(job, memory, dry_run=False)
    """

    def __init__(self, db: Any, tenant_id: str, settings: Any):
        self._db = db
        self._tenant_id = tenant_id
        self._settings = settings

    def run(self, job: Any, memory: dict, dry_run: bool = False) -> DispatchResult:
        """
        Dispatch job using memory.routing_hints.

        Parameters
        ----------
        job      : JobRecord (or any object with .job_id and .job_type attributes)
        memory   : tenant memory dict (from _get_memory)
        dry_run  : when True, never write externally
        """
        job_type = str(getattr(job, "job_type", None) or "")

        if job_type not in SUPPORTED_JOB_TYPES:
            return DispatchResult(
                status="failed",
                system="unknown",
                job_type=job_type,
                message=f"Unsupported job type '{job_type}' for dispatch",
            )

        routing_hints = memory.get("routing_hints") or {}
        preview = resolve_routing_preview(routing_hints, job_type)

        if preview["status"] == "missing_hint":
            return DispatchResult(
                status="failed",
                system="unknown",
                job_type=job_type,
                message=f"No routing hint saved for job type '{job_type}'. "
                         "Use POST /tenant/routing-hints/apply to configure routing.",
            )

        if preview["status"] == "invalid_hint":
            return DispatchResult(
                status="failed",
                system="unknown",
                job_type=job_type,
                message=f"Routing hint for '{job_type}' is malformed: {preview['message']}",
            )

        system = preview["system"]
        routing_hint = routing_hints[job_type]

        adapter = DISPATCH_REGISTRY.get((system, job_type))
        if adapter is None:
            return DispatchResult(
                status="failed",
                system=system,
                job_type=job_type,
                message=f"No dispatch adapter registered for system='{system}' job_type='{job_type}'",
            )

        # Duplicate guard — only for live dispatches
        if not dry_run:
            job_id = str(getattr(job, "job_id", "") or "")
            existing = _find_existing_dispatch(self._db, self._tenant_id, job_id, system, job_type)
            if existing:
                return DispatchResult(
                    status="skipped",
                    system=system,
                    job_type=job_type,
                    target=routing_hint.get("target") or {},
                    message="Redan skickad — Already dispatched to this target",
                )

        result = adapter.dispatch(
            job=job,
            routing_hint=routing_hint,
            settings=self._settings,
            dry_run=dry_run,
        )

        # Persist attempt (skip for dry_run and skipped)
        if not dry_run and result.status in ("success", "failed"):
            job_id = str(getattr(job, "job_id", "") or "")
            _persist_dispatch(self._db, self._tenant_id, job_id, result)

        return result
