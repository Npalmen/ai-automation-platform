"""
Dispatch observability service.

Reads persisted controlled_dispatch IntegrationEvents and produces a
tenant-scoped summary suitable for the dashboard and ROI calculations.

ROI assumption: 5 minutes saved per successful dispatch (deterministic).
No new schema — reads existing integration_events rows.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

MINUTES_SAVED_PER_SUCCESS = 5
_DISPATCH_TYPE = "controlled_dispatch"
_VALID_MODES   = {"manual", "approval_required", "full_auto"}


def _safe_payload(record: Any) -> dict:
    p = getattr(record, "payload", None) or {}
    return p if isinstance(p, dict) else {}


def get_dispatch_summary(
    db: Session,
    tenant_id: str,
    *,
    job_type: str | None = None,
    system: str | None   = None,
    limit_recent: int    = 10,
) -> dict[str, Any]:
    """
    Build a dispatch observability summary for the tenant.

    Queries integration_events where integration_type='controlled_dispatch'.
    All aggregation is done in Python over the result set (no complex SQL).
    """
    from app.domain.integrations.models import IntegrationEvent

    query = (
        db.query(IntegrationEvent)
        .filter(
            IntegrationEvent.tenant_id == tenant_id,
            IntegrationEvent.integration_type == _DISPATCH_TYPE,
        )
        .order_by(IntegrationEvent.created_at.desc())
    )

    records = query.all()

    # Optional post-filters
    if job_type:
        records = [r for r in records if _safe_payload(r).get("job_type") == job_type]
    if system:
        records = [r for r in records if _safe_payload(r).get("system") == system]

    total           = len(records)
    successful      = sum(1 for r in records if r.status == "success")
    failed          = sum(1 for r in records if r.status == "failed")
    skipped         = sum(1 for r in records if r.status == "skipped")

    by_mode: dict[str, int] = {"manual": 0, "approval_required": 0, "full_auto": 0, "unknown": 0}
    by_job_type: dict[str, int] = {}
    by_system:   dict[str, int] = {}

    for r in records:
        p    = _safe_payload(r)
        mode = p.get("dispatch_mode") or "unknown"
        if mode not in _VALID_MODES:
            mode = "unknown"
        by_mode[mode] = by_mode.get(mode, 0) + 1

        jt = p.get("job_type") or "unknown"
        by_job_type[jt] = by_job_type.get(jt, 0) + 1

        sys_ = p.get("system") or "unknown"
        by_system[sys_] = by_system.get(sys_, 0) + 1

    minutes_saved = successful * MINUTES_SAVED_PER_SUCCESS
    hours_saved   = round(minutes_saved / 60, 2)

    recent = []
    for r in records[:limit_recent]:
        p = _safe_payload(r)
        recent.append({
            "job_id":    r.job_id,
            "job_type":  p.get("job_type") or "unknown",
            "system":    p.get("system")   or "unknown",
            "status":    r.status,
            "mode":      p.get("dispatch_mode") or "unknown",
            "external_id": p.get("external_id"),
            "message":   p.get("message") or "",
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {
        "total_dispatches":       total,
        "successful_dispatches":  successful,
        "failed_dispatches":      failed,
        "skipped_dispatches":     skipped,
        "by_mode":                by_mode,
        "by_job_type":            by_job_type,
        "by_system":              by_system,
        "estimated_minutes_saved": minutes_saved,
        "estimated_hours_saved":   hours_saved,
        "recent":                  recent,
    }
