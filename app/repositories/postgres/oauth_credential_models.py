from sqlalchemy import Column, String, DateTime, JSON, Text
from sqlalchemy.sql import func

from app.repositories.postgres.database import Base


class OAuthCredentialRecord(Base):
    __tablename__ = "oauth_credentials"

    tenant_id = Column(String, primary_key=True)
    provider = Column(String, primary_key=True)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(String, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    connected_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
