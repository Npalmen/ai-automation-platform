import re


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_REGEX = re.compile(r"^\+?[0-9\s\-()]{6,20}$")


def is_valid_email(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    return bool(EMAIL_REGEX.match(value.strip()))


def is_valid_phone(value: str | None) -> bool:
    if not value or not isinstance(value, str):
        return False
    digits = re.sub(r"\D", "", value)
    if len(digits) < 6 or len(digits) > 15:
        return False
    return bool(PHONE_REGEX.match(value.strip()))


def is_positive_amount(value: float | int | None) -> bool:
    if value is None:
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None