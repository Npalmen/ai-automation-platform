"""In-process live eval context (app-only; not shared with testbot)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Iterator

from app.evaluation.live.schemas import TrustedLiveEvalSnapshot

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

_current_snapshot: ContextVar[TrustedLiveEvalSnapshot | None] = ContextVar(
    "live_eval_snapshot",
    default=None,
)
_pipeline_db: ContextVar["Session | None"] = ContextVar(
    "live_eval_pipeline_db",
    default=None,
)


def get_current_live_eval_snapshot() -> TrustedLiveEvalSnapshot | None:
    return _current_snapshot.get()


def get_pipeline_db() -> "Session | None":
    return _pipeline_db.get()


def bind_live_eval_snapshot(snapshot: TrustedLiveEvalSnapshot | None):
    return _current_snapshot.set(snapshot)


def reset_live_eval_snapshot(token) -> None:
    _current_snapshot.reset(token)


@contextmanager
def live_eval_context(
    snapshot: TrustedLiveEvalSnapshot | None,
    *,
    db: "Session | None" = None,
) -> Iterator[None]:
    snap_token = bind_live_eval_snapshot(snapshot)
    db_token = _pipeline_db.set(db)
    try:
        yield
    finally:
        reset_live_eval_snapshot(snap_token)
        _pipeline_db.reset(db_token)


def snapshot_from_job_input(input_data: dict | None) -> TrustedLiveEvalSnapshot | None:
    if not isinstance(input_data, dict):
        return None
    raw = input_data.get("live_eval")
    if not isinstance(raw, dict) or not raw.get("trusted"):
        return None
    return TrustedLiveEvalSnapshot.model_validate(raw)
