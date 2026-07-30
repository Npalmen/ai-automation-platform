"""Persistent campaign state for profile semi-auto runner."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.evaluation.profile_testbot.campaign.semi_auto_state import SemiAutoCampaignState


def campaign_state_path(campaign_id: str, *, root: str | Path | None = None) -> Path:
    base = Path(root or os.path.join("storage", "live_eval", "profile_testbot_campaigns"))
    return base / f"{campaign_id}.json"


def load_campaign_state(
    campaign_id: str,
    *,
    root: str | Path | None = None,
) -> SemiAutoCampaignState | None:
    path = campaign_state_path(campaign_id, root=root)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return SemiAutoCampaignState.from_dict(payload)


def save_campaign_state(
    state: SemiAutoCampaignState,
    *,
    root: str | Path | None = None,
) -> Path:
    path = campaign_state_path(state.campaign_id, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = state.to_dict()
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=".campaign.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def delete_campaign_state(campaign_id: str, *, root: str | Path | None = None) -> bool:
    path = campaign_state_path(campaign_id, root=root)
    if not path.is_file():
        return False
    path.unlink()
    return True


def count_campaign_rows(*, root: str | Path | None = None) -> int:
    base = Path(root or os.path.join("storage", "live_eval", "profile_testbot_campaigns"))
    if not base.is_dir():
        return 0
    return sum(1 for item in base.glob("*.json"))
