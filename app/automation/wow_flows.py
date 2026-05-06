from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


_ACTIVE_STATUSES = {"pending", "processing", "awaiting_approval", "manual_review"}
_SEVERITY_RANK = {"info": 0, "medium": 1, "high": 2, "critical": 3}


def build_automation_case_payload(
    record: Any,
    *,
    action_records: list[Any] | None = None,
    approval_records: list[Any] | None = None,
) -> dict[str, Any]:
    """Build the Phase 6 automation experience payload without side effects."""
    actions = list(action_records or [])
    approvals = list(approval_records or [])
    summary = build_case_summary(record, action_records=actions, approval_records=approvals)
    risks = detect_case_risks(record, action_records=actions, approval_records=approvals)
    flows = build_wow_flows(record, risks=risks)
    return {
        "summary": summary,
        "risks": risks,
        "wow_flows": flows,
    }


def build_case_summary(
    record: Any,
    *,
    action_records: list[Any] | None = None,
    approval_records: list[Any] | None = None,
) -> dict[str, Any]:
    inp = _input_data(record)
    history = _history(record)
    job_type = _record_attr(record, "job_type", "unknown") or "unknown"
    status = _record_attr(record, "status", "unknown") or "unknown"
    subject = inp.get("subject") or inp.get("latest_message_subject") or "Case without subject"
    customer = _customer_name(inp, history)
    workspace = _workspace(inp)
    lead_payload = _processor_payload(history, "lead_analyzer_processor")
    support_payload = _processor_payload(history, "support_analyzer_processor")
    dispatch_payload = _last_processor_payload(history, "action_dispatch_processor")

    action_records = list(action_records or [])
    approval_records = list(approval_records or [])
    action_counts = _action_counts(action_records)
    pending_approvals = _pending_approval_count(approval_records)
    next_step = _next_step_for(
        job_type=job_type,
        status=status,
        workspace=workspace,
        lead_payload=lead_payload,
        support_payload=support_payload,
        pending_approvals=pending_approvals,
    )

    evidence: list[str] = []
    if action_counts["success"]:
        evidence.append(f"{action_counts['success']} successful automation actions recorded")
    if action_counts["failed"]:
        evidence.append(f"{action_counts['failed']} failed action needs review")
    if pending_approvals:
        evidence.append(f"{pending_approvals} approval request(s) pending")
    if _missing_fields(lead_payload, support_payload):
        evidence.append("Missing customer information detected")
    if workspace:
        evidence.append("Operations workspace is available")
    if dispatch_payload.get("ai_reply_suggestions"):
        evidence.append("Reply suggestion is available for approval")
    if not evidence:
        evidence.append("Case data is present but no automation evidence has run yet")

    summary_status = "ready"
    if status in {"failed", "manual_review"} or action_counts["failed"]:
        summary_status = "needs_attention"
    elif pending_approvals or _missing_fields(lead_payload, support_payload):
        summary_status = "watch"

    return {
        "status": summary_status,
        "headline": _headline(job_type, subject, customer),
        "current_state": _current_state(status, workspace),
        "next_step": next_step,
        "confidence": "high" if len(evidence) >= 2 else "medium",
        "evidence": evidence[:6],
        "sources": _summary_sources(
            lead_payload=lead_payload,
            support_payload=support_payload,
            dispatch_payload=dispatch_payload,
            workspace=workspace,
        ),
    }


