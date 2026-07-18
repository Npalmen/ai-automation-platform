"""Collision-resistant tenant ID generation."""

from __future__ import annotations

import re
import secrets
import time

from sqlalchemy.orm import Session

from app.repositories.postgres.tenant_config_models import TenantConfigRecord

TENANT_ID_MAX_LEN = 32
_SLUG_RE = re.compile(r"^[a-z0-9-]{2,48}$")


def normalize_slug(raw: str) -> str:
    slug = raw.strip().lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    if not _SLUG_RE.match(slug):
        raise ValueError("slug must be 2–48 lowercase alphanumeric chars or hyphens.")
    return slug


def slug_exists(db: Session, slug: str, *, exclude_tenant_id: str | None = None) -> bool:
    q = db.query(TenantConfigRecord).filter(TenantConfigRecord.slug == slug)
    if exclude_tenant_id:
        q = q.filter(TenantConfigRecord.tenant_id != exclude_tenant_id)
    return q.first() is not None


def generate_tenant_id(db: Session, *, max_attempts: int = 12) -> str:
    for _ in range(max_attempts):
        bucket = format(int(time.time()) & 0xFFFFFF, "x").upper()
        suffix = secrets.token_hex(3).upper()
        tenant_id = f"T_{bucket}_{suffix}"
        if len(tenant_id) > TENANT_ID_MAX_LEN:
            tenant_id = tenant_id[:TENANT_ID_MAX_LEN]
        exists = (
            db.query(TenantConfigRecord)
            .filter(TenantConfigRecord.tenant_id == tenant_id)
            .first()
        )
        if not exists:
            return tenant_id
    raise RuntimeError("Could not allocate unique tenant_id.")
