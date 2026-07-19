"""Signed single-use OAuth state for tenant integration connect (non-onboarding)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.integrations.oauth_state_models import IntegrationOAuthStateRecord

OAUTH_STATE_TTL_MINUTES = 15
CUSTOMER_DETAIL_REDIRECT_PREFIX = "/ops/customers/"


class OAuthStateError(Exception):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _state_secret(settings: Settings) -> str:
    return settings.SESSION_SECRET_KEY or settings.ADMIN_API_KEY or settings.APP_NAME or "krowolf-oauth"


def _compute_state_hash(
    *,
    state_id: str,
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


def validate_redirect_target(redirect_target: str, tenant_id: str) -> str:
    target = redirect_target.strip()
    expected = f"{CUSTOMER_DETAIL_REDIRECT_PREFIX}{tenant_id}"
    onboarding = f"{expected}/onboarding"
    if target not in {expected, onboarding} and not target.startswith(f"{expected}?"):
        raise OAuthStateError("Redirect target is not allowlisted.", code="oauth_redirect_invalid")
    return target


def create_integration_oauth_state(
    db: Session,
    *,
    tenant_id: str,
    operator_id: str,
    provider: str,
    redirect_target: str,
    settings: Settings,
) -> tuple[str, IntegrationOAuthStateRecord]:
    redirect = validate_redirect_target(redirect_target, tenant_id)
    state_id = secrets.token_urlsafe(32)
    expires_at = _utcnow() + timedelta(minutes=OAUTH_STATE_TTL_MINUTES)
    state_hash = _compute_state_hash(
        state_id=state_id,
        tenant_id=tenant_id,
        operator_id=operator_id,
        provider=provider,
        redirect_target=redirect,
        expires_at=expires_at,
        settings=settings,
    )
    record = IntegrationOAuthStateRecord(
        state_id=state_id,
        state_hash=state_hash,
        tenant_id=tenant_id,
        operator_id=operator_id,
        provider=provider,
        redirect_target=redirect,
        expires_at=expires_at,
        created_at=_utcnow(),
    )
    db.add(record)
    db.flush()
    return state_id, record


def consume_integration_oauth_state(
    db: Session,
    *,
    state_id: str,
    provider: str,
    settings: Settings,
) -> IntegrationOAuthStateRecord:
    record = (
        db.query(IntegrationOAuthStateRecord)
        .filter_by(state_id=state_id, provider=provider)
        .with_for_update()
        .first()
    )
    if record is None:
        raise OAuthStateError("Invalid OAuth state.", code="oauth_state_invalid")
    if record.consumed_at is not None:
        raise OAuthStateError("OAuth state already consumed.", code="oauth_state_replay")
    if _as_utc(record.expires_at) < _utcnow():
        raise OAuthStateError("OAuth state expired.", code="oauth_state_expired")

    expected_hash = _compute_state_hash(
        state_id=record.state_id,
        tenant_id=record.tenant_id,
        operator_id=record.operator_id,
        provider=record.provider,
        redirect_target=record.redirect_target,
        expires_at=_as_utc(record.expires_at),
        settings=settings,
    )
    if not hmac.compare_digest(record.state_hash, expected_hash):
        raise OAuthStateError("OAuth state hash mismatch.", code="oauth_state_invalid")

    record.consumed_at = _utcnow()
    db.flush()
    return record
