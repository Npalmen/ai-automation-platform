"""Typed Pydantic schemas for Slice 2B integrations drafts (config-only)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.admin.onboarding.slice2b_registry import SHEETS_EXPORT_TABS

SheetsTab = Literal["Leads", "Support", "Logg"]


class GmailIntegrationConfig(BaseModel):
    requested: bool = False
    label_scope_slug: str = ""


class VismaIntegrationConfig(BaseModel):
    requested: bool = False


class GoogleSheetsIntegrationConfig(BaseModel):
    requested: bool = False
    spreadsheet_id: str = ""
    export_tabs: list[SheetsTab] = Field(default_factory=list)

    @field_validator("export_tabs")
    @classmethod
    def tabs_allowlisted(cls, tabs: list[str]) -> list[str]:
        allowed = set(SHEETS_EXPORT_TABS)
        for tab in tabs:
            if tab not in allowed:
                raise ValueError(f"Unsupported export tab: {tab}")
        return tabs


class MondayIntegrationConfig(BaseModel):
    requested: bool = False


SelectionStatusDraft = Literal["not_selected", "selected_optional", "selected_required"]


class IntegrationSelectionDraft(BaseModel):
    selection_status: SelectionStatusDraft = "not_selected"
    migration_review_required: bool = False


GroupImplementationType = Literal["manual_accounting_routing", "integration"]
FinanceDestinationChoice = Literal["visma", "manual_accounting_routing", "none"]
VismaDisposition = Literal["not_selected", "selected_optional"]


class GroupImplementationDraft(BaseModel):
    type: GroupImplementationType
    integration_key: str | None = None


class FinanceDestinationPatch(BaseModel):
    choice: FinanceDestinationChoice
    visma_disposition: VismaDisposition | None = None

    @model_validator(mode="after")
    def manual_requires_visma_disposition(self) -> "FinanceDestinationPatch":
        if self.choice == "manual_accounting_routing" and self.visma_disposition is None:
            raise ValueError("visma_disposition is required for manual_accounting_routing")
        return self


class IntegrationsDraftPayload(BaseModel):
    schema_version: int = 1
    requested_integrations: list[str] = Field(default_factory=list)
    selections: dict[str, IntegrationSelectionDraft] = Field(default_factory=dict)
    group_implementations: dict[str, GroupImplementationDraft] = Field(default_factory=dict)
    gmail: GmailIntegrationConfig = Field(default_factory=GmailIntegrationConfig)
    visma: VismaIntegrationConfig = Field(default_factory=VismaIntegrationConfig)
    google_sheets: GoogleSheetsIntegrationConfig = Field(default_factory=GoogleSheetsIntegrationConfig)
    monday: MondayIntegrationConfig = Field(default_factory=MondayIntegrationConfig)


class ExternalRoutingTargetDraft(BaseModel):
    target_type: Literal["monday_board"] = "monday_board"
    board_id: str = ""
    board_name: str = ""
    group_id: str | None = None
    group_name: str | None = None


class ExternalRoutingDraftPayload(BaseModel):
    schema_version: int = 1
    targets: dict[str, ExternalRoutingTargetDraft] = Field(default_factory=dict)


class IntegrationsPatchRequest(BaseModel):
    version: int
    requested_integrations: list[str] | None = None
    selections: dict[str, IntegrationSelectionDraft] | None = None
    group_implementations: dict[str, GroupImplementationDraft] | None = None
    finance_destination: FinanceDestinationPatch | None = None
    gmail: GmailIntegrationConfig | None = None
    visma: VismaIntegrationConfig | None = None
    google_sheets: GoogleSheetsIntegrationConfig | None = None
    monday: MondayIntegrationConfig | None = None


class ExternalRoutingPatchRequest(BaseModel):
    version: int
    targets: dict[str, ExternalRoutingTargetDraft] = Field(default_factory=dict)


class ExternalRoutingResetRequest(BaseModel):
    version: int
    job_types: list[str] = Field(min_length=1)


class IntegrationActionRequest(BaseModel):
    version: int
    reason: str | None = None
