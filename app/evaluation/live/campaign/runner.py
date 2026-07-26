"""Observe campaign orchestration for full-system testbot."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Any

from app.evaluation.live.campaign.expected_outcomes import resolve_observe_expected_outcome
from app.evaluation.live.campaign.generator import build_campaign_send_payload
from app.evaluation.live.campaign.gates import (
    campaign_enabled,
    validate_campaign_budget_config,
    validate_no_production_resources,
)
from app.evaluation.live.campaign.modes import CAMPAIGN_TYPE_REPLY_BUDGET
from app.evaluation.live.campaign.registry import list_campaign_scenarios
from app.evaluation.live.campaign.report import CampaignReport, write_campaign_report
from app.evaluation.live.campaign.schemas import CampaignScenario
from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
    resolve_semi_automatic_expected_outcome,
)
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.registry import new_evaluation_run_id
from app.evaluation.live.runner import LiveEvalRunner
from app.evaluation.live.subject_parser import build_subject_with_token


@dataclass
class ScenarioResult:
    scenario_id: str
    scenario_version: str
    evaluation_run_id: str
    correlation_token_redacted: str
    exit_code: int
    status: str
    job_id: str | None = None
    classification: dict[str, Any] = field(default_factory=dict)
    job_status: str | None = None
    approval_status: str | None = None
    violations: list[str] = field(default_factory=list)
    safety_violations: list[str] = field(default_factory=list)


@dataclass
class ObserveCampaignResult:
    campaign_type: str
    overall_status: str
    scenario_results: list[ScenarioResult]
    sends: int = 0
    replies: int = 0
    approval_resolutions: int = 0
    external_writes: int = 0
    safety_violations: list[str] = field(default_factory=list)
    main_sha: str = ""
    server_sha: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "campaign_type": self.campaign_type,
            "overall_status": self.overall_status,
            "sends": self.sends,
            "replies": self.replies,
            "approval_resolutions": self.approval_resolutions,
            "external_writes": self.external_writes,
            "safety_violations": self.safety_violations,
            "main_sha": self.main_sha,
            "server_sha": self.server_sha,
            "scenarios": [
                {
                    "scenario_id": r.scenario_id,
                    "scenario_version": r.scenario_version,
                    "evaluation_run_id": r.evaluation_run_id,
                    "correlation_token_redacted": r.correlation_token_redacted,
                    "exit_code": r.exit_code,
                    "status": r.status,
                    "job_id": r.job_id,
                    "classification": r.classification,
                    "job_status": r.job_status,
                    "approval_status": r.approval_status,
                    "violations": r.violations,
                    "safety_violations": r.safety_violations,
                    "customer_card": "NOT_IMPLEMENTED",
                }
                for r in self.scenario_results
            ],
        }


def _git_sha(ref: str = "HEAD") -> str:
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
        return os.environ.get("BUILD_GIT_SHA", "unknown")


def _redact_token(evaluation_run_id: str, scenario_id: str) -> str:
    return f"KROWOLF-EVAL/{evaluation_run_id[:8]}…/{scenario_id}/1"


def _expected_job_type(scenario: CampaignScenario) -> str | None:
    expected = scenario.expected_classification.get("job_type")
    if expected is not None and str(expected).strip():
        return str(expected).strip()
    return scenario.job_type or None


def run_observe_campaign(
    *,
    campaign_type: str = "transport-smoke",
    tenant_id: str = "TENANT_LIVE_EVAL",
    base_url: str,
    admin_api_key: str,
    report_path: str | None = None,
) -> ObserveCampaignResult:
    if not campaign_enabled():
        raise LiveEvalSafetyError("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED=yes required")

    config = get_live_eval_config()
    budget_issues = validate_campaign_budget_config(campaign_type=campaign_type, config=config)
    if budget_issues:
        raise LiveEvalSafetyError("; ".join(budget_issues))

    prod_issues = validate_no_production_resources(
        app_base_url=base_url,
        tenant_id=tenant_id,
    )
    if prod_issues:
        raise LiveEvalSafetyError("; ".join(prod_issues))

    senders = sorted(config.sender_emails)
    recipients = sorted(config.recipient_emails)
    if len(senders) != 1 or len(recipients) != 1:
        raise LiveEvalSafetyError("exactly one allowlisted sender and recipient required")

    scenarios = list_campaign_scenarios(campaign_type=campaign_type)
    if not scenarios:
        raise LiveEvalSafetyError(f"no scenarios for campaign_type={campaign_type!r}")

    results: list[ScenarioResult] = []
    safety_violations: list[str] = []
    sends = 0

    for scenario in scenarios:
        if scenario.mode != "observe":
            raise LiveEvalSafetyError(f"scenario {scenario.scenario_id!r} is not observe mode")

        run_id = new_evaluation_run_id()
        payload = build_campaign_send_payload(scenario=scenario, evaluation_run_id=run_id)
        expected_outcome = resolve_observe_expected_outcome(scenario)
        runner = LiveEvalRunner(
            base_url=base_url,
            admin_api_key=admin_api_key,
            tenant_id=tenant_id,
            scenario_id=scenario.scenario_id,
            expected_sender=senders[0],
            expected_recipient=recipients[0],
            evaluation_run_id=run_id,
            message_body=payload["body"],
            base_subject=scenario.email.subject,
            expected_job_type=_expected_job_type(scenario),
            use_observe_assertions=True,
            observe_expected_outcome=expected_outcome,
        )
        exit_code = runner.run()
        sends += 1 if exit_code == 0 else 0

        observation: dict[str, Any] = {}
        try:
            observation = runner.observer.get_observation(run_id)
        except Exception:
            observation = {}

        job = observation.get("job") or {}
        violations = []
        if exit_code != 0:
            violations.append(f"runner exit_code={exit_code}")

        result = ScenarioResult(
            scenario_id=scenario.scenario_id,
            scenario_version=scenario.scenario_version,
            evaluation_run_id=run_id,
            correlation_token_redacted=_redact_token(run_id, scenario.scenario_id),
            exit_code=exit_code,
            status="passed" if exit_code == 0 else "failed",
            job_id=job.get("job_id"),
            classification=dict(job.get("classification") or {}),
            job_status=job.get("job_status"),
            approval_status="pending" if job.get("has_pending_approvals") else "none",
            violations=violations,
        )
        results.append(result)

    passed = sum(1 for r in results if r.status == "passed")
    overall = "passed" if passed == len(scenarios) and len(scenarios) == 5 else "failed"
    if sends != len(scenarios):
        safety_violations.append(f"send count mismatch: {sends} != {len(scenarios)}")

    campaign_result = ObserveCampaignResult(
        campaign_type=campaign_type,
        overall_status=overall,
        scenario_results=results,
        sends=len(scenarios),
        replies=0,
        approval_resolutions=0,
        external_writes=0,
        safety_violations=safety_violations,
        main_sha=_git_sha("HEAD"),
        server_sha=os.environ.get("BUILD_GIT_SHA"),
    )

    if report_path:
        report = CampaignReport(
            campaign_type=campaign_type,
            mode="observe",
            main_sha=campaign_result.main_sha,
            server_sha=campaign_result.server_sha,
            scenario_versions=[s.scenario_version for s in scenarios],
            sends=campaign_result.sends,
            replies=0,
            approvals=0,
            overall_status=overall,
        )
        write_campaign_report(report_path, report)

    return campaign_result


def run_semi_automatic_campaign(
    *,
    campaign_type: str = "semi-auto-core",
    tenant_id: str = "TENANT_LIVE_EVAL",
    base_url: str,
    admin_api_key: str,
    report_path: str | None = None,
) -> ObserveCampaignResult:
    if not campaign_enabled():
        raise LiveEvalSafetyError("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED=yes required")

    config = get_live_eval_config()
    budget_issues = validate_campaign_budget_config(campaign_type=campaign_type, config=config)
    if budget_issues:
        raise LiveEvalSafetyError("; ".join(budget_issues))

    reply_ceiling = CAMPAIGN_TYPE_REPLY_BUDGET.get(campaign_type, 0)
    if reply_ceiling and config.max_gmail_replies_per_run < 1:
        raise LiveEvalSafetyError(
            "LIVE_EVAL_MAX_GMAIL_REPLIES must be >= 1 for semi-automatic campaigns"
        )

    prod_issues = validate_no_production_resources(
        app_base_url=base_url,
        tenant_id=tenant_id,
    )
    if prod_issues:
        raise LiveEvalSafetyError("; ".join(prod_issues))

    senders = sorted(config.sender_emails)
    recipients = sorted(config.recipient_emails)
    if len(senders) != 1 or len(recipients) != 1:
        raise LiveEvalSafetyError("exactly one allowlisted sender and recipient required")

    scenarios = list_campaign_scenarios(campaign_type=campaign_type)
    if not scenarios:
        raise LiveEvalSafetyError(f"no scenarios for campaign_type={campaign_type!r}")

    results: list[ScenarioResult] = []
    safety_violations: list[str] = []
    sends = 0
    replies = 0
    approval_resolutions = 0
    reply_budget_remaining = reply_ceiling

    for scenario in scenarios:
        if scenario.mode != "semi_automatic":
            raise LiveEvalSafetyError(
                f"scenario {scenario.scenario_id!r} is not semi_automatic mode"
            )

        run_id = new_evaluation_run_id()
        payload = build_campaign_send_payload(scenario=scenario, evaluation_run_id=run_id)
        expected_outcome = resolve_semi_automatic_expected_outcome(scenario)
        operator_reply_budget = reply_budget_remaining
        if expected_outcome.expected_reply:
            if reply_budget_remaining < 1:
                raise LiveEvalSafetyError(
                    f"reply budget exhausted before scenario {scenario.scenario_id!r}"
                )
            reply_budget_remaining -= 1

        runner = LiveEvalRunner(
            base_url=base_url,
            admin_api_key=admin_api_key,
            tenant_id=tenant_id,
            scenario_id=scenario.scenario_id,
            expected_sender=senders[0],
            expected_recipient=recipients[0],
            evaluation_run_id=run_id,
            message_body=payload["body"],
            base_subject=scenario.email.subject,
            expected_job_type=_expected_job_type(scenario),
            use_semi_automatic_assertions=True,
            semi_automatic_expected_outcome=expected_outcome,
            reply_budget_remaining=operator_reply_budget,
            campaign_scenario=scenario,
        )
        exit_code = runner.run()
        sends += 1 if exit_code == 0 else 0

        observation: dict[str, Any] = {}
        try:
            observation = runner.observer.get_observation(run_id)
        except Exception:
            observation = {}

        job = observation.get("job") or {}
        violations = []
        if exit_code != 0:
            violations.append(f"runner exit_code={exit_code}")

        if expected_outcome.expect_approval_resolution and exit_code == 0:
            approval_resolutions += 1
        if expected_outcome.expected_reply and exit_code == 0:
            replies += 1

        result = ScenarioResult(
            scenario_id=scenario.scenario_id,
            scenario_version=scenario.scenario_version,
            evaluation_run_id=run_id,
            correlation_token_redacted=_redact_token(run_id, scenario.scenario_id),
            exit_code=exit_code,
            status="passed" if exit_code == 0 else "failed",
            job_id=job.get("job_id"),
            classification=dict(job.get("classification") or {}),
            job_status=job.get("job_status"),
            approval_status="resolved" if expected_outcome.expect_approval_resolution else "none",
            violations=violations,
        )
        results.append(result)

    passed = sum(1 for r in results if r.status == "passed")
    expected_count = len(scenarios)
    overall = "passed" if passed == expected_count else "failed"
    if sends != expected_count:
        safety_violations.append(f"send count mismatch: {sends} != {expected_count}")
    if replies > reply_ceiling:
        safety_violations.append(f"reply budget exceeded: {replies} > {reply_ceiling}")

    campaign_result = ObserveCampaignResult(
        campaign_type=campaign_type,
        overall_status=overall if not safety_violations else "failed",
        scenario_results=results,
        sends=len(scenarios),
        replies=replies,
        approval_resolutions=approval_resolutions,
        external_writes=0,
        safety_violations=safety_violations,
        main_sha=_git_sha("HEAD"),
        server_sha=os.environ.get("BUILD_GIT_SHA"),
    )

    if report_path:
        report = CampaignReport(
            campaign_type=campaign_type,
            mode="semi_automatic",
            main_sha=campaign_result.main_sha,
            server_sha=campaign_result.server_sha,
            scenario_versions=[s.scenario_version for s in scenarios],
            sends=campaign_result.sends,
            replies=campaign_result.replies,
            approvals=campaign_result.approval_resolutions,
            overall_status=campaign_result.overall_status,
        )
        write_campaign_report(report_path, report)

    return campaign_result
