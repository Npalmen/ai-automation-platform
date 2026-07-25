"""Invariant and security tests for mutations."""

from __future__ import annotations

import pytest

from app.evaluation.errors import ScenarioValidationError
from app.evaluation.generation.parent_loader import load_canonical_parents
from app.evaluation.mutations.engine import generate_mutated_scenario
from app.evaluation.mutations.registry import SECURITY_MUTATION_IDS, get_mutation


def test_unknown_mutation_denied():
    with pytest.raises(ScenarioValidationError, match="Unknown mutation_id"):
        get_mutation("not_a_real_mutation")


def test_injection_text_remains_in_customer_body():
    _, parents = load_canonical_parents()
    for mutation_id in SECURITY_MUTATION_IDS:
        record = generate_mutated_scenario(parents[0], mutation_ids=[mutation_id], seed=1)
        if record.scenario.category == "injection_attempt":
            assert "instruction" in record.scenario.input.message_text.lower() or "system" in record.scenario.input.message_text.lower() or "ignore" in record.scenario.input.message_text.lower()


def test_security_mutations_have_blocking_invariants():
    for mutation_id in SECURITY_MUTATION_IDS:
        definition = get_mutation(mutation_id)
        assert definition.risk_class in {"high", "critical"}
