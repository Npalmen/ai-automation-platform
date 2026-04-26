"""
Onboarding readiness service.

Computes a tenant's onboarding checklist from existing platform state.
All checks are deterministic and read-only — no external API calls.

Step keys and completion rules:
  tenant_created        — tenant row exists in tenant_configs
  gmail_ready           — GOOGLE_MAIL_ACCESS_TOKEN set OR Gmail scan succeeded before
  monday_ready          — MONDAY_API_KEY set OR Monday scan succeeded before
  systems_scanned       — workflow_scan.systems_scanned contains gmail or monday
  routing_hints_saved   — at least one valid routing hint (has system + target.board_id)
  automation_policy_set — auto_actions has at least one configured job type
  test_lead_created     — at least one lead job exists for tenant (any status)
  dispatch_verified     — at least one successful controlled_dispatch event exists

Overall status:
  not_started  — 0 steps complete
  in_progress  — 1–7 steps complete
  ready        — all 8 steps complete
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

_STEP_KEYS = [
    "tenant_created",
    "gmail_ready",
    "monday_ready",
    "systems_scanned",
    "routing_hints_saved",
    "automation_policy_set",
    "test_lead_created",
    "dispatch_verified",
]

_STEP_LABELS = {
    "tenant_created":        "Tenant skapad",
    "gmail_ready":           "Gmail anslutning",
    "monday_ready":          "Monday anslutning",
    "systems_scanned":       "System skannade",
    "routing_hints_saved":   "Routing sparad",
    "automation_policy_set": "Automation vald",
    "test_lead_created":     "Testlead skapat",
    "dispatch_verified":     "Dispatch verifierad",
}


# ---------------------------------------------------------------------------
# Individual step evaluators (pure functions where possible)
# ---------------------------------------------------------------------------

def _check_tenant_created(tenant_cfg: dict | None) -> tuple[str, str]:
    if tenant_cfg is not None:
        return "complete", "Tenant finns i databasen."
    return "incomplete", "Tenant saknas. Skapa tenant via /tenant."


def _check_gmail_ready(settings: dict, app_settings: Any) -> tuple[str, str]:
    # Prefer live env var check; fall back to scanner success history
    if getattr(app_settings, "GOOGLE_MAIL_ACCESS_TOKEN", ""):
        return "complete", "GOOGLE_MAIL_ACCESS_TOKEN konfigurerat."
    scan = settings.get("workflow_scan") or {}
    summary = scan.get("summary") or {}
    gmail_scan = summary.get("gmail") or {}
    if gmail_scan.get("status") == "success":
        return "complete", "Gmail skanning lyckades tidigare."
    if scan.get("status") == "success" and "gmail" in (scan.get("systems_scanned") or []):
        return "complete", "Gmail inkluderat i lyckad skanning."
    return "incomplete", "Konfigurera GOOGLE_MAIL_ACCESS_TOKEN eller skanna Gmail."


def _check_monday_ready(settings: dict, app_settings: Any) -> tuple[str, str]:
    if getattr(app_settings, "MONDAY_API_KEY", ""):
        return "complete", "MONDAY_API_KEY konfigurerat."
    scan = settings.get("workflow_scan") or {}
    summary = scan.get("summary") or {}
    monday_scan = summary.get("monday") or {}
    if monday_scan.get("status") == "success":
        return "complete", "Monday skanning lyckades tidigare."
    if scan.get("status") == "success" and "monday" in (scan.get("systems_scanned") or []):
        return "complete", "Monday inkluderat i lyckad skanning."
    return "incomplete", "Konfigurera MONDAY_API_KEY eller skanna Monday."


def _check_systems_scanned(settings: dict) -> tuple[str, str]:
    scan = settings.get("workflow_scan") or {}
    scanned = scan.get("systems_scanned") or []
    found = [s for s in scanned if s in ("gmail", "monday")]
    if found:
        return "complete", f"Skannade system: {', '.join(found)}."
    return "incomplete", "Kör Gmail- eller Monday-skanning."


def _check_routing_hints_saved(settings: dict) -> tuple[str, str]:
    memory = settings.get("memory") or {}
    hints = memory.get("routing_hints") or {}
    valid = [
        k for k, v in hints.items()
        if isinstance(v, dict)
        and v.get("system")
        and isinstance(v.get("target"), dict)
        and v["target"].get("board_id")
    ]
    if valid:
        return "complete", f"Sparade routing-hints för: {', '.join(valid)}."
    return "incomplete", "Föreslå och spara routing-hints via Kundminne."


def _check_automation_policy(settings: dict) -> tuple[str, str]:
    auto_actions = settings.get("auto_actions") or {}
    configured = {k: v for k, v in auto_actions.items() if v not in (None, False, "")}
    if configured:
        return "complete", f"Automationsnivå satt för: {', '.join(configured.keys())}."
    return "incomplete", "Sätt automationsnivå i Kontrollpanel → auto_actions."


def _check_test_lead(db: Session, tenant_id: str) -> tuple[str, str]:
    count = JobRepository.count_jobs_for_tenant(db, tenant_id, job_type="lead")
    if count > 0:
        return "complete", f"{count} lead-jobb finns för tenanten."
    return "incomplete", "Skapa ett testlead via Onboarding-fliken."


def _check_dispatch_verified(db: Session, tenant_id: str) -> tuple[str, str]:
    from app.domain.integrations.models import IntegrationEvent  # avoid circular at import time
    exists = (
        db.query(IntegrationEvent)
        .filter(
            IntegrationEvent.tenant_id == tenant_id,
            IntegrationEvent.integration_type == "controlled_dispatch",
            IntegrationEvent.status == "success",
        )
        .first()
    )
    if exists:
        return "complete", "Minst en lyckad dispatch finns."
    return "incomplete", "Kör en dispatch (manuell, godkänd eller auto) för att verifiera."


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_onboarding_status(
    db: Session,
    tenant_id: str,
    *,
    app_settings: Any,
) -> dict[str, Any]:
    """
    Compute and return the full onboarding readiness checklist.

    All checks are read-only — no external API calls.
    """
    record = TenantConfigRepository.get(db, tenant_id)
    tenant_cfg = TenantConfigRepository.to_dict(record) if record else None
    settings = TenantConfigRepository.get_settings(db, tenant_id)

    evaluators = {
        "tenant_created":        lambda: _check_tenant_created(tenant_cfg),
        "gmail_ready":           lambda: _check_gmail_ready(settings, app_settings),
        "monday_ready":          lambda: _check_monday_ready(settings, app_settings),
        "systems_scanned":       lambda: _check_systems_scanned(settings),
        "routing_hints_saved":   lambda: _check_routing_hints_saved(settings),
        "automation_policy_set": lambda: _check_automation_policy(settings),
        "test_lead_created":     lambda: _check_test_lead(db, tenant_id),
        "dispatch_verified":     lambda: _check_dispatch_verified(db, tenant_id),
    }

    steps = []
    completed = 0
    for key in _STEP_KEYS:
        status, message = evaluators[key]()
        if status == "complete":
            completed += 1
        steps.append({
            "key":     key,
            "label":   _STEP_LABELS[key],
            "status":  status,
            "message": message,
        })

    total   = len(_STEP_KEYS)
    percent = round(completed / total * 100)

    if completed == 0:
        overall = "not_started"
    elif completed == total:
        overall = "ready"
    else:
        overall = "in_progress"

    return {
        "tenant_id": tenant_id,
        "status":    overall,
        "score": {
            "completed": completed,
            "total":     total,
            "percent":   percent,
        },
        "steps": steps,
    }
