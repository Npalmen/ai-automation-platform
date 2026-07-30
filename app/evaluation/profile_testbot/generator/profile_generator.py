"""Deterministic profile-based scenario generator."""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.profile_testbot.constants import (
    AUTOMATIC_CANARY_TARGET,
    AUTOMATIC_CORE_TARGET,
    GENERATOR_MODEL,
    GENERATOR_PROMPT_VERSION,
    HERMETIC_SCENARIO_TARGET,
    ORACLE_VERSION,
    SEMI_AUTO_HOLD_EDGE_MIN,
    SEMI_AUTO_SCENARIO_TARGET,
    SEMI_AUTO_SEND_AFTER_APPROVAL_MIN,
)
from app.evaluation.profile_testbot.generator.coverage_matrix import (
    CoverageCell,
    build_coverage_matrix,
    required_coverage_keys,
)
from app.evaluation.profile_testbot.generator.deduplication import semantic_fingerprint
from app.evaluation.profile_testbot.generator.templates import render_template, template_for_intent
from app.evaluation.profile_testbot.profile_contract import CustomerProfileSnapshot
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario, ProfileScenarioInput


@dataclass(frozen=True)
class GenerationOptions:
    profile: CustomerProfileSnapshot
    seed: int = 0
    count: int = HERMETIC_SCENARIO_TARGET
    campaign_phase: str = "hermetic"
    mode: str = "observe"


def _select_cells(options: GenerationOptions) -> list[CoverageCell]:
    matrix = build_coverage_matrix()
    if not matrix:
        return []
    selected: list[CoverageCell] = []
    index = 0
    while len(selected) < options.count:
        cell = matrix[(options.seed + index) % len(matrix)]
        selected.append(cell)
        index += 1
    return selected


def _mode_for_phase(phase: str, send_behavior: str) -> str:
    if phase == "hermetic":
        return "observe"
    if phase in {"automatic-canary", "automatic-core"}:
        return "automatic"
    if send_behavior in {"send_after_approval", "draft_for_approval"}:
        return "semi_automatic"
    return "observe"


def _build_scenario_from_cell(
    *,
    profile: CustomerProfileSnapshot,
    cell: CoverageCell,
    seed: int,
    campaign_phase: str,
    scenario_id: str,
) -> ProfileScenario:
    template = template_for_intent(cell.intent)
    rendered = render_template(template, cell, seed=seed)
    mutation_types: list[str] = []
    if cell.ambiguity == "adversarial":
        mutation_types.append("prompt_injection")
    if cell.thread_state == "duplicate":
        mutation_types.append("duplicate_message")
    draft = ProfileScenario(
        scenario_id=scenario_id,
        profile_id=profile.profile_id,
        profile_snapshot_hash=profile.profile_snapshot_hash,
        family=template.family,
        intent=cell.intent,
        risk_class=cell.risk_class,
        input=ProfileScenarioInput(
            subject=rendered["subject"],
            message_text=rendered["message_text"],
            sender_name=rendered["sender_name"],
            sender_email=rendered["sender_email"],
            language=cell.language,
        ),
        expected_classification={
            "job_type": template.job_type,
            "label": template.classification_label,
        },
        expected_route={
            "queue": template.route_queue,
            "final_job_status": "manual_review"
            if cell.expected_send_behavior in {"hold", "reject"}
            else "awaiting_approval",
        },
        expected_authorization={
            "policy_authorization": template.policy_authorization,
        },
        expected_send_behavior=cell.expected_send_behavior,
        required_reply_facts=list(template.required_facts),
        forbidden_reply_claims=list(template.forbidden_claims),
        customer_state_setup={"state": cell.customer_state, "seed": seed, "ambiguity": cell.ambiguity},
        thread_setup={"state": cell.thread_state},
        mutation_types=mutation_types,
        generator_provenance={
            "seed": seed,
            "template_id": template.template_id,
            "generator_model": GENERATOR_MODEL,
            "generator_prompt_version": GENERATOR_PROMPT_VERSION,
            "parent_scenario": None,
        },
        oracle_version=ORACLE_VERSION,
        mode=_mode_for_phase(campaign_phase, cell.expected_send_behavior),
        campaign_phase=campaign_phase,
        semantic_hash="",
    )
    semantic = semantic_fingerprint(draft)
    return ProfileScenario(
        scenario_id=draft.scenario_id,
        profile_id=draft.profile_id,
        profile_snapshot_hash=draft.profile_snapshot_hash,
        family=draft.family,
        intent=draft.intent,
        risk_class=draft.risk_class,
        input=draft.input,
        expected_classification=draft.expected_classification,
        expected_route=draft.expected_route,
        expected_authorization=draft.expected_authorization,
        expected_send_behavior=draft.expected_send_behavior,
        required_reply_facts=draft.required_reply_facts,
        optional_reply_facts=draft.optional_reply_facts,
        forbidden_reply_claims=draft.forbidden_reply_claims,
        required_questions=draft.required_questions,
        customer_state_setup=draft.customer_state_setup,
        thread_setup=draft.thread_setup,
        provider_setup=draft.provider_setup,
        mutation_types=draft.mutation_types,
        generator_provenance=draft.generator_provenance,
        oracle_version=draft.oracle_version,
        semantic_hash=semantic,
        mode=draft.mode,
        campaign_phase=draft.campaign_phase,
    )


