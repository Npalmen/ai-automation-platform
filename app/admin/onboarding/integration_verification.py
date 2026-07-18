"""Server-controlled integration verification records (not stored in drafts)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.admin.onboarding.models import OnboardingIntegrationVerificationRecord


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IntegrationVerificationStore:
  @staticmethod
  def get(db: Session, session_id: str, integration_key: str) -> OnboardingIntegrationVerificationRecord | None:
      return (
          db.query(OnboardingIntegrationVerificationRecord)
          .filter(
              OnboardingIntegrationVerificationRecord.session_id == session_id,
              OnboardingIntegrationVerificationRecord.integration_key == integration_key,
          )
          .first()
      )

  @staticmethod
  def list_for_session(db: Session, session_id: str) -> list[OnboardingIntegrationVerificationRecord]:
      return (
          db.query(OnboardingIntegrationVerificationRecord)
          .filter(OnboardingIntegrationVerificationRecord.session_id == session_id)
          .all()
      )

  @staticmethod
  def invalidate(
      db: Session,
      *,
      session_id: str,
      integration_key: str,
      source_class: str = "declared",
  ) -> None:
      record = IntegrationVerificationStore.get(db, session_id, integration_key)
      now = _utcnow()
      if record is None:
          db.add(
              OnboardingIntegrationVerificationRecord(
                  session_id=session_id,
                  integration_key=integration_key,
                  verification_status="invalidated",
                  source_class=source_class,
                  verified_at=None,
                  verified_by_operator_id=None,
                  config_fingerprint=None,
                  integration_state_revision_at_verify=None,
                  error_code=None,
                  environment_safe_metadata=None,
                  updated_at=now,
              )
          )
      else:
          record.verification_status = "invalidated"
          record.source_class = source_class
          record.verified_at = None
          record.verified_by_operator_id = None
          record.config_fingerprint = None
          record.integration_state_revision_at_verify = None
          record.error_code = None
          record.environment_safe_metadata = None
          record.updated_at = now
      db.flush()

  @staticmethod
  def invalidate_all(db: Session, session_id: str) -> None:
      for record in IntegrationVerificationStore.list_for_session(db, session_id):
          record.verification_status = "invalidated"
          record.verified_at = None
          record.config_fingerprint = None
          record.updated_at = _utcnow()
      db.flush()

  @staticmethod
  def mark_failed(
      db: Session,
      *,
      session_id: str,
      integration_key: str,
      source_class: str,
      error_code: str,
      metadata: dict | None = None,
  ) -> None:
      now = _utcnow()
      record = IntegrationVerificationStore.get(db, session_id, integration_key)
      if record is None:
          record = OnboardingIntegrationVerificationRecord(
              session_id=session_id,
              integration_key=integration_key,
              verification_status="failed",
              source_class=source_class,
              updated_at=now,
          )
          db.add(record)
      record.verification_status = "failed"
      record.source_class = source_class
      record.verified_at = None
      record.verified_by_operator_id = None
      record.config_fingerprint = None
      record.integration_state_revision_at_verify = None
      record.error_code = error_code
      record.environment_safe_metadata = metadata
      record.updated_at = now
      db.flush()

  @staticmethod
  def mark_verified(
      db: Session,
      *,
      session_id: str,
      integration_key: str,
      source_class: str,
      operator_id: str,
      config_fingerprint: str,
      integration_state_revision: int,
      metadata: dict | None = None,
  ) -> OnboardingIntegrationVerificationRecord:
      """Only verification service may call this."""
      now = _utcnow()
      record = IntegrationVerificationStore.get(db, session_id, integration_key)
      if record is None:
          record = OnboardingIntegrationVerificationRecord(
              session_id=session_id,
              integration_key=integration_key,
              verification_status="verified",
              source_class=source_class,
              updated_at=now,
          )
          db.add(record)
      record.verification_status = "verified"
      record.source_class = source_class
      record.verified_at = now
      record.verified_by_operator_id = operator_id
      record.config_fingerprint = config_fingerprint
      record.integration_state_revision_at_verify = integration_state_revision
      record.error_code = None
      record.environment_safe_metadata = metadata
      record.updated_at = now
      db.flush()
      return record

  @staticmethod
  def is_verified_for_fingerprint(
      record: OnboardingIntegrationVerificationRecord | None,
      *,
      expected_fingerprint: str,
  ) -> bool:
      if record is None:
          return False
      if record.verification_status != "verified":
          return False
      return record.config_fingerprint == expected_fingerprint

  @staticmethod
  def fingerprints_hash(db: Session, session_id: str) -> str:
      import hashlib
      import json

      rows = IntegrationVerificationStore.list_for_session(db, session_id)
      payload = {
          r.integration_key: {
              "status": r.verification_status,
              "fingerprint": r.config_fingerprint,
          }
          for r in sorted(rows, key=lambda x: x.integration_key)
      }
      raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
      return hashlib.sha256(raw.encode("utf-8")).hexdigest()
