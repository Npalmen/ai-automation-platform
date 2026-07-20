"""Typed Pydantic schemas for Slice 2A onboarding drafts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

LeadFieldMode = Literal["required", "optional", "inherit", "skip"]


class ServiceProfileDraftPayload(BaseModel):
    schema_version: int = 1
    selected_profiles: list[str] = Field(default_factory=list)
    lead_requirements: dict[str, dict[str, LeadFieldMode]] = Field(default_factory=dict)


class RoutingDraftPayload(BaseModel):
    schema_version: int = 1
    route_overrides: dict[str, str | None] = Field(default_factory=dict)


class DataStartDraftPayload(BaseModel):
    schema_version: int = 1
    mode: Literal["new_incoming_only"] = "new_incoming_only"


class ServiceProfilePatchRequest(BaseModel):
    version: int
    selected_profiles: list[str]
    lead_requirements: dict[str, dict[str, LeadFieldMode]] = Field(default_factory=dict)


class RoutingPatchRequest(BaseModel):
    version: int
    route_overrides: dict[str, str | None] = Field(default_factory=dict)


class RoutingResetRequest(BaseModel):
    version: int
    service_types: list[str] = Field(min_length=1)


class DataStartPatchRequest(BaseModel):
    version: int
    mode: Literal["new_incoming_only"] = "new_incoming_only"

    @field_validator("mode")
    @classmethod
    def only_supported_mode(cls, v: str) -> str:
        if v != "new_incoming_only":
            raise ValueError("Only new_incoming_only is supported in slice 2A.")
        return v
