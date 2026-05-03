from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.postgres.database import Base


class TenantApiKeyRecord(Base):
    """Stores hashed tenant API keys.

    The raw key is generated once and returned to the caller.
    Only the SHA-256 hex digest is persisted — the raw key is never stored.

    key_hint: last 4 chars of the raw key, for display/identification only.
    """

    __tablename__ = "tenant_api_keys"

    key_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    key_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    key_hint: Mapped[str] = mapped_column(String(8), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
