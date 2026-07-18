"""
Pilot / production readiness service.

Evaluates whether the platform is ready for a live pilot run.
All checks are deterministic and read-only — no external API calls.
No secrets are included in the response.

Checks:
  auth_configured              — env or DB-backed tenant API keys are configured
  tenant_exists                — at least one tenant row in DB
  onboarding_ready             — onboarding status == "ready" for the tenant
  integrations_health_not_error — integration health overall_status != "error"
  routing_ready_for_lead       — routing preview for "lead" is "ready"
  dispatch_duplicate_protection — integration_events table has idempotency support (column exists)
  dispatch_observability        — at least one integration event exists for the tenant
  scheduler_safe               — run_mode != "scheduled" OR Gmail is configured
  required_env_present         — APP_NAME set + at least one integration env set
  ui_available                 — index.html file present on disk
  test_lead_exists             — at least one lead job exists for the tenant

Overall status: ready | almost_ready | not_ready
  ready        — all checks pass
  almost_ready — only warnings, no failures
  not_ready    — at least one failure
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

# Module-level imports for test patchability
from app.health.integration_health import get_integration_health
from app.onboarding.readiness import get_onboarding_status
from app.workflows.scanners.external_routing_resolver import resolve_effective_routing_preview
from app.workflows.scanners.routing_preview import resolve_routing_preview

_UI_PATH = Path(__file__).parent.parent / "ui" / "index.html"

_CHECK_KEYS = [
    "auth_configured",
    "tenant_exists",
    "onboarding_ready",
    "integrations_health_not_error",
    "routing_ready_for_lead",
    "dispatch_duplicate_protection",
    "dispatch_observability",
    "scheduler_safe",
    "required_env_present",
    "ui_available",
    "test_lead_exists",
]


# ---------------------------------------------------------------------------
# Individual check helpers
# ---------------------------------------------------------------------------

def _db_has_active_tenant_api_keys(db: Session | None) -> bool:
    if db is None:
        return False
    try:
        from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord
        return (
            db.query(TenantApiKeyRecord)
            .filter(TenantApiKeyRecord.is_active.is_(True))
            .limit(1)
            .first()
            is not None
        )
    except Exception:
        return False


def _check_auth_configured(app_settings: Any, db: Session | None = None) -> tuple[str, str, str]:
    configured = bool(getattr(app_settings, "TENANT_API_KEYS", ""))
    if configured:
        return "pass", "TENANT_API_KEYS konfigurerat.", "info"
    if _db_has_active_tenant_api_keys(db):
        return "pass", "DB-baserade tenant API-nycklar är konfigurerade.", "info"
    if str(getattr(app_settings, "ENV", "") or "").strip().lower() in {"prod", "production"}:
        return "fail", "Ingen tenant-auth konfigurerad i production.", "error"
    return "warning", "TENANT_API_KEYS ej satt — endast lokalt dev-läge får sakna tenant-auth.", "warning"


def _check_tenant_exists(db: Session) -> tuple[str, str, str]:
    tenants = TenantConfigRepository.list_all(db)
    if tenants:
        return "pass", f"{len(tenants)} tenant(s) finns i databasen.", "info"
    return "fail", "Inga tenants i databasen. Skapa ett via POST /tenant.", "error"


def _check_onboarding_ready(db: Session, tenant_id: str, app_settings: Any) -> tuple[str, str, str]:
    status = get_onboarding_status(db, tenant_id, app_settings=app_settings)
    overall = status.get("status", "not_started")
    score = status.get("score", {})
    completed = score.get("completed", 0)
    total = score.get("total", 8)
    if overall == "ready":
        return "pass", "Alla onboarding-steg klara.", "info"
    if overall == "in_progress":
        return "warning", f"Onboarding pågår: {completed}/{total} steg klara.", "warning"
    return "fail", "Onboarding ej påbörjad.", "error"


def _check_integrations_health(db: Session, tenant_id: str, app_settings: Any) -> tuple[str, str, str]:
    health = get_integration_health(db, tenant_id, app_settings=app_settings)
    overall = health.get("overall_status", "warning")
    if overall == "healthy":
        return "pass", "Alla integrationer är friska.", "info"
    if overall == "warning":
        return "warning", "En eller fler integrationer har varningar.", "warning"
    return "fail", "En eller fler integrationer rapporterar fel.", "error"


def _check_routing_for_lead(db: Session, tenant_id: str) -> tuple[str, str, str]:
    settings = TenantConfigRepository.get_settings(db, tenant_id)
    memory = settings.get("memory") or {}
    routing_hints = memory.get("routing_hints") or {}
    preview = resolve_effective_routing_preview(
        job_type="lead",
        tenant_settings=settings,
        memory=memory,
    )
    status = preview.get("status", "missing_hint")
    if status == "ready":
        system = preview.get("system", "")
        return "pass", f"Lead-routing klar → {system}.", "info"
    if status == "invalid_hint":
        return "warning", f"Lead-routing hint är ogiltig: {preview.get('message', '')}.", "warning"
    return "warning", "Ingen routing-hint sparad för lead.", "warning"


def _check_dispatch_duplicate_protection(db: Session, tenant_id: str) -> tuple[str, str, str]:
    from app.domain.integrations.models import IntegrationEvent  # avoid circular
    # Check that the idempotency_key column exists by doing a minimal query
    try:
        db.query(IntegrationEvent.idempotency_key).limit(1).all()
        return "pass", "Duplicate-skydd via idempotency_key aktivt.", "info"
    except Exception:
        return "fail", "idempotency_key-kolumn saknas i integration_events.", "error"


def _check_dispatch_observability(db: Session, tenant_id: str) -> tuple[str, str, str]:
    from app.domain.integrations.models import IntegrationEvent  # avoid circular
    count = (
        db.query(IntegrationEvent)
        .filter(IntegrationEvent.tenant_id == tenant_id)
        .count()
    )
    if count > 0:
        return "pass", f"{count} integration-händelse(r) loggade.", "info"
    return "warning", "Inga integration-händelser loggade än. Kör ett dispatch.", "warning"


def _check_scheduler_safe(db: Session, tenant_id: str, app_settings: Any) -> tuple[str, str, str]:
    settings = TenantConfigRepository.get_settings(db, tenant_id)
    scheduler = settings.get("scheduler") or {}
    run_mode = scheduler.get("run_mode", "manual")
    gmail_ok = bool(getattr(app_settings, "GOOGLE_MAIL_ACCESS_TOKEN", ""))
    if run_mode == "scheduled" and not gmail_ok:
        return "warning", (
            "Scheduler är i 'scheduled'-läge men GOOGLE_MAIL_ACCESS_TOKEN saknas. "
            "Inkorgssynk kommer misslyckas."
        ), "warning"
    if run_mode == "paused":
        return "warning", "Scheduler är pausad — automatisering inaktiv.", "warning"
    return "pass", f"Scheduler run_mode='{run_mode}' är säker.", "info"


def _check_required_env(app_settings: Any) -> tuple[str, str, str]:
    app_name = bool(getattr(app_settings, "APP_NAME", ""))
    gmail_set = bool(getattr(app_settings, "GOOGLE_MAIL_ACCESS_TOKEN", ""))
    monday_set = bool(getattr(app_settings, "MONDAY_API_KEY", ""))
    if not app_name:
        return "fail", "APP_NAME saknas i miljövariabler.", "error"
    if not gmail_set and not monday_set:
        return "warning", "Varken GOOGLE_MAIL_ACCESS_TOKEN eller MONDAY_API_KEY är satt.", "warning"
    set_list = [s for s, ok in [("Gmail", gmail_set), ("Monday", monday_set)] if ok]
    return "pass", f"Obligatoriska env-variabler ok. Integrationer satta: {', '.join(set_list)}.", "info"


def _check_ui_available() -> tuple[str, str, str]:
    if _UI_PATH.exists():
        return "pass", "Operatörsgränssnitt tillgängligt på /ui.", "info"
    return "fail", f"index.html saknas: {_UI_PATH}", "error"


def _check_test_lead_exists(db: Session, tenant_id: str) -> tuple[str, str, str]:
    count = JobRepository.count_jobs_for_tenant(db, tenant_id, job_type="lead")
    if count > 0:
        return "pass", f"{count} lead-jobb finns. Pipeline verifierad.", "info"
    return "warning", "Inga lead-jobb för tenanten. Skapa ett testlead.", "warning"


# ---------------------------------------------------------------------------
# Overall status aggregation
# ---------------------------------------------------------------------------

def _overall_status(checks: list[dict]) -> str:
    statuses = [c["status"] for c in checks]
    if "fail" in statuses:
        return "not_ready"
    if "warning" in statuses:
        return "almost_ready"
    return "ready"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_pilot_readiness(
    db: Session,
    tenant_id: str,
    *,
    app_settings: Any,
) -> dict[str, Any]:
    """
    Evaluate pilot/production readiness for the given tenant.

    All checks are read-only and deterministic. No external API calls.
    """
    evaluators = {
        "auth_configured":              lambda: _check_auth_configured(app_settings, db),
        "tenant_exists":                lambda: _check_tenant_exists(db),
        "onboarding_ready":             lambda: _check_onboarding_ready(db, tenant_id, app_settings),
        "integrations_health_not_error": lambda: _check_integrations_health(db, tenant_id, app_settings),
        "routing_ready_for_lead":       lambda: _check_routing_for_lead(db, tenant_id),
        "dispatch_duplicate_protection": lambda: _check_dispatch_duplicate_protection(db, tenant_id),
        "dispatch_observability":       lambda: _check_dispatch_observability(db, tenant_id),
        "scheduler_safe":               lambda: _check_scheduler_safe(db, tenant_id, app_settings),
        "required_env_present":         lambda: _check_required_env(app_settings),
        "ui_available":                 _check_ui_available,
        "test_lead_exists":             lambda: _check_test_lead_exists(db, tenant_id),
    }

    checks = []
    for key in _CHECK_KEYS:
        result_status, message, severity = evaluators[key]()
        checks.append({
            "key":      key,
            "status":   result_status,
            "message":  message,
            "severity": severity,
        })

    passed   = sum(1 for c in checks if c["status"] == "pass")
    warnings = sum(1 for c in checks if c["status"] == "warning")
    failures = sum(1 for c in checks if c["status"] == "fail")

    return {
        "tenant_id":      tenant_id,
        "overall_status": _overall_status(checks),
        "score": {
            "passed":   passed,
            "warnings": warnings,
            "failures": failures,
            "total":    len(checks),
        },
        "checks": checks,
    }
