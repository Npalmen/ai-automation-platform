"""Customer workspace password policy — single-factor, min 15 code points."""

from __future__ import annotations

MIN_PASSWORD_LENGTH = 15
MAX_PASSWORD_LENGTH = 64

# Local blocklist only — no external breach API in connected-b.
_BLOCKED_PASSWORDS_LOWER: frozenset[str] = frozenset(
    {
        "passwordpassword",
        "password1234567",
        "qwertyuiopasdfg",
        "letmeinletmein1",
        "welcomewelcome1",
        "changeme1234567",
        "adminadminadmin",
        "customerviewer1",
        "workspaceviewer1",
        "correcthorsebatt",
    }
)


class CustomerPasswordPolicyError(ValueError):
    """Raised when a password fails customer workspace policy."""


def validate_customer_password(password: str) -> None:
    """Validate password for provisioning and reset. Password is never normalized."""
    if not isinstance(password, str):
        raise CustomerPasswordPolicyError("Ogiltigt lösenord.")
    length = len(password)
    if length < MIN_PASSWORD_LENGTH:
        raise CustomerPasswordPolicyError(
            f"Lösenordet måste vara minst {MIN_PASSWORD_LENGTH} tecken."
        )
    if length > MAX_PASSWORD_LENGTH:
        raise CustomerPasswordPolicyError(
            f"Lösenordet får vara högst {MAX_PASSWORD_LENGTH} tecken."
        )
    if password.lower() in _BLOCKED_PASSWORDS_LOWER:
        raise CustomerPasswordPolicyError("Lösenordet är för vanligt. Välj ett starkare lösenord.")
