"""Campaign report builder for full-system testbot."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_SCHEMA_VERSION = "full-system-testbot.v1"


@dataclass
class CampaignReport:
    schema_version: str = REPORT_SCHEMA_VERSION
    main_sha: str = ""
    server_sha: str | None = None
    campaign_type: str = ""
    mode: str = ""
    scenario_versions: list[str] = field(default_factory=list)
    sends: int = 0
    replies: int = 0
    approvals: int = 0
    auto_actions: int = 0
    writes_per_integration: dict[str, int] = field(default_factory=dict)
    customer_card_outcomes: list[dict[str, Any]] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)
    safety_violations: list[str] = field(default_factory=list)
    cleanup: dict[str, Any] = field(default_factory=dict)
    overall_status: str = "not_started"
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "main_sha": self.main_sha,
            "server_sha": self.server_sha,
            "campaign_type": self.campaign_type,
            "mode": self.mode,
            "scenario_versions": self.scenario_versions,
            "sends": self.sends,
            "replies": self.replies,
            "approvals": self.approvals,
            "auto_actions": self.auto_actions,
            "writes_per_integration": self.writes_per_integration,
            "customer_card_outcomes": self.customer_card_outcomes,
            "failures": self.failures,
            "safety_violations": self.safety_violations,
            "cleanup": self.cleanup,
            "overall_status": self.overall_status,
            "generated_at": self.generated_at,
        }


def write_campaign_report(path: Path, report: CampaignReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