def _generate_from_cells(
    *,
    profile: CustomerProfileSnapshot,
    cells: list[CoverageCell],
    campaign_phase: str,
    seed: int,
    id_prefix: str,
) -> list[ProfileScenario]:
    scenarios: list[ProfileScenario] = []
    for index, cell in enumerate(cells):
        scenarios.append(
            _build_scenario_from_cell(
                profile=profile,
                cell=cell,
                seed=seed + index,
                campaign_phase=campaign_phase,
                scenario_id=f"{id_prefix}-{index:04d}",
            )
        )
    return scenarios


def generate_profile_scenarios(options: GenerationOptions) -> list[ProfileScenario]:
    scenarios: list[ProfileScenario] = []
    seen_semantic: set[str] = set()
    cells = _select_cells(options)
    index = 0
    while len(scenarios) < options.count and index < len(cells) * 3:
        cell = cells[index % len(cells)]
        scenario = _build_scenario_from_cell(
            profile=options.profile,
            cell=cell,
            seed=options.seed + index,
            campaign_phase=options.campaign_phase,
            scenario_id=f"PTB-{options.campaign_phase[:3].upper()}-{len(scenarios):04d}",
        )
        if scenario.semantic_hash in seen_semantic:
            index += 1
            continue
        seen_semantic.add(scenario.semantic_hash)
        scenarios.append(scenario)
        index += 1
    return scenarios


def generate_hermetic_campaign(profile: CustomerProfileSnapshot, *, seed: int = 0) -> list[ProfileScenario]:
    required_cells = []
    for key in sorted(required_coverage_keys()):
        parts = key.split("|")
        required_cells.append(
            CoverageCell(
                intent=parts[0],
                risk_class=parts[1],
                expected_send_behavior=parts[2],
                customer_state=parts[3],
                thread_state=parts[4],
                language=parts[5],
                ambiguity=parts[6],
            )
        )
    pinned = _generate_from_cells(
        profile=profile,
        cells=required_cells,
        campaign_phase="hermetic",
        seed=seed,
        id_prefix="PTB-PIN",
    )
    remaining = max(0, HERMETIC_SCENARIO_TARGET - len(pinned))
    generated = generate_profile_scenarios(
        GenerationOptions(
            profile=profile,
            seed=seed,
            count=remaining,
            campaign_phase="hermetic",
            mode="observe",
        )
    )
    return (pinned + generated)[:HERMETIC_SCENARIO_TARGET]


def generate_semi_auto_campaign(profile: CustomerProfileSnapshot, *, seed: int = 0) -> list[ProfileScenario]:
    pool = generate_hermetic_campaign(profile, seed=seed)
    send_after = [s for s in pool if s.expected_send_behavior == "send_after_approval"]
    hold_edge = [
        s
        for s in pool
        if s.expected_send_behavior in {"hold", "reject", "no_reply", "observe_only", "draft_for_approval"}
    ]
    selected: list[ProfileScenario] = []
    for index, scenario in enumerate(send_after[:SEMI_AUTO_SEND_AFTER_APPROVAL_MIN]):
        selected.append(_relabel_scenario(scenario, phase="semi-auto", index=index))
    offset = len(selected)
    for index, scenario in enumerate(hold_edge[:SEMI_AUTO_HOLD_EDGE_MIN]):
        selected.append(_relabel_scenario(scenario, phase="semi-auto", index=offset + index))
    return selected[:SEMI_AUTO_SCENARIO_TARGET]


