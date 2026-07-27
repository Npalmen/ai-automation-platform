"""Render live Gmail forensics report as markdown."""

from __future__ import annotations

from app.evaluation.live.forensics.gmail_forensics import LiveGmailForensicsReport


def render_forensics_markdown(report: LiveGmailForensicsReport) -> str:
    lines = [
        "# Semi-auto live OAuth forensics",
        "",
        f"**Source workflow:** `{report.source_workflow_run or 'not_observed'}`",
        f"**Evaluation run ID:** `{report.evaluation_run_id}`",
        f"**Scenario:** `{report.scenario_id}`",
        f"**Job ID:** `{report.job_id or 'not_observed'}`",
        f"**Campaign run ID:** `{report.campaign_run_id or 'not_observed'}`",
        f"**Runtime SHA:** `{report.runtime_sha or 'not_observed'}`",
        "",
        "## Mailbox identities",
        "",
        "| Role | Profile (masked) | Allowlist match | Read scope |",
        "|------|------------------|-----------------|------------|",
        f"| testbot_sender | {report.sender_identity.profile_email_masked} | "
        f"{report.sender_identity.allowlist_match} | {report.sender_identity.read_scope_verified} |",
        f"| app_recipient_mailbox | {report.recipient_identity.profile_email_masked} | "
        f"{report.recipient_identity.allowlist_match} | {report.recipient_identity.read_scope_verified} |",
        "",
        f"**Credential role collision:** `{report.credential_role_collision}`",
        "",
        "## Provider object",
        "",
        f"- provider_message_id: `{report.provider_message_id or 'not_observed'}`",
        f"- provider_sent_status: `{report.provider_sent_status}`",
        f"- adapter_recipient_masked: `{report.adapter_recipient_masked or 'not_observed'}`",
    ]
    if report.provider_object:
        obj = report.provider_object
        lines.extend(
            [
                f"- in_sent: `{obj.in_sent}`",
                f"- from_masked: `{obj.from_masked}`",
                f"- to_masked: `{obj.to_masked}`",
                f"- rfc_message_id: `{obj.rfc_message_id or 'not_observed'}`",
                f"- in_reply_to: `{obj.in_reply_to or 'not_observed'}`",
                f"- labels: `{','.join(obj.labels) or 'not_observed'}`",
            ]
        )
    lines.extend(["", "## Recipient searches", ""])
    for row in report.recipient_searches:
        lines.append(f"- query: `{row.query}` → matches={row.match_count}, placement={row.placement}")
    lines.extend(
        [
            "",
            "## Root cause",
            "",
            f"- classification: **{report.root_cause_classification}**",
            f"- subcodes: `{', '.join(report.root_cause_subcodes) or 'none'}`",
            f"- recipient_verification_status: `{report.recipient_verification_status}`",
        ]
    )
    if report.issues:
        lines.extend(["", "## Issues", ""])
        lines.extend(f"- {issue}" for issue in report.issues)
    return "\n".join(lines) + "\n"
