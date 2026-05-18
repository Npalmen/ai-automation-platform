"""
Admin session authentication — username/password login with signed HttpOnly cookie.

This module provides:
  - Password hashing/verification (PBKDF2-HMAC-SHA256, stdlib only)
  - Signed session tokens (HMAC-SHA256, stdlib only, stateless)
  - FastAPI dependencies for login/logout/session validation
  - Backward-compatible: if ADMIN_USERNAME/ADMIN_PASSWORD_HASH not set, falls
    back gracefully; if SESSION_SECRET_KEY not set, sessions are disabled.

Configuration (env vars):
  ADMIN_USERNAME        Admin login username (default: "admin")
  ADMIN_PASSWORD_HASH   PBKDF2-HMAC-SHA256 hash produced by hash_password()
  SESSION_SECRET_KEY    Random 32-byte base64 secret for signing cookies

Generate a password hash (run once, store in .env):
  python -c "from app.core.admin_session import hash_password; print(hash_password('yourpassword'))"

Generate a session secret:
  python -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional

from fastapi import Request, Response

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

SESSION_COOKIE = "admin_session"
SESSION_MAX_AGE = 8 * 3600  # 8 hours


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2-HMAC-SHA256, stdlib)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    """Hash a plaintext password, returning a base64-encoded salt+hash."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return base64.b64encode(salt + dk).decode("ascii")


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time check of password against stored hash. Returns False on any error."""
    try:
        raw = base64.b64decode(hashed.encode("ascii"))
        salt, stored_dk = raw[:16], raw[16:]
        check_dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
        return hmac.compare_digest(check_dk, stored_dk)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Signed session tokens (HMAC-SHA256, stateless)
# ---------------------------------------------------------------------------

def _sign(payload: str, secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session_token(admin_user: str, secret: str) -> str:
    now = int(time.time())
    payload = json.dumps({"sub": admin_user, "iat": now, "exp": now + SESSION_MAX_AGE})
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    sig = _sign(encoded, secret)
    return f"{encoded}.{sig}"


def validate_session_token(token: str, secret: str) -> Optional[str]:
    """Returns admin username if the token is valid and unexpired, else None."""
    try:
        encoded, sig = token.rsplit(".", 1)
    except ValueError:
        return None
    expected = _sign(encoded, secret)
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        # Pad base64 to a multiple of 4 before decoding
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except Exception:
        return None
    if time.time() > payload.get("exp", 0):
        return None
    return payload.get("sub")


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

def set_admin_session_cookie(response: Response, admin_user: str) -> None:
    s = get_settings()
    secret = getattr(s, "SESSION_SECRET_KEY", "").strip()
    if not secret:
        logger.warning("SESSION_SECRET_KEY not configured — admin session cookies are disabled.")
        return
    token = create_session_token(admin_user, secret)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        httponly=True,
        samesite="strict",
        max_age=SESSION_MAX_AGE,
        secure=getattr(s, "ENV", "dev") not in ("dev", "development", "local"),
        path="/",
    )


def clear_admin_session_cookie(response: Response) -> None:
    response.delete_cookie(key=SESSION_COOKIE, httponly=True, samesite="strict", path="/")


def get_admin_from_session(request: Request) -> Optional[str]:
    """Extract and validate admin username from session cookie. Returns None if invalid/absent."""
    s = get_settings()
    secret = getattr(s, "SESSION_SECRET_KEY", "").strip()
    if not secret:
        return None
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        return None
    return validate_session_token(token, secret)


# ---------------------------------------------------------------------------
# Credential validation
# ---------------------------------------------------------------------------

def verify_admin_credentials(username: str, password: str) -> bool:
    """
    Validate username + password against configured admin credentials.

    Returns True only when both username and password match and the
    password hash is configured.  Falls back to False (not to API key
    logic — that is the caller's responsibility).
    """
    s = get_settings()
    configured_user = getattr(s, "ADMIN_USERNAME", "admin").strip() or "admin"
    configured_hash = getattr(s, "ADMIN_PASSWORD_HASH", "").strip()

    if not configured_hash:
        # Not configured — deny all login attempts; admin must set a password.
        return False

    if not hmac.compare_digest(username.lower(), configured_user.lower()):
        return False

    return verify_password(password, configured_hash)


def is_session_auth_configured() -> bool:
    """Return True if session auth is fully configured (hash + secret both set)."""
    s = get_settings()
    return bool(
        getattr(s, "ADMIN_PASSWORD_HASH", "").strip()
        and getattr(s, "SESSION_SECRET_KEY", "").strip()
    )
