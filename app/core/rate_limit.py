"""
In-memory rate limiting (Kapitel 11).

Limitation: per-process only; not shared across multiple app instances.
Document in runbooks for multi-instance deployments.
"""

from __future__ import annotations

import time
from threading import Lock

_buckets: dict[str, list[float]] = {}
_lock = Lock()


def check_rate_limit(key: str, *, max_calls: int, window_seconds: float) -> tuple[bool, int]:
    """
    Return (allowed, retry_after_seconds).
    retry_after_seconds is 0 when allowed.
    """
    if max_calls <= 0 or window_seconds <= 0:
        return True, 0

    now = time.monotonic()
    cutoff = now - window_seconds

    with _lock:
        timestamps = _buckets.get(key, [])
        timestamps = [t for t in timestamps if t > cutoff]
        if len(timestamps) >= max_calls:
            oldest = min(timestamps)
            retry_after = max(1, int(window_seconds - (now - oldest)) + 1)
            _buckets[key] = timestamps
            return False, retry_after
        timestamps.append(now)
        _buckets[key] = timestamps
        return True, 0


def reset_rate_limits_for_tests() -> None:
    """Test helper — clear all buckets."""
    with _lock:
        _buckets.clear()
