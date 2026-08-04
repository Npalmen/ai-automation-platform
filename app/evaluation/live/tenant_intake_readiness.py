"""Read-only tenant intake readiness for R3 live eval canary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.workflows.intake_enforcement import parse_cutoff_at

R3_REQUIRED_JOB_TYPES: frozenset[str] = frozenset(
    {"lead", "customer_inquiry", "invoice"}
)
R3_REQUIRED_INTEGRATION = "google_mail"
# Compatible with seed script 300s tolerance; JIT allows up to 15 minutes.
INTAKE_CUTOFF_MAX_AGE_SECONDS = 900
SEED_INTAKE_CUTOFF_TOLERANCE_SECONDS = 300


@dataclass
class TenantIntakeReadinessResult:
    tenant_config_exists: bool = False
    tenant_id_match: bool = False
    is_test_tenant: bool = False
    lifecycle_status: str | None = None
    lifecycle_active: bool = False
    intake_enabled: bool = False
    intake_cutoff_present: bool = False
    intake_cutoff_parseable: bool = False
    intake_cutoff_not_future: bool = False
    intake_cutoff_fresh: bool = False
    intake_cutoff_at_redacted: str | None = None
    intake_cutoff_age_seconds: int | None = None
    required_integrations_present: bool = False
    required_job_types_present: bool = False
    tenant_intake_ready: bool = False
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tenant_config_exists": self.tenant_config_exists,
            "tenant_id_match": self.tenant_id_match,
            "is_test_tenant": self.is_test_tenant,
            "lifecycle_status": self.lifecycle_status,
            "lifecycle_active": self.lifecycle_active,
            "intake_enabled": self.intake_enabled,
            "intake_cutoff_present": self.intake_cutoff_present,
            "intake_cutoff_parseable": self.intake_cutoff_parseable,
            "intake_cutoff_not_future": self.intake_cutoff_not_future,
            "intake_cutoff_fresh": self.intake_cutoff_fresh,
            "intake_cutoff_at_redacted": self.intake_cutoff_at_redacted,
            "intake_cutoff_age_seconds": self.intake_cutoff_age_seconds,
            "required_integrations_present": self.required_integrations_present,
            "required_job_types_present": self.required_job_types_present,
            "tenant_intake_ready": self.tenant_intake_ready,
            "tenant_intake_blockers": list(self.blockers),
            "ready": self.tenant_intake_ready,
        }


def _redact_cutoff_iso(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if len(text) <= 12:
        return text
    return f"{text[:10]}…{text[-6:]}"


def run_r3_tenant_intake_readiness(
    db: Session,
    *,
    tenant_id: str,
    manifest: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> TenantIntakeReadinessResult:
    """Read-only tenant intake gate for R3 frozen live canary."""
    del manifest  # reserved for future manifest-scoped job-type checks
    now = now or datetime.now(timezone.utc)
    result = TenantIntakeReadinessResult()
    blockers: list[str] = []

    if tenant_id != LIVE_EVAL_TENANT_ID:
        blockers.append(f"tenant_id {tenant_id!r} != {LIVE_EVAL_TENANT_ID}")
        result.tenant_id_match = False
        result.blockers = blockers
        return result
    result.tenant_id_match = True

    row = db.get(TenantConfigRecord, tenant_id)
    if row is None:
        blockers.append("tenant_config missing")
        result.blockers = blockers
        return result

    result.tenant_config_exists = True
    result.is_test_tenant = bool(row.is_test_tenant)
    if not result.is_test_tenant:
        blockers.append("is_test_tenant is false")

    result.lifecycle_status = str(row.lifecycle_status or "")
    result.lifecycle_active = result.lifecycle_status == "active"
    if not result.lifecycle_active:
        blockers.append(f"lifecycle_status {result.lifecycle_status!r} != active")

    settings = dict(row.settings or {})
    intake = dict(settings.get("intake") or {})
    result.intake_enabled = bool(intake.get("enabled"))
    if not result.intake_enabled:
        blockers.append("intake.enabled is not true")

    cutoff_raw = intake.get("intake_cutoff_at") or intake.get("activation_cutoff_at")
    if cutoff_raw:
        result.intake_cutoff_present = True
        result.intake_cutoff_at_redacted = _redact_cutoff_iso(str(cutoff_raw))

    cutoff_dt = parse_cutoff_at(str(cutoff_raw) if cutoff_raw else None)
    if result.intake_cutoff_present and cutoff_dt is None:
        blockers.append("intake_cutoff_at is not parseable")
    elif cutoff_dt is not None:
        result.intake_cutoff_parseable = True
        age_seconds = int((now - cutoff_dt).total_seconds())
        result.intake_cutoff_age_seconds = age_seconds
        if cutoff_dt > now:
            blockers.append("intake_cutoff_at is in the future")
        else:
            result.intake_cutoff_not_future = True
        if age_seconds > INTAKE_CUTOFF_MAX_AGE_SECONDS:
            blockers.append(
                f"intake_cutoff_at stale (age {age_seconds}s > {INTAKE_CUTOFF_MAX_AGE_SECONDS}s)"
            )
        else:
            result.intake_cutoff_fresh = True
    elif not result.intake_cutoff_present:
        blockers.append("intake_cutoff_at missing")

    integrations = set(row.allowed_integrations or [])
    result.required_integrations_present = R3_REQUIRED_INTEGRATION in integrations
    if not result.required_integrations_present:
        blockers.append(f"{R3_REQUIRED_INTEGRATION} not in allowed_integrations")

    enabled_job_types = set(row.enabled_job_types or [])
    missing_job_types = sorted(R3_REQUIRED_JOB_TYPES - enabled_job_types)
    result.required_job_types_present = not missing_job_types
    if missing_job_types:
        blockers.append(f"missing enabled_job_types: {', '.join(missing_job_types)}")

    result.blockers = list(dict.fromkeys(blockers))
    result.tenant_intake_ready = not blockers
    return result
