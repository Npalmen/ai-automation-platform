"""Readiness checks for full-system testbot isolated environment."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from app.core.settings import get_settings
from app.evaluation.live.campaign.gates import (
    campaign_enabled,
    validate_campaign_budget_config,
    validate_campaign_tenant,
    validate_no_production_resources,
)
from app.evaluation.live.campaign.modes import CAMPAIGN_TYPE_SEND_BUDGET
from app.evaluation.live.campaign.automatic_action_contract import (
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    AUTOMATIC_GMAIL_CANARY_WORKFLOW_CONFIRMATION,
    validate_automatic_campaign_qualification,
)
from app.evaluation.live.campaign.automatic_reply_contract import (
    validate_automatic_reply_contract,
)
from app.evaluation.live.campaign.operator_contract import validate_semi_auto_operator_contract
from app.evaluation.live.campaign.reply_contract import validate_semi_auto_reply_contract
from app.evaluation.live.campaign.registry import (
    get_campaign_scenario,
    list_campaign_scenarios,
    load_campaign_manifest,
)
from app.evaluation.live.campaign.scenario_budget import build_selected_scenario_budget
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.readiness import run_offline_readiness_checks
from app.evaluation.live.safety import validate_config_readiness


@dataclass
class TestbotReadinessReport:
    ready: bool
    origin_main_sha: str
    server_sha: str | None
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    campaign_manifest_version: str = ""
    scenario_count: int = 0
    campaign_types: list[str] = field(default_factory=list)
    gates: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "origin_main_sha": self.origin_main_sha,
            "server_sha": self.server_sha,
            "issues": self.issues,
            "warnings": self.warnings,
            "campaign_manifest_version": self.campaign_manifest_version,
            "scenario_count": self.scenario_count,
            "campaign_types": self.campaign_types,
            "gates": self.gates,
        }


def _git_sha(ref: str = "origin/main") -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", ref],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def build_full_system_testbot_readiness(
    *,
    campaign_type: str = "transport-smoke",
    tenant_id: str = "TENANT_LIVE_EVAL",
    app_base_url: str = "",
    server_sha: str | None = None,
    selected_scenario_ids: tuple[str, ...] | None = None,
) -> TestbotReadinessReport:
    settings = get_settings()
    config = get_live_eval_config()
    issues: list[str] = []
    warnings: list[str] = []
    gates: dict[str, Any] = {}

    origin_sha = _git_sha("origin/main")

    # 2F baseline gates (always required)
    offline = run_offline_readiness_checks(config)
    if not campaign_enabled(config):
        issues.extend(offline.issues)
    else:
        # Campaign mode relaxes 2F.2 single-scenario budget locks
        for issue in offline.issues:
            if "must be 1 for 2F.2" in issue or "must be 0 for 2F.2" in issue:
                continue
            issues.append(issue)

    # 2F.2 locked config (when campaign not enabled)
    if not campaign_enabled(config):
        issues.extend(validate_config_readiness(config))
        warnings.append(
            "FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED is not set; campaign scenarios unavailable"
        )
    else:
        issues.extend(validate_campaign_budget_config(campaign_type=campaign_type, config=config))
        issues.extend(validate_campaign_tenant(tenant_id, config))

    issues.extend(
        validate_no_production_resources(
            database_url=settings.DATABASE_URL or "",
            app_base_url=app_base_url or os.environ.get("LIVE_EVAL_APP_BASE_URL", ""),
            tenant_id=tenant_id,
        )
    )

    manifest = load_campaign_manifest()
    manifest_version = str(manifest.get("manifest_version") or "")
    scenarios = []

    if selected_scenario_ids:
        try:
            selected_budget = build_selected_scenario_budget(
                campaign_type=campaign_type,
                selected_scenario_ids=selected_scenario_ids,
            )
        except Exception as exc:
            issues.append(str(exc))
            selected_budget = None
        if selected_budget is not None:
            scenarios = [
                get_campaign_scenario(scenario_id)
                for scenario_id in selected_budget.selected_scenario_ids
            ]
            gates["selected_scenario_budget"] = selected_budget.to_dict()
            if campaign_type in ("transport-smoke", "observe-core"):
                for scenario in scenarios:
                    if scenario.mode != "observe":
                        issues.append(
                            f"selected scenario {scenario.scenario_id!r} is not observe mode"
                        )
            if campaign_type == AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE:
                for scenario in scenarios:
                    if scenario.mode != "automatic":
                        issues.append(
                            f"selected scenario {scenario.scenario_id!r} is not automatic mode"
                        )
    else:
        scenarios = list_campaign_scenarios(campaign_type=campaign_type)
        expected_budget = CAMPAIGN_TYPE_SEND_BUDGET.get(campaign_type)
        if (
            expected_budget
            and len(scenarios) != expected_budget
            and campaign_type == "transport-smoke"
        ):
            warnings.append(
                f"transport-smoke expects {expected_budget} scenarios, found {len(scenarios)}"
            )

    if not scenarios:
        issues.append(f"no scenarios registered for campaign_type={campaign_type!r}")

    gates["campaign_enabled"] = campaign_enabled(config)
    gates["gmail_enabled"] = config.gmail_enabled
    gates["external_side_effects"] = config.external_side_effects_enabled
    gates["sender_count"] = len(config.sender_emails)
    gates["recipient_count"] = len(config.recipient_emails)
    gates["max_gmail_sends"] = config.max_gmail_sends_per_run
    gates["max_gmail_replies_per_run"] = config.max_gmail_replies_per_run
    gates["intake_label"] = config.intake_label

    if campaign_type == "semi-auto-core":
        contract_issues, contract_matrix = validate_semi_auto_reply_contract(
            campaign_type=campaign_type,
            config=config,
            selected_scenario_ids=selected_scenario_ids,
        )
        issues.extend(contract_issues)
        gates["semi_auto_reply_contract"] = contract_matrix
        operator_issues, operator_warnings, operator_matrix = (
            validate_semi_auto_operator_contract(
                campaign_type=campaign_type,
                config=config,
            )
        )
        issues.extend(operator_issues)
        warnings.extend(operator_warnings)
        gates["semi_auto_operator_contract"] = operator_matrix
        from app.evaluation.live.campaign.tenant_materialization import (
            resolve_live_eval_tenant_context,
        )

        tenant_ctx = resolve_live_eval_tenant_context(tenant_id=tenant_id)
        gates["tenant_materialization"] = {
            "tenant_id": tenant_ctx.tenant_id,
            "internal_notification_email": tenant_ctx.internal_notification_email,
            "internal_handoff_enabled": tenant_ctx.internal_handoff_enabled,
        }

    if campaign_type == AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE:
        issues.extend(
            validate_automatic_campaign_qualification(
                campaign_type=campaign_type,
                scenario_ids=selected_scenario_ids,
                raise_on_failure=False,
            )
        )
        contract_issues, contract_matrix = validate_automatic_reply_contract(
            campaign_type=campaign_type,
            config=config,
            selected_scenario_ids=selected_scenario_ids,
        )
        issues.extend(contract_issues)
        gates["automatic_reply_contract"] = contract_matrix

        from pathlib import Path

        script_root = Path(__file__).resolve().parents[3] / "scripts"
        for script_name in (
            "snapshot_live_eval_tenant_config.py",
            "restore_live_eval_automatic_canary.py",
        ):
            if not (script_root / script_name).is_file():
                issues.append(f"missing required script: {script_name}")

        from app.evaluation.live.campaign.tenant_automation_lifecycle import (
            snapshot_tenant_config,
            verify_automation_not_broadly_enabled,
        )

        try:
            tenant_snapshot = snapshot_tenant_config(tenant_id=tenant_id)
            gates["tenant_automation_snapshot_hash"] = tenant_snapshot.config_hash
            issues.extend(verify_automation_not_broadly_enabled(tenant_snapshot.auto_actions))
        except Exception as exc:
            issues.append(f"tenant automation snapshot failed: {exc}")

        gates["workflow_confirmation"] = AUTOMATIC_GMAIL_CANARY_WORKFLOW_CONFIRMATION

    required_secrets = [
        "LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN",
        "LIVE_EVAL_SENDER_GMAIL_CLIENT_ID",
        "LIVE_EVAL_SENDER_GMAIL_CLIENT_SECRET",
        "ADMIN_API_KEY",
    ]
    missing_secrets = [name for name in required_secrets if not os.environ.get(name, "").strip()]
    if missing_secrets:
        warnings.append(f"secrets not configured locally: {', '.join(missing_secrets)}")

    return TestbotReadinessReport(
        ready=not issues,
        origin_main_sha=origin_sha,
        server_sha=server_sha,
        issues=issues,
        warnings=warnings,
        campaign_manifest_version=manifest_version,
        scenario_count=len(scenarios),
        campaign_types=sorted({s.campaign_type for s in list_campaign_scenarios()}),
        gates=gates,
    )
