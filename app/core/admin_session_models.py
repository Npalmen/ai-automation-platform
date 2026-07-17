"""Typed admin session API models for operator panel auth."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

OperatorRole = Literal["read_only", "operations", "admin"]
OperatorEnvironment = Literal["local", "test", "production"]

VALID_OPERATOR_ROLES: frozenset[str] = frozenset({"read_only", "operations", "admin"})


class OperatorInfo(BaseModel):
    id: str
    display_name: str
    role: OperatorRole


class AdminMeResponse(BaseModel):
    authenticated: bool
    operator: OperatorInfo
    environment: OperatorEnvironment


class AdminLoginResponse(BaseModel):
    ok: bool
    mode: str
    operator: OperatorInfo | None = None
    environment: OperatorEnvironment | None = None


class AdminLogoutResponse(BaseModel):
    ok: bool
