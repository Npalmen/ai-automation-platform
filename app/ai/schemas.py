from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


AllowedJobType = Literal[
    "invoice",
    "lead",
    "customer_inquiry",
    "unknown",
]


class ClassificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    detected_job_type: AllowedJobType
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list)


class EntityExtractionEntities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_name: str | None = None
    company_name: str | None = None
    email: str | None = None
    phone: str | None = None
    organization_number: str | None = None
    invoice_number: str | None = None
    amount: float | None = None
    currency: str | None = None
    due_date: str | None = None
    requested_service: str | None = None
    address: str | None = None
    city: str | None = None
    notes: str | None = None


class EntityExtractionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entities: EntityExtractionEntities
    confidence: float = Field(ge=0.0, le=1.0)


class LeadScoringResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lead_score: int = Field(ge=0, le=100)
    priority: Literal["low", "medium", "high"]
    routing: Literal["crm_update", "priority_sales_followup", "manual_review"]
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class InquiryAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inquiry_type: Literal["support", "sales", "billing", "general"]
    priority: Literal["low", "medium", "high"]
    routing: Literal["support_queue", "sales_queue", "billing_queue", "case_queue", "manual_review"]
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class InvoiceAnalysisData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    supplier_name: str | None = None
    organization_number: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    currency: str | None = None
    amount_ex_vat: float | None = None
    vat_amount: float | None = None
    amount_inc_vat: float | None = None
    reference: str | None = None


class InvoiceAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_data: InvoiceAnalysisData
    validation_status: Literal["validated", "incomplete", "manual_review"]
    duplicate_suspected: bool
    missing_critical: list[str] = Field(default_factory=list)
    approval_route: Literal["auto_approve", "approval_required", "manual_review"]
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class DecisionActionFlags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    create_crm_lead: bool = False
    notify_human: bool = False
    request_missing_data: bool = False


class DecisioningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["auto_route", "manual_review", "hold"]
    target_queue: str
    action_flags: DecisionActionFlags
    reasons: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)