def detect_case_risks(
    record: Any,
    *,
    action_records: list[Any] | None = None,
    approval_records: list[Any] | None = None,
) -> dict[str, Any]:
    inp = _input_data(record)
    history = _history(record)
    status = _record_attr(record, "status", "unknown") or "unknown"
    workspace = _workspace(inp)
    lead_payload = _processor_payload(history, "lead_analyzer_processor")
    support_payload = _processor_payload(history, "support_analyzer_processor")
    risks: list[dict[str, Any]] = []

    if status == "failed":
        risks.append(_risk(
            "job_failed",
            "high",
            "Job failed during processing.",
            "Open the error list and rerun or handle manually.",
        ))

    for action in action_records or []:
        if (_record_attr(action, "status") or "").lower() == "failed" or _record_attr(action, "error_message"):
            risks.append(_risk(
                "action_failed",
                "high",
                f"Action {_record_attr(action, 'action_type', 'unknown')} failed.",
                "Review integration error before continuing automation.",
            ))
            break

    pending_approvals = _pending_approval_count(approval_records or [])
    if pending_approvals or status == "awaiting_approval":
        risks.append(_risk(
            "approval_waiting",
            "medium",
            "Automation is waiting for operator approval.",
            "Approve or reject the pending approval to keep the flow moving.",
        ))

    missing = _missing_fields(lead_payload, support_payload)
    if missing:
        risks.append(_risk(
            "missing_customer_info",
            "medium",
            "Required customer information is missing.",
            "Send the generated question message before dispatching or invoicing.",
            {"missing_fields": missing},
        ))

    work_order = workspace.get("work_order") or {}
    project = workspace.get("project") or {}
    if work_order.get("status") == "blocked" or project.get("status") == "on_hold":
        risks.append(_risk(
            "project_blocked",
            "high",
            "Project or work order is blocked.",
            "Resolve the blocker before triggering downstream automation.",
        ))

    if work_order.get("status") == "completed":
        docs = (workspace.get("documentation") or {})
        doc_count = sum(len(v or []) for v in docs.values() if isinstance(v, list))
        delivery_status = (workspace.get("delivery_package") or {}).get("status")
        if doc_count == 0 or delivery_status not in {"ready", "sent"}:
            risks.append(_risk(
                "delivery_package_incomplete",
                "medium",
                "Completed work lacks ready delivery documentation.",
                "Collect documentation and mark the delivery package ready.",
            ))

    profitability = _profitability_snapshot(inp)
    if profitability:
        margin = profitability.get("margin_percent")
        if margin is not None and margin < 20:
            severity = "high" if margin < 0 else "medium"
            risks.append(_risk(
                "low_margin",
                severity,
                f"Project margin is {margin:.1f} percent.",
                "Review price, material, labor, and external cost inputs.",
                profitability,
            ))

    stale_hours = _stale_hours(record)
    if stale_hours is not None and status in _ACTIVE_STATUSES and stale_hours >= 48:
        risks.append(_risk(
            "stale_active_case",
            "medium",
            f"Active case has had no update for {int(stale_hours)} hours.",
            "Review SLA, customer response, or manual owner.",
        ))

    max_rank = max((_SEVERITY_RANK.get(r["severity"], 0) for r in risks), default=0)
    status_map = {0: "ok", 1: "watch", 2: "risk", 3: "critical"}
    return {
        "status": status_map[max_rank],
        "risk_count": len(risks),
        "risks": risks,
    }


