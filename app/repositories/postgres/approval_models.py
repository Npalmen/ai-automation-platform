from datetime import datetime, timezone

from sqlalchemy import DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.postgres.database import Base


class ApprovalRequestRecord(Base):
    __tablename__ = "approval_requests"

    approval_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    job_type: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    state: Mapped[str] = mapped_column(String, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String, nullable=False, index=True)

    title: Mapped[str | None] = mapped_column(String, nullable=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)

    requested_by: Mapped[str | None] = mapped_column(String, nullable=True)
    requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    resolved_by: Mapped[str | None] = mapped_column(String, nullable=True)
    resolved_via: Mapped[str | None] = mapped_column(String, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String, nullable=True)

    next_on_approve: Mapped[str | None] = mapped_column(String, nullable=True)
    next_on_reject: Mapped[str | None] = mapped_column(String, nullable=True)

    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    delivery_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )