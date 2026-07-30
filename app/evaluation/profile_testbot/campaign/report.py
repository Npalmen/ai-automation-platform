"""Campaign report writer for profile-driven testbot."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_profile_testbot_report(
    *,
    phase: str,
    run_id: str,
    payload: dict[str, Any],
    output_dir: str = "storage/status",
) -> Path:
    path = Path(output_dir) / f"profile-testbot-{phase}-{run_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Profile testbot {phase} report",
        "",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"- run_id: `{run_id}`",
        f"- overall_status: **{payload.get('overall_status', 'unknown')}**",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(payload, indent=2, ensure_ascii=False),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
