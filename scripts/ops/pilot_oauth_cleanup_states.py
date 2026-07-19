#!/usr/bin/env python3
"""Delete expired or superseded unconsumed integration OAuth states for one tenant."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from app.integrations.oauth_state_models import IntegrationOAuthStateRecord
from app.repositories.postgres.database import SessionLocal

TENANT = sys.argv[1] if len(sys.argv) > 1 else "T_NIKLAS_DEMO_001"
PROVIDER = "google_mail"


def main() -> int:
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        rows = (
            db.query(IntegrationOAuthStateRecord)
            .filter(
                IntegrationOAuthStateRecord.tenant_id == TENANT,
                IntegrationOAuthStateRecord.provider == PROVIDER,
                IntegrationOAuthStateRecord.consumed_at.is_(None),
            )
            .order_by(IntegrationOAuthStateRecord.created_at.desc())
            .all()
        )

        latest_consumed = (
            db.query(IntegrationOAuthStateRecord)
            .filter(
                IntegrationOAuthStateRecord.tenant_id == TENANT,
                IntegrationOAuthStateRecord.provider == PROVIDER,
                IntegrationOAuthStateRecord.consumed_at.isnot(None),
            )
            .order_by(IntegrationOAuthStateRecord.consumed_at.desc())
            .first()
        )
        cutoff = latest_consumed.created_at if latest_consumed else None

        deleted_expired = 0
        deleted_superseded = 0
        for row in rows:
            exp = row.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp < now:
                db.delete(row)
                deleted_expired += 1
                continue
            if cutoff is not None and row.created_at < cutoff:
                db.delete(row)
                deleted_superseded += 1

        db.commit()
        remaining = (
            db.query(IntegrationOAuthStateRecord)
            .filter(
                IntegrationOAuthStateRecord.tenant_id == TENANT,
                IntegrationOAuthStateRecord.provider == PROVIDER,
                IntegrationOAuthStateRecord.consumed_at.is_(None),
            )
            .count()
        )
        print(
            f"tenant={TENANT} provider={PROVIDER} "
            f"deleted_expired={deleted_expired} deleted_superseded={deleted_superseded} "
            f"remaining_unconsumed={remaining}"
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
