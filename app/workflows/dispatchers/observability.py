"""
Dispatch observability service.

Reads persisted controlled_dispatch IntegrationEvents and produces:
- get_dispatch_summary(): tenant-scoped summary with optional time-range filtering
- get_dispatch_report(): executive ROI summary (customer-facing)

Time-range presets: today | 7d | 30d | all (default: 30d)
ROI assumption: 5 minutes saved per successful dispatch (deterministic).
No new schema — reads existing integration_events rows.

automation_share definition:
  (approval_required + full_auto) / total_actionable
  where total_actionable = total - skipped
  "actionable" excludes skipped because those never reached an external system.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

MINUTES_SAVED_PER_SUCCESS = 5
_DISPATCH_TYPE = "controlled_dispatch"
_VALID_MODES   = {"manual", "approval_required", "full_auto"}
_VALID_RANGES  = {"today", "7d", "30d", "all"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_payload(record: Any) -> dict:
    p = getattr(record, "payload", None) or {}
    return p if isinstance(p, dict) else {}


def _range_bounds(range_: str) -> tuple[datetime | None, datetime]:
    """Return (from_dt, to_dt) UTC bounds for a named range preset."""
    now = datetime.now(timezone.utc)
    if range_ == "today":
        from_dt = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif range_ == "7d":
        from_dt = now - timedelta(days=7)
    elif range_ == "30d":
        from_dt = now - timedelta(days=30)
    else:  # "all"
        from_dt = None
    return from_dt, now


def _range_label(range_: str) -> str:
    return {"today": "idag", "7d": "7 dagar", "30d": "30 dagar", "all": "all tid"}.get(range_, range_)


def _normalise_range(range_: str | None) -> str:
    """Coerce unknown/missing range values to '30d'."""
    if range_ in _VALID_RANGES:
        return range_
    return "30d"


# ---------------------------------------------------------------------------
# Core query
# ---------------------------------------------------------------------------

def _fetch_records(
    db: Session,
    tenant_id: str,
    range_: str,
    *,
    job_type: str | None = None,
    system: str | None = None,
) -> tuple[list[Any], datetime | None, datetime]:
    from app.domain.integrations.models import IntegrationEvent

    from_dt, to_dt = _range_bounds(range_)

    q = (
        db.query(IntegrationEvent)
        .filter(
            IntegrationEvent.tenant_id == tenant_id,
            IntegrationEvent.integration_type == _DISPATCH_TYPE,
        )
    )
    if from_dt is not None:
        q = q.filter(IntegrationEvent.created_at >= from_dt)

    records = q.order_by(IntegrationEvent.created_at.desc()).all()

    if job_type:
        records = [r for r in records if _safe_payload(r).get("job_type") == job_type]
    if system:
        records = [r for r in records if _safe_payload(r).get("system") == system]

    return records, from_dt, to_dt


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_dispatch_summary(
    db: Session,
    tenant_id: str,
    *,
    range_: str | None   = None,
    job_type: str | None = None,
    system: str | None   = None,
    limit_recent: int    = 10,
) -> dict[str, Any]:
    """
    Build a dispatch observability summary for the tenant.

    range_ preset: today | 7d | 30d | all  (default: 30d)
    All aggregation is done in Python over the result set (no complex SQL).
    Response shape is backward-compatible; adds range/from/to metadata.
    """
    range_ = _normalise_range(range_)
    records, from_dt, to_dt = _fetch_records(
        db, tenant_id, range_, job_type=job_type, system=system,
    )

    total      = len(records)
    successful = sum(1 for r in records if r.status == "success")
    failed     = sum(1 for r in records if r.status == "failed")
    skipped    = sum(1 for r in records if r.status == "skipped")

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
            "job_id":      r.job_id,
            "job_type":    p.get("job_type") or "unknown",
            "system":      p.get("system")   or "unknown",
            "status":      r.status,
            "mode":        p.get("dispatch_mode") or "unknown",
            "external_id": p.get("external_id"),
            "message":     p.get("message") or "",
            "created_at":  r.created_at.isoformat() if r.created_at else None,
        })

    return {
        "range":                   range_,
        "from":                    from_dt.isoformat() if from_dt else None,
        "to":                      to_dt.isoformat(),
        "total_dispatches":        total,
        "successful_dispatches":   successful,
        "failed_dispatches":       failed,
        "skipped_dispatches":      skipped,
        "by_mode":                 by_mode,
        "by_job_type":             by_job_type,
        "by_system":               by_system,
        "estimated_minutes_saved": minutes_saved,
        "estimated_hours_saved":   hours_saved,
        "recent":                  recent,
    }


def get_dispatch_report(
    db: Session,
    tenant_id: str,
    *,
    range_: str | None = None,
) -> dict[str, Any]:
    """
    Executive ROI report — customer-facing summary.

    automation_share = (approval_required + full_auto) / actionable
    where actionable = total - skipped (dispatches that reached the adapter).
    success_rate     = successful / actionable  (skipped excluded).
    Both are 0 when actionable == 0.
    """
    range_ = _normalise_range(range_)
    records, from_dt, to_dt = _fetch_records(db, tenant_id, range_)

    total      = len(records)
    successful = sum(1 for r in records if r.status == "success")
    skipped    = sum(1 for r in records if r.status == "skipped")

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

    actionable       = total - skipped
    hours_saved      = round(successful * MINUTES_SAVED_PER_SUCCESS / 60, 2)
    success_rate     = round(successful / actionable * 100) if actionable else 0
    auto_count       = by_mode["approval_required"] + by_mode["full_auto"]
    automation_share = round(auto_count / actionable * 100) if actionable else 0

    label = _range_label(range_)
    message = (
        f"{total} uppgifter hanterades automatiskt eller med assistans under {label}."
        if total > 0
        else f"Inga dispatches under {label}."
    )

    return {
        "range": range_,
        "from":  from_dt.isoformat() if from_dt else None,
        "to":    to_dt.isoformat(),
        "headline": {
            "dispatches_completed":    total,
            "time_saved_hours":        hours_saved,
            "success_rate_percent":    success_rate,
            "automation_share_percent": automation_share,
        },
        "breakdown":  by_mode,
        "systems":    by_system,
        "job_types":  by_job_type,
        "message":    message,
    }
