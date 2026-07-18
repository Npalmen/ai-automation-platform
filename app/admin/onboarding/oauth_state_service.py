"""Secure OAuth state storage for onboarding integration connect flows."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.admin.onboarding.errors import OnboardingConflictError, OnboardingValidationError
from app.admin.onboarding.models import OPEN_SESSION_STATUSES, OnboardingOAuthStateRecord, OnboardingSessionRecord
from app.core.settings import Settings

OAUTH_STATE_TTL_MINUTES = 15
ALLOWED_REDIRECT_PREFIX = "/ops/customers/"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _state_secret(settings: Settings) -> str:
    key = settings.ADMIN_API_KEY or settings.APP_NAME or "krowolf-onboarding-oauth"
    return key


def _compute_state_hash(
    *,
    state_id: str,
    session_id: str,
    tenant_id: str,
    operator_id: str,
    provider: str,
    redirect_target: str,
    expires_at: datetime,
    settings: Settings,
) -> str:
    payload = "|".join(
        [
            state_id,
            session_id,
            tenant_id,
            operator_id,
            provider,
            redirect_target,
            expires_at.isoformat(),
        ]
    )
    return hmac.new(
        _state_secret(settings).encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _validate_redirect_target(redirect_target: str, tenant_id: str) -> str:
    target = redirect_target.strip()
    expected_suffix = f"/ops/customers/{tenant_id}/onboarding"
    if target != expected_suffix and not target.startswith(f"{expected_suffix}?"):
        raise OnboardingValidationError("Redirect target is not allowlisted for onboarding.")
    return target


def _looks_like_opaque_state(state: str) -> bool:
    try:
        UUID(state)
        return True
    except ValueError:
        return len(state) >= 32 and state.replace("-", "").isalnum()


def create_oauth_state(
    db: Session,
    *,
    session: OnboardingSessionRecord,
    operator_id: str,
    provider: str,
    redirect_target: str,
    settings: Settings,
) -> tuple[str, OnboardingOAuthStateRecord]:
    if session.status not in OPEN_SESSION_STATUSES:
        raise OnboardingValidationError("Onboarding session is not writable.")
    redirect = _validate_redirect_target(redirect_target, session.tenant_id)
    state_id = secrets.token_urlsafe(32)
    expires_at = _utcnow() + timedelta(minutes=OAUTH_STATE_TTL_MINUTES)
    state_hash = _compute_state_hash(
        state_id=state_id,
        session_id=session.id,
        tenant_id=session.tenant_id,
        operator_id=operator_id,
        provider=provider,
        redirect_target=redirect,
        expires_at=expires_at,
        settings=settings,
    )
    record = OnboardingOAuthStateRecord(
        state_id=state_id,
        state_hash=state_hash,
        session_id=session.id,
        tenant_id=session.tenant_id,
        operator_id=operator_id,
        provider=provider,
        redirect_target=redirect,
        expires_at=expires_at,
        created_at=_utcnow(),
    )
    db.add(record)
    db.flush()
    return state_id, record


def consume_oauth_state(
    db: Session,
    *,
    state_id: str,
    settings: Settings,
) -> OnboardingOAuthStateRecord:
    record = (
        db.query(OnboardingOAuthStateRecord)
        .filter(OnboardingOAuthStateRecord.state_id == state_id)
        .with_for_update()
        .first()
    )
    if record is None:
        raise OnboardingConflictError("Invalid OAuth state.", code="oauth_state_invalid")
    if record.consumed_at is not None:
        raise OnboardingConflictError("OAuth state already consumed.", code="oauth_state_replay")
    if _as_utc(record.expires_at) < _utcnow():
        raise OnboardingConflictError("OAuth state expired.", code="oauth_state_expired")

    expected_hash = _compute_state_hash(
        state_id=record.state_id,
        session_id=record.session_id,
        tenant_id=record.tenant_id,
        operator_id=record.operator_id,
        provider=record.provider,
        redirect_target=record.redirect_target,
        expires_at=_as_utc(record.expires_at),
        settings=settings,
    )
    if not hmac.compare_digest(record.state_hash, expected_hash):
        raise OnboardingConflictError("OAuth state hash mismatch.", code="oauth_state_invalid")

    session = (
        db.query(OnboardingSessionRecord)
        .filter(OnboardingSessionRecord.id == record.session_id)
        .first()
    )
    if session is None or session.status not in OPEN_SESSION_STATUSES:
        raise OnboardingConflictError(
            "Onboarding session is no longer active.",
            code="oauth_session_stale",
        )

    record.consumed_at = _utcnow()
    db.flush()
    return record


def is_onboarding_oauth_state(state: str) -> bool:
    return _looks_like_opaque_state(state)
