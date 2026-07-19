"""
Synthetic controlled_dispatch approval fixture for browser approval-first tests.

Uses tenant-isolated IDs prefixed with k12-browser-. No external integration writes.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TEST_TENANT = "T_K12_BROWSER"
APPROVAL_PREFIX = "k12-browser-approval-"
JOB_PREFIX = "k12-browser-job-"


def _engine():
    from sqlalchemy import create_engine

    from app.core.settings import get_settings

    settings = get_settings()
    url = settings.DATABASE_URL.strip()
    if not url:
        raise RuntimeError("DATABASE_URL not configured")
    return create_engine(url)


def setup_synthetic_approval(tenant_id: str | None = None) -> dict[str, str]:
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    tenant = (tenant_id or DEFAULT_TEST_TENANT).strip()
    approval_id = f"{APPROVAL_PREFIX}{uuid.uuid4()}"
    job_id = f"{JOB_PREFIX}{uuid.uuid4()}"
    now = datetime.now(timezone.utc)
    stale_created_at = now - timedelta(hours=25)
    payload = {
        "approval_id": approval_id,
        "state": "pending",
        "channel": "dashboard",
        "title": "K12 browser matrix — controlled dispatch (synthetic)",
        "summary": "Synthetic approval for operator browser verification. No external write.",
        "next_on_approve": "controlled_dispatch",
        "next_on_reject": "manual_review",
        "dispatch_context": {
            "job_id": job_id,
            "tenant_id": tenant,
            "job_type": "lead",
            "system": "monday",
            "target": {
                "board_id": "k12-browser-sandbox",
                "board_name": "K12 Browser Sandbox",
            },
            "dry_run_result": {
                "status": "dry_run",
                "system": "monday",
                "message": "k12 browser synthetic fixture",
            },
        },
        "k12_browser_fixture": True,
    }

    engine = _engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.execute(
            text(
                """
                INSERT INTO tenant_configs (
                    tenant_id, name, slug, status, settings,
                    enabled_job_types, allowed_integrations, created_at, updated_at
                )
                VALUES (
                    :tenant_id, :name, :slug, 'active', :settings,
                    '[]', '[]', :now, :now
                )
                ON CONFLICT (tenant_id) DO UPDATE SET updated_at = :now
                """
            ),
            {
                "tenant_id": tenant,
                "name": "K12 Browser Fixture",
                "slug": tenant.lower(),
                "settings": json.dumps({"scheduler": {"run_mode": "manual"}}),
                "now": now,
            },
        )
        db.execute(
            text(
                """
                INSERT INTO jobs (
                    job_id, tenant_id, job_type, status, input_data, created_at, updated_at
                )
                VALUES (
                    :job_id, :tenant_id, 'lead', 'awaiting_approval', '{}', :now, :now
                )
                ON CONFLICT (job_id) DO UPDATE SET updated_at = :now
                """
            ),
            {"job_id": job_id, "tenant_id": tenant, "now": stale_created_at},
        )
        db.execute(
            text(
                """
                INSERT INTO approval_requests (
                    approval_id, tenant_id, job_id, state, channel, next_on_approve,
                    created_at, updated_at, request_payload
                )
                VALUES (
                    :approval_id, :tenant_id, :job_id, 'pending', 'dashboard',
                    'controlled_dispatch', :now, :now, CAST(:payload AS JSONB)
                )
                ON CONFLICT (approval_id) DO UPDATE
                SET state='pending', updated_at=:now, request_payload=CAST(:payload AS JSONB)
                """
            ),
            {
                "approval_id": approval_id,
                "tenant_id": tenant,
                "job_id": job_id,
                "now": stale_created_at,
                "payload": json.dumps(payload),
            },
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {
        "tenant_id": tenant,
        "approval_id": approval_id,
        "job_id": job_id,
        "needs_help_path": f"/ops/needs-help/approval:{approval_id}",
    }


def cleanup_synthetic_approvals(tenant_id: str | None = None) -> int:
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    tenant = (tenant_id or DEFAULT_TEST_TENANT).strip()
    engine = _engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        result = db.execute(
            text(
                """
                DELETE FROM approval_requests
                WHERE tenant_id = :tenant_id
                  AND approval_id LIKE :prefix
                """
            ),
            {"tenant_id": tenant, "prefix": f"{APPROVAL_PREFIX}%"},
        )
        db.execute(
            text(
                """
                DELETE FROM jobs
                WHERE tenant_id = :tenant_id
                  AND job_id LIKE :prefix
                """
            ),
            {"tenant_id": tenant, "prefix": f"{JOB_PREFIX}%"},
        )
        db.commit()
        return int(result.rowcount or 0)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def fixture_summary(artifacts: dict[str, str]) -> dict[str, Any]:
    return {
        "tenant_id": artifacts.get("tenant_id"),
        "approval_id_prefix": APPROVAL_PREFIX,
        "needs_help_path": artifacts.get("needs_help_path"),
        "external_side_effects": 0,
    }
