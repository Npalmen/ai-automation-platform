from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.postgres.database import Base


class TenantConfigRecord(Base):
    __tablename__ = "tenant_configs"

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    slug: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="onboarding")
    config_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lifecycle_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lifecycle_updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_test_tenant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_config_updated_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    readiness_config_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    readiness_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled_job_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    allowed_integrations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    auto_actions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
