"""Versioned template registry for deterministic scenario generation."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable

from app.evaluation.errors import ScenarioValidationError
from app.evaluation.schema.scenario import ScenarioContract

SYNTHETIC_NAMES = (
    "Erik Synsson",
    "Maria Testsson",
    "Lars Exempel",
    "Sara Provdotter",
    "Johan Fiktiv",
    "Emma Demodata",
)
SYNTHETIC_EMAILS = (
    "erik.synsson@example.com",
    "maria.testsson@example.com",
    "lars.exempel@example.com",
    "sara.provdotter@example.com",
    "johan.fiktiv@example.com",
    "emma.demodata@example.com",
)
SUBJECT_OPENERS = (
    "Angående",
    "Gällande",
    "Fråga om",
    "Behov av",
    "Önskemål om",
    "Kontakt angående",
)
BODY_OPENERS = (
    "Hej,",
    "God dag,",
    "Hejsan,",
    "Hallå,",
    "Tjena,",
    "Hej igen,",
)

KNOWN_TEMPLATE_VERSIONS = frozenset({"v1"})


@dataclass(frozen=True)
class TemplateDefinition:
    template_id: str
    template_version: str
    category: str
    compatible_categories: frozenset[str] | None
    variable_schema: dict[str, str]
    apply: Callable[[ScenarioContract, int], ScenarioContract]


def _pick(pool: tuple[str, ...], seed: int, offset: int = 0) -> str:
    return pool[(seed + offset) % len(pool)]


def _apply_paraphrase_opener(parent: ScenarioContract, seed: int) -> ScenarioContract:
    scenario = copy.deepcopy(parent)
    opener = _pick(BODY_OPENERS, seed)
    name = _pick(SYNTHETIC_NAMES, seed, 1)
    email = _pick(SYNTHETIC_EMAILS, seed, 2)
    body = scenario.input.message_text.strip()
    scenario.input.message_text = f"{opener}\n{body}"
    scenario.input.sender = {"name": name, "email": email}
    scenario.category = "paraphrase"
    tags = list(scenario.tags)
    if "generated" not in tags:
        tags.append("generated")
    if "paraphrase" not in tags:
        tags.append("paraphrase")
    scenario.tags = tags
    scenario.title = f"{parent.title} (paraphrase opener)"
    return scenario


def _apply_paraphrase_subject(parent: ScenarioContract, seed: int) -> ScenarioContract:
    scenario = copy.deepcopy(parent)
    prefix = _pick(SUBJECT_OPENERS, seed)
    subject = scenario.input.subject.strip()
    scenario.input.subject = f"{prefix}: {subject}"
    name = _pick(SYNTHETIC_NAMES, seed, 3)
    email = _pick(SYNTHETIC_EMAILS, seed, 4)
    scenario.input.sender = {"name": name, "email": email}
    scenario.category = "paraphrase"
    tags = list(scenario.tags)
    if "generated" not in tags:
        tags.append("generated")
    if "paraphrase" not in tags:
        tags.append("paraphrase")
    scenario.tags = tags
    scenario.title = f"{parent.title} (paraphrase subject)"
    return scenario


TEMPLATE_REGISTRY: dict[str, TemplateDefinition] = {
    "tpl_paraphrase_opener_v1": TemplateDefinition(
        template_id="tpl_paraphrase_opener_v1",
        template_version="v1",
        category="paraphrase",
        compatible_categories=None,
        variable_schema={
            "opener_index": "int",
            "name_index": "int",
            "email_index": "int",
        },
        apply=_apply_paraphrase_opener,
    ),
    "tpl_paraphrase_subject_v1": TemplateDefinition(
        template_id="tpl_paraphrase_subject_v1",
        template_version="v1",
        category="paraphrase",
        compatible_categories=None,
        variable_schema={
            "subject_prefix_index": "int",
            "name_index": "int",
            "email_index": "int",
        },
        apply=_apply_paraphrase_subject,
    ),
}

DEFAULT_TEMPLATE_IDS = (
    "tpl_paraphrase_opener_v1",
    "tpl_paraphrase_subject_v1",
)


def get_template(template_id: str, template_version: str = "v1") -> TemplateDefinition:
    if template_version not in KNOWN_TEMPLATE_VERSIONS:
        raise ScenarioValidationError(f"Unknown template_version: {template_version}")
    template = TEMPLATE_REGISTRY.get(template_id)
    if template is None:
        raise ScenarioValidationError(f"Unknown template_id: {template_id}")
    if template.template_version != template_version:
        raise ScenarioValidationError(
            f"Template version mismatch for {template_id}: expected {template.template_version}, got {template_version}"
        )
    return template


def assert_parent_compatible(template: TemplateDefinition, parent: ScenarioContract) -> None:
    if template.compatible_categories is None:
        return
    if parent.category not in template.compatible_categories:
        raise ScenarioValidationError(
            f"Template {template.template_id} incompatible with parent category {parent.category!r}"
        )
