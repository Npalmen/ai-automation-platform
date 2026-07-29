"""Campaign scenario registry (versioned YAML manifest + scenarios)."""

from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.evaluation.live.campaign.modes import CAMPAIGN_MODES, CAMPAIGN_TYPES
from app.evaluation.live.campaign.schemas import CampaignBudget, CampaignEmailInput, CampaignScenario
from app.evaluation.live.errors import LiveEvalSafetyError

CAMPAIGN_RESOURCES_ROOT = Path(__file__).resolve().parents[1] / "resources" / "campaign"
MANIFEST_FILENAME = "manifest.yaml"


class CampaignRegistryError(LiveEvalSafetyError):
    """Invalid or missing campaign scenario registry."""


def _resources_root() -> Path:
    return CAMPAIGN_RESOURCES_ROOT


def _manifest_path() -> Path:
    return _resources_root() / MANIFEST_FILENAME


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _compute_content_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _parse_budget(raw: dict[str, Any] | None) -> CampaignBudget:
    raw = raw or {}
    return CampaignBudget(
        gmail_sends=int(raw.get("gmail_sends", 1)),
        gmail_replies=int(raw.get("gmail_replies", 0)),
        external_writes=int(raw.get("external_writes", 0)),
    )


def _parse_scenario_file(path: Path, *, campaign_type: str, default_mode: str) -> CampaignScenario:
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    scenario_id = str(raw.get("scenario_id") or path.stem)
    mode = str(raw.get("mode") or default_mode)
    if mode not in CAMPAIGN_MODES:
        raise CampaignRegistryError(f"scenario {scenario_id!r} has invalid mode {mode!r}")

    email_raw = raw.get("email") or {}
    sender = email_raw.get("sender") or {}
    email = CampaignEmailInput(
        subject=str(email_raw.get("subject") or "Test scenario"),
        message_text=str(email_raw.get("message_text") or ""),
        sender_name=str(sender.get("name") or "Testbot Sender"),
        sender_email=str(sender.get("email") or "testbot@eval.test"),
    )

    hash_payload = {
        "scenario_id": scenario_id,
        "scenario_version": str(raw.get("scenario_version") or "v1"),
        "mode": mode,
        "job_type": str(raw.get("job_type") or "unknown"),
        "email": {
            "subject": email.subject,
            "message_text": email.message_text,
            "sender_name": email.sender_name,
            "sender_email": email.sender_email,
        },
    }

    return CampaignScenario(
        scenario_id=scenario_id,
        scenario_version=str(raw.get("scenario_version") or "v1"),
        mode=mode,
        campaign_type=campaign_type,
        job_type=str(raw.get("job_type") or "unknown"),
        service_profile=raw.get("service_profile"),
        synthetic_customer_id=str(raw.get("synthetic_customer_id") or scenario_id),
        thread_id=str(raw.get("thread_id") or scenario_id),
        label=str(raw.get("label") or "krowolf-live-eval"),
        email=email,
        expected_classification=dict(raw.get("expected_classification") or {}),
        expected_entities=dict(raw.get("expected_entities") or {}),
        expected_routing=dict(raw.get("expected_routing") or {}),
        expected_approval=dict(raw.get("expected_approval") or {}),
        expected_customer_card=dict(raw.get("expected_customer_card") or {}),
        expected_external_actions=list(raw.get("expected_external_actions") or []),
        budgets=_parse_budget(raw.get("budgets")),
        content_hash=_compute_content_hash(hash_payload),
    )


@lru_cache
def load_campaign_manifest() -> dict[str, Any]:
    path = _manifest_path()
    if not path.exists():
        raise CampaignRegistryError(f"campaign manifest missing: {path}")
    with path.open(encoding="utf-8") as handle:
        manifest = yaml.safe_load(handle) or {}
    version = str(manifest.get("manifest_version") or "")
    if not version:
        raise CampaignRegistryError("campaign manifest_version is required")
    return manifest


