#!/usr/bin/env python3
"""Secret-free OAuth state report for one tenant."""
from __future__ import annotations

import json
import sys

from app.integrations.oauth_state_models import IntegrationOAuthStateRecord
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository

TENANT = sys.argv[1] if len(sys.argv) > 1 else "T_NIKLAS_DEMO_001"
PROVIDER = "google_mail"


def main() -> int:
    db = SessionLocal()
    try:
        rows = (
            db.query(IntegrationOAuthStateRecord)
            .filter_by(tenant_id=TENANT, provider=PROVIDER)
            .order_by(IntegrationOAuthStateRecord.created_at.desc())
            .limit(3)
            .all()
        )
        states = []
        for r in rows:
            states.append(
                {
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "expires_at": r.expires_at.isoformat() if r.expires_at else None,
                    "consumed": r.consumed_at is not None,
                    "consumed_at": r.consumed_at.isoformat() if r.consumed_at else None,
                    "tenant_id_match": r.tenant_id == TENANT,
                    "operator_set": bool(r.operator_id),
                    "redirect_path": r.redirect_target,
                    "hash_record_exists": bool(r.state_hash),
                    "callback_attempt": None,
                }
            )
        cred = OAuthCredentialRepository.get(db, TENANT, PROVIDER)
        print(
            json.dumps(
                {
                    "tenant": TENANT,
                    "latest_states": states,
                    "oauth_credentials_row": cred is not None,
                },
                indent=2,
            )
        )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
