"""Pydantic/TypedDict models for customer workspace session auth."""

from __future__ import annotations

from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class CustomerSessionContext(TypedDict):
    user_id: str
    tenant_id: str
    email: str
    display_name: str
    role: Literal["customer_viewer"]


class CustomerLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=256)
    password: str = Field(min_length=1, max_length=64)


class CustomerLoginResponse(BaseModel):
    ok: bool = True
    user_id: str
    email: str
    display_name: str
    role: Literal["customer_viewer"] = "customer_viewer"
    tenant_id: str


class CustomerLogoutResponse(BaseModel):
    ok: bool = True


class CustomerMeResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    role: Literal["customer_viewer"] = "customer_viewer"
    tenant_id: str
    company_name: str
