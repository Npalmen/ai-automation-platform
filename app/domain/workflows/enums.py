from enum import Enum


class JobType(str, Enum):
    # Core
    INTAKE = "intake"
    CLASSIFICATION = "classification"
    ENTITY_EXTRACTION = "entity_extraction"
    POLICY = "policy"
    HUMAN_HANDOFF = "human_handoff"

    # Legacy / current active
    EMAIL = "email"
    CONTRACT = "contract"

    # Finance
    INVOICE = "invoice"
    RECEIPT = "receipt"
    APPROVAL = "approval"
    ANOMALY = "anomaly"
    PAYMENT_FOLLOWUP = "payment_followup"
    FINANCE_SUMMARY = "finance_summary"

    # Sales
    LEAD = "lead"
    LEAD_QUALIFICATION = "lead_qualification"
    QUOTE = "quote"
    SALES_FOLLOWUP = "sales_followup"
    CRM_UPDATE = "crm_update"
    OPPORTUNITY_SUMMARY = "opportunity_summary"

    # Support
    CUSTOMER_INQUIRY = "customer_inquiry"
    SUPPORT_TRIAGE = "support_triage"
    RESPONSE_DRAFT = "response_draft"
    ESCALATION = "escalation"
    CASE_SUMMARY = "case_summary"
    SLA_MONITORING = "sla_monitoring"

    # Management
    KPI = "kpi"
    EXEC_SUMMARY = "exec_summary"
    RISK = "risk"
    DECISION_SUPPORT = "decision_support"
    REPORT = "report"

    UNKNOWN = "unknown"