"""
Production Alerting Engine (Slice 3).

Evaluates operational alert conditions for a tenant, deduplicates emissions
within a configurable window, and sends alerts via the existing email action
path (send_email through action_executor).

Alert config lives in tenant_configs.settings.alerts:
  {
    "enabled":           bool,        # default True
    "recipient_email":   str,         # operator address
    "channel":           "email",     # future: "slack"
    "dedup_window_hours": int,        # default 4
    "thresholds": {
      "failed_jobs_count":     int,   # default 3
      "dispatch_failures":     int,   # default 3
      "stale_approval_hours":  int,   # default 24
    }
  }

Alert types
-----------
repeated_failed_jobs        – N+ failed jobs in last 48h
gmail_oauth_failure         – failed audit event in oauth/inbox_sync category
scheduler_failure           – scheduler_state.last_status == "failed"
repeated_dispatch_failures  – N+ failed integration_events in last 48h
stale_approvals             – M+ pending approvals older than K hours
integration_health_critical – any system with status="error" in integration health

Dedup key: settings.alerts.last_sent is a dict of {alert_type: last_sent_at_iso}
An alert is only re-emitted after dedup_window_hours has elapsed since last emission.

All alert sends are audit-logged with category="alert".
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.domain.integrations.models import IntegrationEvent
from app.health.integration_health import get_integration_health

logger = logging.getLogger(__name__)

_ALERT_SETTINGS_KEY = "alerts"
_LAST_SENT_KEY = "last_sent"

_DEFAULT_THRESHOLDS = {
    "failed_jobs_count": 3,
    "dispatch_failures": 3,
    "stale_approval_hours": 24,
}
_DEFAULT_DEDUP_HOURS = 4


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def get_alert_config(settings: dict) -> dict:
    return dict(settings.get(_ALERT_SETTINGS_KEY) or {})


def save_alert_config(db: Session, tenant_id: str, settings: dict, alert_cfg: dict) -> None:
    settings[_ALERT_SETTINGS_KEY] = alert_cfg
    TenantConfigRepository.update_settings(db, tenant_id, settings)


def _threshold(alert_cfg: dict, key: str) -> int:
    return int((alert_cfg.get("thresholds") or {}).get(key, _DEFAULT_THRESHOLDS.get(key, 3)))


def _dedup_hours(alert_cfg: dict) -> int:
    return int(alert_cfg.get("dedup_window_hours", _DEFAULT_DEDUP_HOURS))


def _last_sent(alert_cfg: dict, alert_type: str) -> datetime | None:
    sent_map: dict = alert_cfg.get(_LAST_SENT_KEY) or {}
    raw = sent_map.get(alert_type)
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None


def _should_send(alert_cfg: dict, alert_type: str) -> bool:
    last = _last_sent(alert_cfg, alert_type)
    if last is None:
        return True
    window = timedelta(hours=_dedup_hours(alert_cfg))
    return (_utcnow() - last) >= window


def _mark_sent(alert_cfg: dict, alert_type: str) -> dict:
    sent_map = dict(alert_cfg.get(_LAST_SENT_KEY) or {})
    sent_map[alert_type] = _utcnow().isoformat()
    alert_cfg[_LAST_SENT_KEY] = sent_map
    return alert_cfg


# ---------------------------------------------------------------------------
# Alert evaluators — each returns a dict or None (None = no alert needed)
# ---------------------------------------------------------------------------

def _eval_repeated_failed_jobs(db: Session, tenant_id: str, alert_cfg: dict) -> dict | None:
    threshold = _threshold(alert_cfg, "failed_jobs_count")
    cutoff = _utcnow() - timedelta(hours=48)
    try:
        count = (
            db.query(JobRecord)
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.status == "failed",
                JobRecord.updated_at >= cutoff,
            )
            .count()
        )
    except Exception:
        return None

    if count >= threshold:
        return {
            "type": "repeated_failed_jobs",
            "title": f"{count} misslyckade jobb de senaste 48 timmarna",
            "detail": f"Gränsvärde: {threshold}. Kontrollera ärendeloggen och försök igen via återhämtningskonsolen.",
            "recommended_action": "Öppna Super Admin → behöver hjälp och kör 'Försök igen' på misslyckade jobb.",
            "severity": "high",
            "count": count,
        }
    return None


def _eval_gmail_oauth_failure(db: Session, tenant_id: str) -> dict | None:
    cutoff = _utcnow() - timedelta(hours=24)
    try:
        hit = (
            db.query(AuditEventRecord)
            .filter(
                AuditEventRecord.tenant_id == tenant_id,
                AuditEventRecord.status == "failed",
                AuditEventRecord.category.in_(["oauth", "inbox_sync"]),
                AuditEventRecord.created_at >= cutoff,
            )
            .order_by(AuditEventRecord.created_at.desc())
            .first()
        )
    except Exception:
        return None

    if hit:
        return {
            "type": "gmail_oauth_failure",
            "title": "Gmail OAuth/inkorg-sync misslyckades",
            "detail": f"Kategori: {hit.category}. Åtgärd: {hit.action}. Se OAuth-runbook för återhämtning.",
            "recommended_action": "Kontrollera Gmail OAuth-tokens. Se docs/runbook-oauth.md.",
            "severity": "critical",
        }
    return None


def _eval_scheduler_failure(settings: dict) -> dict | None:
    state = (settings.get("scheduler_state") or {})
    if state.get("last_status") == "failed":
        error = state.get("last_error") or "okänt fel"
        return {
            "type": "scheduler_failure",
            "title": "Scheduler misslyckades vid senaste körning",
            "detail": f"Fel: {str(error)[:200]}. Se docs/runbook-scheduler.md.",
            "recommended_action": "Kör 'POST /scheduler/run-once' manuellt och kontrollera loggar.",
            "severity": "high",
        }
    return None


def _eval_repeated_dispatch_failures(db: Session, tenant_id: str, alert_cfg: dict) -> dict | None:
    threshold = _threshold(alert_cfg, "dispatch_failures")
    cutoff = _utcnow() - timedelta(hours=48)
    try:
        count = (
            db.query(IntegrationEvent)
            .filter(
                IntegrationEvent.tenant_id == tenant_id,
                IntegrationEvent.status == "failed",
                IntegrationEvent.created_at >= cutoff,
            )
            .count()
        )
    except Exception:
        return None

    if count >= threshold:
        return {
            "type": "repeated_dispatch_failures",
            "title": f"{count} misslyckade dispatch-händelser de senaste 48 timmarna",
            "detail": f"Gränsvärde: {threshold}. Kontrollera integration-credentials och ärenden.",
            "recommended_action": "Kontrollera Monday/Gmail-konfiguration och försök dispatch igen.",
            "severity": "high",
            "count": count,
        }
    return None


def _eval_stale_approvals(db: Session, tenant_id: str, alert_cfg: dict) -> dict | None:
    hours = _threshold(alert_cfg, "stale_approval_hours")
    cutoff = _utcnow() - timedelta(hours=hours)
    try:
        count = (
            db.query(ApprovalRequestRecord)
            .filter(
                ApprovalRequestRecord.tenant_id == tenant_id,
                ApprovalRequestRecord.state == "pending",
                ApprovalRequestRecord.created_at < cutoff,
            )
            .count()
        )
    except Exception:
        return None

    if count > 0:
        return {
            "type": "stale_approvals",
            "title": f"{count} godkännanden har väntat mer än {hours} timmar",
            "detail": f"Väntande godkännanden riskerar att blockera workflows. Granska och godkänn eller avvisa.",
            "recommended_action": "Öppna Ärenden → Godkänna väntande poster.",
            "severity": "high",
            "count": count,
        }
    return None


def _eval_integration_health_critical(db: Session, tenant_id: str, app_settings: Any) -> dict | None:
    try:
        health = get_integration_health(db, tenant_id, app_settings=app_settings)
        systems = health.get("systems") or {}
        critical = [s for s, d in systems.items() if d.get("status") == "error"]
    except Exception:
        return None

    if critical:
        names = ", ".join(critical)
        return {
            "type": "integration_health_critical",
            "title": f"Kritisk integrationsstatus: {names}",
            "detail": f"Systemen {names} rapporterar fel. Verifiera credentials och kör skanner.",
            "recommended_action": "Öppna Integrationshälsa och kör verifiering.",
            "severity": "critical",
        }
    return None


# ---------------------------------------------------------------------------
# Alert sender
# ---------------------------------------------------------------------------

def _build_alert_email(tenant_id: str, alert: dict, recipient: str) -> tuple[str, str]:
    severity_sv = {"critical": "KRITISK", "high": "HÖG", "medium": "MEDEL"}.get(alert.get("severity", "high"), "HÖG")
    title = alert.get("title", "Okänt larm")
    detail = alert.get("detail", "")
    action = alert.get("recommended_action", "")
    subject = f"[{severity_sv}] Krowolf-larm: {title}"
    body = (
        f"Plattformslarm för kund {tenant_id}\n\n"
        f"Typ: {alert.get('type', 'unknown')}\n"
        f"Allvarlighetsgrad: {severity_sv}\n\n"
        f"{title}\n\n"
        f"{detail}\n\n"
        f"Rekommenderad åtgärd:\n{action}\n\n"
        f"Tidpunkt: {_utcnow().isoformat()}\n"
    )
    return subject, body


def _send_alert(
    db: Session,
    tenant_id: str,
    alert: dict,
    recipient: str,
    app_settings: Any,
) -> bool:
    """Send the alert email. Returns True on success, False on failure."""
    from app.workflows.action_executor import execute_action as _dispatch

    subject, body = _build_alert_email(tenant_id, alert, recipient)
    try:
        _dispatch({
            "type": "send_email",
            "tenant_id": tenant_id,
            "to": recipient,
            "subject": subject,
            "body": body,
        })
        return True
    except Exception:
        logger.exception("Alert send failed for tenant %s type %s", tenant_id, alert.get("type"))
        return False


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------

def _audit_alert(db: Session, tenant_id: str, alert_type: str, status: str, details: dict) -> None:
    try:
        create_audit_event(
            db=db,
            tenant_id=tenant_id,
            category="alert",
            action=alert_type,
            status=status,
            details=details,
        )
    except Exception:
        logger.exception("Failed to audit alert emission for %s/%s", tenant_id, alert_type)


# ---------------------------------------------------------------------------
# Public: run alert pass for one tenant
# ---------------------------------------------------------------------------

def run_alert_pass(
    db: Session,
    tenant_id: str,
    app_settings: Any,
) -> dict[str, Any]:
    """
    Evaluate all alert conditions for a tenant and send deduped notifications.

    Returns a summary dict: {evaluated, sent, skipped_dedup, errors}.
    """
    settings = TenantConfigRepository.get_settings(db, tenant_id)
    alert_cfg = get_alert_config(settings)

    if not alert_cfg.get("enabled", True):
        return {"tenant_id": tenant_id, "skipped": True, "reason": "alerts_disabled"}

    recipient = alert_cfg.get("recipient_email") or ""
    if not recipient:
        return {"tenant_id": tenant_id, "skipped": True, "reason": "no_recipient_configured"}

    # Evaluate all alert types
    candidates: list[dict] = []
    for evaluator, *args in [
        (_eval_repeated_failed_jobs, db, tenant_id, alert_cfg),
        (_eval_gmail_oauth_failure, db, tenant_id),
        (_eval_scheduler_failure, settings),
        (_eval_repeated_dispatch_failures, db, tenant_id, alert_cfg),
        (_eval_stale_approvals, db, tenant_id, alert_cfg),
        (_eval_integration_health_critical, db, tenant_id, app_settings),
    ]:
        try:
            result = evaluator(*args)
            if result:
                candidates.append(result)
        except Exception:
            logger.exception("Alert evaluator %s failed for tenant %s", evaluator.__name__, tenant_id)

    sent: list[str] = []
    skipped_dedup: list[str] = []
    errors: list[str] = []

    for alert in candidates:
        alert_type = alert["type"]
        if not _should_send(alert_cfg, alert_type):
            skipped_dedup.append(alert_type)
            continue

        success = _send_alert(db, tenant_id, alert, recipient, app_settings)
        if success:
            alert_cfg = _mark_sent(alert_cfg, alert_type)
            sent.append(alert_type)
            _audit_alert(db, tenant_id, alert_type, "success", {
                "recipient": recipient,
                "severity": alert.get("severity"),
                "title": alert.get("title"),
            })
        else:
            errors.append(alert_type)
            _audit_alert(db, tenant_id, alert_type, "failed", {
                "recipient": recipient,
                "error": "send_failed",
            })

    # Persist updated last_sent map
    if sent or alert_cfg.get(_LAST_SENT_KEY):
        save_alert_config(db, tenant_id, settings, alert_cfg)

    return {
        "tenant_id": tenant_id,
        "skipped": False,
        "evaluated": len(candidates),
        "sent": sent,
        "skipped_dedup": skipped_dedup,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Public: get/put alert config (for admin UI endpoint)
# ---------------------------------------------------------------------------

def get_alerts_config_for_tenant(db: Session, tenant_id: str) -> dict:
    settings = TenantConfigRepository.get_settings(db, tenant_id)
    cfg = get_alert_config(settings)
    # Return safe view (no last_sent internals cluttering UI)
    return {
        "enabled": cfg.get("enabled", True),
        "recipient_email": cfg.get("recipient_email", ""),
        "channel": cfg.get("channel", "email"),
        "dedup_window_hours": cfg.get("dedup_window_hours", _DEFAULT_DEDUP_HOURS),
        "thresholds": {**_DEFAULT_THRESHOLDS, **(cfg.get("thresholds") or {})},
        "last_sent": cfg.get(_LAST_SENT_KEY) or {},
    }


def save_alerts_config_for_tenant(
    db: Session,
    tenant_id: str,
    enabled: bool,
    recipient_email: str,
    channel: str = "email",
    dedup_window_hours: int = _DEFAULT_DEDUP_HOURS,
    thresholds: dict | None = None,
) -> dict:
    settings = TenantConfigRepository.get_settings(db, tenant_id)
    existing_cfg = get_alert_config(settings)
    existing_cfg.update({
        "enabled": enabled,
        "recipient_email": recipient_email,
        "channel": channel,
        "dedup_window_hours": dedup_window_hours,
        "thresholds": {**_DEFAULT_THRESHOLDS, **(thresholds or {})},
    })
    save_alert_config(db, tenant_id, settings, existing_cfg)
    return get_alerts_config_for_tenant(db, tenant_id)
