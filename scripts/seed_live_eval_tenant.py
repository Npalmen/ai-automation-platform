"""Seed a dedicated live-eval test tenant (dry-run by default)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.settings import get_settings
from app.evaluation.live.config import get_live_eval_config
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

# Messages delivered shortly after seed must be after this anchor (not a static historical date).
SEED_INTAKE_CUTOFF_TOLERANCE_SECONDS = 300


def seed_intake_cutoff_at() -> str:
    anchor = datetime.now(timezone.utc) - timedelta(seconds=SEED_INTAKE_CUTOFF_TOLERANCE_SECONDS)
    return anchor.replace(microsecond=0).isoformat()


def _is_production_db(database_url: str) -> bool:
    lowered = database_url.lower()
    blocked = ("prod", "production", "live", "rds.amazonaws.com")
    return any(token in lowered for token in blocked)


def _validate_guards(tenant_id: str, *, apply: bool) -> list[str]:
    issues: list[str] = []
    settings = get_settings()
    config = get_live_eval_config()

    if settings.ENV != "test":
        issues.append("ENV must be test")
    if not config.enabled:
        issues.append("LIVE_EVAL_ALLOWED=yes required")
    if apply and not config.seed_allowed:
        issues.append("LIVE_EVAL_SEED_ALLOWED=yes required for --apply")
    if not tenant_id:
        issues.append("explicit --tenant-id is required")
    if config.tenant_ids and tenant_id not in config.tenant_ids:
        issues.append(f"tenant_id {tenant_id!r} is not in LIVE_EVAL_TENANT_IDS")
    if _is_production_db(settings.DATABASE_URL or ""):
        issues.append("refusing production-like DATABASE_URL")

    if not apply:
        return issues

    db = SessionLocal()
    try:
        existing = db.get(TenantConfigRecord, tenant_id)
        if existing is not None and not getattr(existing, "is_test_tenant", False):
            issues.append("tenant already exists and is not marked is_test_tenant")
    finally:
        db.close()

    return issues


def _seed_tenant(tenant_id: str) -> dict:
    db = SessionLocal()
    try:
        row = db.get(TenantConfigRecord, tenant_id)
        if row is None:
            row = TenantConfigRecord(
                tenant_id=tenant_id,
                name=f"Live Eval {tenant_id}",
                slug=tenant_id.lower().replace("_", "-"),
                status="active",
                lifecycle_status="active",
                is_test_tenant=True,
                allowed_integrations=["google_mail"],
                enabled_job_types=["lead", "customer_inquiry", "invoice"],
                settings={
                    "intake": {
                        "enabled": True,
                        "intake_cutoff_at": seed_intake_cutoff_at(),
                    },
                    "live_eval": {"seeded": True},
                },
            )
            db.add(row)
        else:
            row.is_test_tenant = True
            settings = dict(row.settings or {})
            intake = dict(settings.get("intake") or {})
            intake["enabled"] = True
            intake["intake_cutoff_at"] = seed_intake_cutoff_at()
            settings["intake"] = intake
            settings.setdefault("live_eval", {})["seeded"] = True
            row.settings = settings
        db.commit()
        return {"tenant_id": tenant_id, "status": "seeded", "is_test_tenant": True}
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed live-eval test tenant (guarded)")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--apply", action="store_true", help="Mutate database (default is dry-run)")
    args = parser.parse_args(argv)

    issues = _validate_guards(args.tenant_id, apply=args.apply)
    config = get_live_eval_config()

    if not args.apply:
        print(
            {
                "mode": "dry_run",
                "tenant_id": args.tenant_id,
                "env_fingerprint": config.env_fingerprint,
                "issues": issues,
                "would_apply": not issues,
            }
        )
        return 1 if issues else 0

    if issues:
        print({"mode": "apply", "issues": issues}, file=sys.stderr)
        return 1

    result = _seed_tenant(args.tenant_id)
    print({"mode": "apply", **result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
