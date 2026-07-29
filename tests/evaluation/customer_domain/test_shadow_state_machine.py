"""Hermetic tests for shadow observation state machine."""

from __future__ import annotations

import pytest

from app.domain.customer.shadow_enums import ShadowObservationState
from app.domain.customer.shadow_state import ShadowStateTransitionError, assert_shadow_observation_transition


def test_allowed_system_transitions():
    assert_shadow_observation_transition(
        ShadowObservationState.OBSERVED, ShadowObservationState.NORMALIZED
    )
    assert_shadow_observation_transition(
        ShadowObservationState.EXTRACTED, ShadowObservationState.MATCH_ASSESSED
    )


def test_operator_only_promotion():
    assert_shadow_observation_transition(
        ShadowObservationState.AWAITING_OPERATOR,
        ShadowObservationState.PROMOTED,
        operator_action=True,
    )


def test_forbidden_direct_promotion():
    with pytest.raises(ShadowStateTransitionError):
        assert_shadow_observation_transition(
            ShadowObservationState.EXTRACTED,
            ShadowObservationState.PROMOTED,
        )


def test_shadow_flags_default_false():
    from app.services.shadow_gate import shadow_flags_default_false

    assert shadow_flags_default_false() is True
