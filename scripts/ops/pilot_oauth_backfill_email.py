#!/usr/bin/env python3
"""Backfill verified Gmail address into oauth credential metadata (no token output)."""
from __future__ import annotations

import json
import sys

from app.integrations.google.oauth_service import test_connection
from app.integrations.google.oauth_token_resolver import PROVIDER, resolve_google_mail_connection_config
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository

TENANT = sys.argv[1] if len(sys.argv) > 1 else "T_NIKLAS_DEMO_001"


def main() -> int:
    db = SessionLocal()
    try:
        row = OAuthCredentialRepository.get(db, TENANT, PROVIDER)
        if row is None:
            print(json.dumps({"tenant": TENANT, "updated": False, "reason": "no_oauth_row"}))
            return 1

        meta = dict(row.metadata_json or {})
        if meta.get("email"):
            print(
                json.dumps(
                    {
                        "tenant": TENANT,
                        "updated": False,
                        "reason": "email_already_set",
                        "email_domain": str(meta["email"]).split("@")[-1],
                    }
                )
            )
            return 0

        cfg = resolve_google_mail_connection_config(TENANT, db=db)
        if cfg.get("credential_source") != "tenant_oauth":
            print(json.dumps({"tenant": TENANT, "updated": False, "reason": "not_tenant_oauth"}))
            return 1

        profile = test_connection(cfg["access_token"], cfg.get("user_id") or "me")
        email = profile.get("email_address")
        if not email:
            print(json.dumps({"tenant": TENANT, "updated": False, "reason": "profile_empty"}))
            return 1

        meta["email"] = email
        meta.setdefault("connected_via", meta.get("connected_via") or "operator_oauth_callback")
        row.metadata_json = meta
        db.commit()
        print(
            json.dumps(
                {
                    "tenant": TENANT,
                    "updated": True,
                    "email_domain": email.split("@")[-1],
                    "credential_source": "tenant_oauth",
                }
            )
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