def _relabel_scenario(scenario: ProfileScenario, *, phase: str, index: int) -> ProfileScenario:
    return ProfileScenario(
        scenario_id=f"PTB-{phase[:3].upper()}-{index:04d}",
        profile_id=scenario.profile_id,
        profile_snapshot_hash=scenario.profile_snapshot_hash,
        family=scenario.family,
        intent=scenario.intent,
        risk_class=scenario.risk_class,
        input=scenario.input,
        expected_classification=scenario.expected_classification,
        expected_route=scenario.expected_route,
        expected_authorization=scenario.expected_authorization,
        expected_send_behavior=scenario.expected_send_behavior,
        required_reply_facts=scenario.required_reply_facts,
        optional_reply_facts=scenario.optional_reply_facts,
        forbidden_reply_claims=scenario.forbidden_reply_claims,
        required_questions=scenario.required_questions,
        customer_state_setup=scenario.customer_state_setup,
        thread_setup=scenario.thread_setup,
        provider_setup=scenario.provider_setup,
        mutation_types=scenario.mutation_types,
        generator_provenance=scenario.generator_provenance,
        oracle_version=scenario.oracle_version,
        semantic_hash=scenario.semantic_hash,
        mode="semi_automatic",
        campaign_phase=phase,
    )


def generate_automatic_canary(profile: CustomerProfileSnapshot, *, seed: int = 0) -> list[ProfileScenario]:
    scenarios = generate_profile_scenarios(
        GenerationOptions(
            profile=profile,
            seed=seed,
            count=AUTOMATIC_CANARY_TARGET * 8,
            campaign_phase="automatic-canary",
            mode="automatic",
        )
    )
    safe = [s for s in scenarios if s.expected_send_behavior == "automatic_safe_send"]
    hold = [s for s in scenarios if s.expected_send_behavior in {"hold", "no_reply", "reject"}]
    if len(safe) < 2 or len(hold) < 2:
        safe = [
            _build_scenario_from_cell(
                profile=profile,
                cell=CoverageCell("lead_new", "low", "automatic_safe_send", "new", "new_thread", "sv", "clear"),
                seed=seed,
                campaign_phase="automatic-canary",
                scenario_id="PTB-CAN-SAFE-01",
            ),
            _build_scenario_from_cell(
                profile=profile,
                cell=CoverageCell("support_status", "low", "automatic_safe_send", "returning", "continuation", "sv", "clear"),
                seed=seed + 1,
                campaign_phase="automatic-canary",
                scenario_id="PTB-CAN-SAFE-02",
            ),
        ]
        hold = [
            _build_scenario_from_cell(
                profile=profile,
                cell=CoverageCell("lead_price", "medium", "hold", "new", "new_thread", "sv", "clear"),
                seed=seed + 2,
                campaign_phase="automatic-canary",
                scenario_id="PTB-CAN-HOLD-01",
            ),
            _build_scenario_from_cell(
                profile=profile,
                cell=CoverageCell("spam_newsletter", "low", "no_reply", "new", "new_thread", "sv", "clear"),
                seed=seed + 3,
                campaign_phase="automatic-canary",
                scenario_id="PTB-CAN-HOLD-02",
            ),
        ]
    return (safe[:2] + hold[:2])[:AUTOMATIC_CANARY_TARGET]


def generate_automatic_core(profile: CustomerProfileSnapshot, *, seed: int = 0) -> list[ProfileScenario]:
    scenarios = generate_profile_scenarios(
        GenerationOptions(
            profile=profile,
            seed=seed,
            count=AUTOMATIC_CORE_TARGET * 2,
            campaign_phase="automatic-core",
            mode="automatic",
        )
    )
    return scenarios[:AUTOMATIC_CORE_TARGET]