@lru_cache
def _load_registry() -> tuple[
    dict[str, CampaignScenario],
    dict[str, list[str]],
    dict[str, frozenset[str]],
]:
    manifest = load_campaign_manifest()
    campaigns_raw = manifest.get("campaigns") or {}
    scenarios: dict[str, CampaignScenario] = {}
    campaign_index: dict[str, list[str]] = {}
    membership_sets: dict[str, set[str]] = {}

    for campaign_type, spec in campaigns_raw.items():
        if campaign_type not in CAMPAIGN_TYPES:
            raise CampaignRegistryError(f"unknown campaign_type in manifest: {campaign_type!r}")
        default_mode = str(spec.get("default_mode") or "observe")
        scenario_ids: list[str] = []
        for rel_path in spec.get("scenarios") or []:
            path = _resources_root() / str(rel_path)
            if not path.exists():
                raise CampaignRegistryError(f"campaign scenario file missing: {path}")
            scenario = _parse_scenario_file(path, campaign_type=campaign_type, default_mode=default_mode)
            existing = scenarios.get(scenario.scenario_id)
            if existing is not None:
                if existing.content_hash != scenario.content_hash:
                    raise CampaignRegistryError(
                        f"scenario {scenario.scenario_id!r} has conflicting definitions across campaigns"
                    )
            else:
                scenarios[scenario.scenario_id] = scenario
            membership_sets.setdefault(scenario.scenario_id, set()).add(campaign_type)
            scenario_ids.append(scenario.scenario_id)
        campaign_index[campaign_type] = scenario_ids

    scenario_membership = {
        scenario_id: frozenset(sorted(types))
        for scenario_id, types in membership_sets.items()
    }
    for scenario_id, scenario in scenarios.items():
        types = scenario_membership.get(scenario_id, frozenset({scenario.campaign_type}))
        scenarios[scenario_id] = CampaignScenario(
            scenario_id=scenario.scenario_id,
            scenario_version=scenario.scenario_version,
            mode=scenario.mode,
            campaign_type=sorted(types)[0],
            campaign_types=types,
            job_type=scenario.job_type,
            service_profile=scenario.service_profile,
            synthetic_customer_id=scenario.synthetic_customer_id,
            thread_id=scenario.thread_id,
            label=scenario.label,
            email=scenario.email,
            expected_classification=dict(scenario.expected_classification),
            expected_entities=dict(scenario.expected_entities),
            expected_routing=dict(scenario.expected_routing),
            expected_approval=dict(scenario.expected_approval),
            expected_customer_card=dict(scenario.expected_customer_card),
            expected_external_actions=list(scenario.expected_external_actions),
            budgets=scenario.budgets,
            content_hash=scenario.content_hash,
        )

    if not scenarios:
        raise CampaignRegistryError("campaign manifest contains no scenarios")
    return scenarios, campaign_index, scenario_membership


@lru_cache
def _load_all_scenarios() -> dict[str, CampaignScenario]:
    scenarios, _, _ = _load_registry()
    return scenarios


def get_scenario_campaign_membership(scenario_id: str) -> frozenset[str]:
    _, _, membership = _load_registry()
    types = membership.get(scenario_id)
    if types is None:
        raise CampaignRegistryError(f"campaign scenario not found: {scenario_id!r}")
    return types


def scenario_belongs_to_campaign(scenario_id: str, campaign_type: str) -> bool:
    return campaign_type in get_scenario_campaign_membership(scenario_id)


def list_campaign_scenarios(*, campaign_type: str | None = None, mode: str | None = None) -> list[CampaignScenario]:
    scenarios, campaign_index, _ = _load_registry()
    if campaign_type:
        ids = campaign_index.get(campaign_type)
        if ids is None:
            raise CampaignRegistryError(f"unknown campaign_type: {campaign_type!r}")
        items = [scenarios[sid] for sid in ids]
    else:
        items = list(scenarios.values())
    if mode:
        items = [s for s in items if s.mode == mode]
    return sorted(items, key=lambda s: s.scenario_id)


def get_campaign_scenario(scenario_id: str) -> CampaignScenario:
    scenario = _load_all_scenarios().get(scenario_id)
    if scenario is None:
        raise CampaignRegistryError(f"campaign scenario not found: {scenario_id!r}")
    return scenario


def get_campaign_scenario_ids() -> frozenset[str]:
    return frozenset(_load_all_scenarios().keys())


def clear_campaign_registry_cache() -> None:
    load_campaign_manifest.cache_clear()
    _load_registry.cache_clear()
    _load_all_scenarios.cache_clear()


def get_campaign_membership_index() -> dict[str, frozenset[str]]:
    _, _, membership = _load_registry()
    return dict(membership)
