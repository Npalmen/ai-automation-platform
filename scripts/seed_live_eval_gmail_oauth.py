"""Seed Gmail OAuth credentials for live-eval tenant (dry-run by default)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.settings import get_settings
from app.evaluation.live.config import get_live_eval_config
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

PROVIDER = "google_mail"


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
    if apply and len(sorted(config.recipient_emails)) != 1:
        issues.append("exactly one LIVE_EVAL_RECIPIENT_EMAILS entry required for OAuth seed")
    if _is_production_db(settings.DATABASE_URL or ""):
        issues.append("refusing production-like DATABASE_URL")

    refresh = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN", "").strip()
    client_id = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_ID", "").strip() or os.environ.get(
        "GOOGLE_OAUTH_CLIENT_ID", ""
    ).strip()
    client_secret = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_SECRET", "").strip() or os.environ.get(
        "GOOGLE_OAUTH_CLIENT_SECRET", ""
    ).strip()
    if apply and not refresh:
        issues.append("LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN is required for --apply")
    if apply and (not client_id or not client_secret):
        issues.append("recipient Gmail client id/secret required for --apply")

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


def _seed_oauth(tenant_id: str) -> dict:
    refresh = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN", "").strip()
    config = get_live_eval_config()
    recipients = sorted(config.recipient_emails)
    if len(recipients) != 1:
        raise ValueError("exactly one allowlisted LIVE_EVAL_RECIPIENT_EMAILS entry required")
    email = recipients[0].strip().lower()
    scopes = os.environ.get(
        "LIVE_EVAL_RECIPIENT_GMAIL_SCOPES",
        "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.modify",
    ).strip()

    db = SessionLocal()
    try:
        OAuthCredentialRepository.upsert(
            db,
            tenant_id=tenant_id,
            provider=PROVIDER,
            access_token="pending",
            refresh_token=refresh,
            expires_at=datetime.now(timezone.utc),
            scopes=scopes,
            metadata_json={"email": email},
        )
        return {
            "tenant_id": tenant_id,
            "status": "seeded",
            "credential_source": "tenant_oauth",
            "recipient_email_fingerprint": email[:1] + "***@" + email.split("@", 1)[-1],
        }
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed live-eval Gmail OAuth (guarded)")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--apply", action="store_true", help="Mutate database (default is dry-run)")
    args = parser.parse_args(argv)

    issues = _validate_guards(args.tenant_id, apply=args.apply)
    config = get_live_eval_config()

    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "dry_run",
                    "tenant_id": args.tenant_id,
                    "env_fingerprint": config.env_fingerprint,
                    "issues": issues,
                    "would_apply": not issues,
                },
                indent=2,
            )
        )
        return 1 if issues else 0

    if issues:
        print(json.dumps({"mode": "apply", "issues": issues}), file=sys.stderr)
        return 1

    result = _seed_oauth(args.tenant_id)
    print(json.dumps({"mode": "apply", **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
