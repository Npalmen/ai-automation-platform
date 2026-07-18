"""Slice 2B registry: external routing targets and settings schema version."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

SETTINGS_SCHEMA_VERSION_SLICE2B: int = 3

Availability = Literal["available", "read_only", "deferred"]

SHEETS_EXPORT_TABS: tuple[str, ...] = ("Leads", "Support", "Logg")


@dataclass(frozen=True)
class ExternalRoutingTargetDefinition:
    key: str
    label_sv: str
    job_type: str
    integration_key: str
    enforced: bool
    availability: Availability
    supported_in_current_slice: bool
    required_target_keys: tuple[str, ...]


EXTERNAL_ROUTING_TARGETS: dict[str, ExternalRoutingTargetDefinition] = {
    "monday_board": ExternalRoutingTargetDefinition(
        key="monday_board",
        label_sv="Monday board (lead)",
        job_type="lead",
        integration_key="monday",
        enforced=True,
        availability="available",
        supported_in_current_slice=True,
        required_target_keys=("board_id", "board_name"),
    ),
    "google_sheets_tab": ExternalRoutingTargetDefinition(
        key="google_sheets_tab",
        label_sv="Google Sheets (export)",
        job_type="",
        integration_key="google_sheets",
        enforced=False,
        availability="deferred",
        supported_in_current_slice=False,
        required_target_keys=("spreadsheet_id", "tab"),
    ),
    "visma_workflow": ExternalRoutingTargetDefinition(
        key="visma_workflow",
        label_sv="Visma workflow",
        job_type="",
        integration_key="visma",
        enforced=False,
        availability="deferred",
        supported_in_current_slice=False,
        required_target_keys=(),
    ),
}


def enforced_external_routing_targets() -> list[ExternalRoutingTargetDefinition]:
    return [
        t for t in EXTERNAL_ROUTING_TARGETS.values() if t.enforced and t.supported_in_current_slice
    ]
