"""Shadow observation state machine helpers."""

from __future__ import annotations

from app.domain.customer.shadow_enums import (
    ShadowObservationState,
    can_transition_shadow_observation,
)


class ShadowStateTransitionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


FORBIDDEN_DIRECT_TRANSITIONS = frozenset({
    (ShadowObservationState.OBSERVED, ShadowObservationState.PROMOTED),
    (ShadowObservationState.EXTRACTED, ShadowObservationState.PROMOTED),
    (ShadowObservationState.MATCH_ASSESSED, ShadowObservationState.PROMOTED),
})


def assert_shadow_observation_transition(
    current: ShadowObservationState,
    target: ShadowObservationState,
    *,
    operator_action: bool = False,
) -> None:
    pair = (current, target)
    if pair in FORBIDDEN_DIRECT_TRANSITIONS and not operator_action:
        raise ShadowStateTransitionError(
            "FORBIDDEN_SHADOW_TRANSITION",
            f"Direct transition {current.value} -> {target.value} is forbidden",
        )
    if not can_transition_shadow_observation(current, target, operator_action=operator_action):
        raise ShadowStateTransitionError(
            "UNSUPPORTED_SHADOW_TRANSITION",
            f"Transition {current.value} -> {target.value} is not allowed",
        )
