"""Support Next Action engine.

Deterministic rules — no LLM, no external writes.

Priority order:
1. critical urgency / emergency → escalate
2. requires_human + angry sentiment → escalate
3. completeness < 0.7 → ask_for_info
4. common_issue match + low risk + complete → suggest_solution
5. score >= 70 + complete + tenant auto_actions → ready_to_dispatch (create_task)
6. score >= 40 → manual_review
7. default → manual_review

No external dispatch in v1 — ready_to_dispatch only signals intent.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.support.models import (
    SupportAnalysis,
    SupportMissingInfoResult,
    SupportPriority,
    SupportNextAction,
)

if TYPE_CHECKING:
    from app.support.tenant_context import TenantSupportContext


def decide_support_next_action(
    analysis: SupportAnalysis,
    missing_info: SupportMissingInfoResult,
    priority: SupportPriority,
    tenant_auto_actions: dict | None = None,
    tenant_ctx: "TenantSupportContext | None" = None,
) -> SupportNextAction:
    """Determine the next action for a support ticket. Never triggers external writes."""
    ctx_used = bool(tenant_ctx and tenant_ctx.context_available)
    ctx_sources = list(tenant_ctx.sources_used) if ctx_used else []

    # 1. Critical / emergency → always escalate
    if analysis.urgency == "critical" or analysis.ticket_type == "emergency":
        return SupportNextAction(
            action="escalate",
            requires_approval=True,
            reason="Kritisk urgency eller emergency-ticket — kräver omedelbar mänsklig hantering.",
            tenant_context_used=ctx_used,
            context_sources=ctx_sources,
        )

    # 2. Angry + requires_human → escalate
    if analysis.requires_human and analysis.customer_sentiment == "angry":
        return SupportNextAction(
            action="escalate",
            requires_approval=True,
            reason="Arg kund och mänsklig hantering krävs.",
            tenant_context_used=ctx_used,
            context_sources=ctx_sources,
        )

    # 3. Incomplete → ask for info
    if missing_info.completeness_score < 0.7:
        return SupportNextAction(
            action="ask_for_info",
            requires_approval=False,
            reason=f"Kompletthet {missing_info.completeness_score:.0%} — saknad information behövs.",
            tenant_context_used=ctx_used,
            context_sources=ctx_sources,
        )

    # 4. Human-required, complete high-risk cases become approval-gated tasks.
    if analysis.requires_human or analysis.urgency == "high":
        return SupportNextAction(
            action="create_task",
            requires_approval=True,
            reason="Ärendet är tillräckligt komplett men kräver mänsklig uppföljning.",
            tenant_context_used=ctx_used,
            context_sources=ctx_sources,
        )

    # 5. Common issue match + low risk + complete → suggest solution
    if tenant_ctx and tenant_ctx.context_available and not analysis.requires_human:
        text = ""  # can't access input_data here — signal via priority score
        # Use priority score < 40 as proxy for low risk
        if priority.score < 40 and analysis.urgency in ("low", "medium"):
            # Check via context if any common issue is configured
            if tenant_ctx.common_issues:
                return SupportNextAction(
                    action="suggest_solution",
                    requires_approval=False,
                    reason="Vanligt ärende med känd lösning — föreslår lösning.",
                    tenant_context_used=ctx_used,
                    context_sources=ctx_sources,
                )

    # 6. High priority score + tenant auto_actions → ready_to_dispatch (create_task only)
    auto = (tenant_auto_actions or {}).get("support", False)
    if priority.score >= 70 and (auto is True or auto == "auto"):
        return SupportNextAction(
            action="ready_to_dispatch",
            requires_approval=False,
            reason=f"Score {priority.score} + auto-åtgärd aktiverad — redo för uppgiftsskapande.",
            tenant_context_used=ctx_used,
            context_sources=ctx_sources,
        )

    # 7. Complete + high score → create_task (pending approval)
    if priority.score >= 40 and missing_info.completeness_score >= 0.7:
        return SupportNextAction(
            action="create_task",
            requires_approval=True,
            reason=f"Score {priority.score} — skapar uppgift med godkännande.",
            tenant_context_used=ctx_used,
            context_sources=ctx_sources,
        )

    # 8. Default → manual review
    return SupportNextAction(
        action="manual_review",
        requires_approval=False,
        reason="Ärendet kräver manuell granskning.",
        tenant_context_used=ctx_used,
        context_sources=ctx_sources,
    )
