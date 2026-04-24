from sqlalchemy import String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.repositories.postgres.database import Base


class TenantConfigRecord(Base):
    __tablename__ = "tenant_configs"

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    enabled_job_types: Mapped[list | None] = mapped_column(JSON, nullable=True)
    allowed_integrations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    auto_actions: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    settings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