def build_wow_flows(record: Any, *, risks: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    inp = _input_data(record)
    history = _history(record)
    job_type = _record_attr(record, "job_type", "unknown") or "unknown"
    workspace = _workspace(inp)
    sender = inp.get("sender") or {}
    email = sender.get("email") or inp.get("sender_email")
    lead_payload = _processor_payload(history, "lead_analyzer_processor")
    support_payload = _processor_payload(history, "support_analyzer_processor")
    dispatch_payload = _last_processor_payload(history, "action_dispatch_processor")
    missing = _missing_fields(lead_payload, support_payload)

    return [
        _lead_reply_flow(job_type, bool(email), bool(missing), dispatch_payload),
        _case_handoff_flow(job_type, workspace),
        _project_invoice_flow(workspace, risks or {"risks": []}),
    ]


def _lead_reply_flow(job_type: str, has_email: bool, has_missing: bool, dispatch_payload: dict) -> dict[str, Any]:
    if job_type not in {"lead", "customer_inquiry"}:
        status = "not_applicable"
        why = "Only lead and support cases use customer reply automation."
    elif not has_email:
        status = "blocked"
        why = "Customer email is missing."
    else:
        status = "ready"
        why = "Reply draft can be prepared and sent only after approval."
    if has_missing:
        why = "Missing information questions can be sent after approval."

    return {
        "id": "approved_customer_reply",
        "title": "Approved customer reply",
        "status": status,
        "why": why,
        "requires_approval": True,
        "external_writes": False,
        "preview_steps": [
            "Use case analysis and tenant context",
            "Prepare a customer reply draft",
            "Create or reuse approval gate",
            "Send through Gmail only after operator approval",
        ],
        "signals": {
            "has_reply_suggestion": bool(dispatch_payload.get("ai_reply_suggestions")),
            "has_customer_email": has_email,
        },
    }


def _case_handoff_flow(job_type: str, workspace: dict) -> dict[str, Any]:
    if job_type not in {"lead", "customer_inquiry"}:
        status = "not_applicable"
        why = "Case-to-project handoff starts from lead or support cases."
    elif workspace:
        status = "ready"
        why = "Operations workspace is present and can guide handoff."
    else:
        status = "blocked"
        why = "Operations workspace is missing."

    return {
        "id": "case_to_project_handoff",
        "title": "Case to project handoff",
        "status": status,
        "why": why,
        "requires_approval": False,
        "external_writes": False,
        "preview_steps": [
            "Summarize customer need and current status",
            "Map work-order status, technician, tasks, and checklist",
            "Highlight missing handoff information",
            "Keep downstream dispatch controlled by existing policy",
        ],
        "signals": {
            "has_operations_workspace": bool(workspace),
            "work_order_status": (workspace.get("work_order") or {}).get("status"),
        },
    }


def _project_invoice_flow(workspace: dict, risks: dict[str, Any]) -> dict[str, Any]:
    work_order = workspace.get("work_order") or {}
    delivery = workspace.get("delivery_package") or {}
    finance = workspace.get("finance") or {}
    has_delivery = delivery.get("status") in {"ready", "sent"}
    has_revenue = any(finance.get(k) for k in ("actual_revenue", "estimated_revenue", "contract_value"))
    blocking_codes = {r.get("code") for r in risks.get("risks", [])}

    if not workspace:
        status = "not_applicable"
        why = "No project workspace is available."
    elif "delivery_package_incomplete" in blocking_codes or not has_delivery:
        status = "blocked"
        why = "Delivery package must be ready before invoice preparation."
    elif work_order.get("status") == "completed" and has_revenue:
        status = "ready"
        why = "Completed work has delivery and finance signals."
    else:
        status = "blocked"
        why = "Project needs completed work and revenue estimate."

    return {
        "id": "project_to_invoice_ready",
        "title": "Project to invoice-ready package",
        "status": status,
        "why": why,
        "requires_approval": True,
        "external_writes": False,
        "preview_steps": [
            "Check work-order completion and delivery package",
            "Summarize finance and margin signals",
            "Prepare pre-accounting handoff",
            "Require approval before any Fortnox export",
        ],
        "signals": {
            "work_order_status": work_order.get("status"),
            "delivery_status": delivery.get("status"),
            "has_revenue_signal": has_revenue,
        },
    }


def _record_attr(obj: Any, name: str, default: Any = None) -> Any:
    value = getattr(obj, name, default)
    return default if callable(value) else value


def _input_data(record: Any) -> dict[str, Any]:
    data = _record_attr(record, "input_data", {}) or {}
    return data if isinstance(data, dict) else {}


def _history(record: Any) -> list[dict[str, Any]]:
    result = _record_attr(record, "result", None)
    if isinstance(result, dict):
        history = result.get("processor_history") or []
        if isinstance(history, list):
            return history
    direct = _record_attr(record, "processor_history", []) or []
    return direct if isinstance(direct, list) else []


def _processor_payload(history: list[dict[str, Any]], processor: str) -> dict[str, Any]:
    for entry in history:
        if entry.get("processor") == processor:
            payload = (entry.get("result") or {}).get("payload") or {}
            return payload if isinstance(payload, dict) else {}
    return {}


def _last_processor_payload(history: list[dict[str, Any]], processor: str) -> dict[str, Any]:
    for entry in reversed(history):
        if entry.get("processor") == processor:
            payload = (entry.get("result") or {}).get("payload") or {}
            return payload if isinstance(payload, dict) else {}
    return {}


def _customer_name(inp: dict[str, Any], history: list[dict[str, Any]]) -> str | None:
    sender = inp.get("sender") or {}
    if sender.get("name") or inp.get("sender_name"):
        return sender.get("name") or inp.get("sender_name")
    for entry in reversed(history):
        payload = (entry.get("result") or {}).get("payload") or {}
        entities = payload.get("entities") or {}
        if entities.get("customer_name"):
            return entities["customer_name"]
    return None


def _workspace(inp: dict[str, Any]) -> dict[str, Any]:
    workspace = inp.get("operations_workspace") or {}
    return workspace if isinstance(workspace, dict) else {}


def _headline(job_type: str, subject: str, customer: str | None) -> str:
    prefix = {
        "lead": "Lead",
        "customer_inquiry": "Support case",
        "invoice": "Invoice case",
    }.get(job_type, "Case")
    if customer:
        return f"{prefix} for {customer}: {subject}"
    return f"{prefix}: {subject}"


def _current_state(status: str, workspace: dict[str, Any]) -> str:
    work_order = workspace.get("work_order") or {}
    project = workspace.get("project") or {}
    if work_order.get("status"):
        return f"Job status {status}, work order {work_order['status']}"
    if project.get("status"):
        return f"Job status {status}, project {project['status']}"
    return f"Job status {status}"


def _next_step_for(
    *,
    job_type: str,
    status: str,
    workspace: dict[str, Any],
    lead_payload: dict[str, Any],
    support_payload: dict[str, Any],
    pending_approvals: int,
) -> str:
    if pending_approvals or status == "awaiting_approval":
        return "Resolve pending approval"
    if job_type == "lead" and lead_payload.get("next_action"):
        return str(lead_payload["next_action"]).replace("_", " ")
    support_next = support_payload.get("support_next_action") or {}
    if isinstance(support_next, dict) and support_next.get("action"):
        return str(support_next["action"]).replace("_", " ")
    work_order = workspace.get("work_order") or {}
    delivery = workspace.get("delivery_package") or {}
    if work_order.get("status") == "completed" and delivery.get("status") != "ready":
        return "Prepare delivery package"
    if work_order.get("status") in {"new", "planned", "scheduled"}:
        return "Move work order forward"
    if status == "completed":
        return "Review automation outcome"
    return "Review case and choose next controlled action"


def _summary_sources(**payloads: dict[str, Any]) -> list[str]:
    labels = {
        "lead_payload": "lead_analysis",
        "support_payload": "support_analysis",
        "dispatch_payload": "action_dispatch",
        "workspace": "operations_workspace",
    }
    return [labels[name] for name, value in payloads.items() if value]


def _action_counts(action_records: list[Any]) -> dict[str, int]:
    counts = {"success": 0, "failed": 0, "other": 0}
    for action in action_records:
        status = str(_record_attr(action, "status", "") or "").lower()
        if status in {"success", "completed"}:
            counts["success"] += 1
        elif status == "failed" or _record_attr(action, "error_message"):
            counts["failed"] += 1
        else:
            counts["other"] += 1
    return counts


def _pending_approval_count(approval_records: list[Any]) -> int:
    count = 0
    for approval in approval_records:
        state = _record_attr(approval, "state", None)
        if state is None:
            payload = _record_attr(approval, "request_payload", {}) or {}
            state = payload.get("state") if isinstance(payload, dict) else None
        if (state or "pending") == "pending":
            count += 1
    return count


def _missing_fields(lead_payload: dict[str, Any], support_payload: dict[str, Any]) -> list[str]:
    lead_missing = (lead_payload.get("missing_info") or {}).get("missing_fields") or []
    support_missing = (support_payload.get("support_missing_info") or {}).get("missing_fields") or []
    return list(dict.fromkeys([*lead_missing, *support_missing]))


def _risk(code: str, severity: str, message: str, recommended_action: str, metadata: dict | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "recommended_action": recommended_action,
        "metadata": metadata or {},
    }


def _profitability_snapshot(inp: dict[str, Any]) -> dict[str, Any] | None:
    workspace = _workspace(inp)
    finance = workspace.get("finance") or inp.get("project_finance") or {}
    if not isinstance(finance, dict) or not finance:
        return None
    revenue = _float(finance.get("actual_revenue")) or _float(finance.get("estimated_revenue")) or _float(finance.get("contract_value"))
    if not revenue:
        return None
    costs = sum(
        _float(finance.get(key)) or 0.0
        for key in ("material_cost", "labor_cost", "external_cost", "other_cost")
    )
    costs += _sum_items(finance.get("materials")) + _sum_items(finance.get("external_costs")) + _sum_items(finance.get("other_costs"))
    if not costs and (_float(finance.get("labor_hours")) or 0) and (_float(finance.get("labor_rate")) or 0):
        costs += (_float(finance.get("labor_hours")) or 0) * (_float(finance.get("labor_rate")) or 0)
    margin_amount = round(revenue - costs, 2)
    return {
        "revenue": round(revenue, 2),
        "costs": round(costs, 2),
        "margin_percent": round((margin_amount / revenue) * 100, 1),
    }


def _float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).replace("kr", "").replace("SEK", "").replace(" ", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _sum_items(items: Any) -> float:
    if not isinstance(items, list):
        return 0.0
    total = 0.0
    for item in items:
        if isinstance(item, dict):
            total += _float(item.get("cost") or item.get("amount") or item.get("total")) or 0.0
    return total


def _stale_hours(record: Any) -> float | None:
    updated_at = _record_attr(record, "updated_at", None) or _record_attr(record, "created_at", None)
    if not isinstance(updated_at, datetime):
        return None
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600
