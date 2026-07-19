from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord


class OAuthCredentialRepository:

    @staticmethod
    def get(db: Session, tenant_id: str, provider: str) -> OAuthCredentialRecord | None:
        return (
            db.query(OAuthCredentialRecord)
            .filter(
                OAuthCredentialRecord.tenant_id == tenant_id,
                OAuthCredentialRecord.provider == provider,
            )
            .first()
        )

    @staticmethod
    def upsert(
        db: Session,
        tenant_id: str,
        provider: str,
        access_token: str,
        refresh_token: str | None,
        expires_at: datetime | None,
        scopes: str | None,
        metadata_json: dict | None = None,
    ) -> OAuthCredentialRecord:
        record = OAuthCredentialRepository.get(db, tenant_id, provider)
        if record is None:
            record = OAuthCredentialRecord(
                tenant_id=tenant_id,
                provider=provider,
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scopes=scopes,
                metadata_json=metadata_json,
                connected_at=datetime.now(timezone.utc),
            )
            db.add(record)
        else:
            record.access_token = access_token
            if refresh_token is not None:
                record.refresh_token = refresh_token
            if expires_at is not None:
                record.expires_at = expires_at
            if scopes is not None:
                record.scopes = scopes
            if metadata_json is not None:
                record.metadata_json = metadata_json
            record.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def delete(db: Session, tenant_id: str, provider: str) -> bool:
        record = OAuthCredentialRepository.get(db, tenant_id, provider)
        if record is None:
            return False
        db.delete(record)
        db.commit()
        return True
