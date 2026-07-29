"""Shadow observation ledger enums — isolated from verified customer domain."""

from enum import Enum


class ShadowObservationState(str, Enum):
    OBSERVED = "observed"
    NORMALIZED = "normalized"
    EXTRACTED = "extracted"
    MATCH_ASSESSED = "match_assessed"
    AWAITING_OPERATOR = "awaiting_operator"
    PROMOTED = "promoted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ShadowMatchProposalState(str, Enum):
    PROPOSED = "proposed"
    AWAITING_OPERATOR = "awaiting_operator"
    CONFIRMED_FOR_PROMOTION = "confirmed_for_promotion"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ShadowFactProposalState(str, Enum):
    SHADOW = "shadow"
    APPROVED_FOR_PROMOTION = "approved_for_promotion"
    PROMOTED_AS_PROPOSED_FACT = "promoted_as_proposed_fact"
    VERIFIED_BY_OPERATOR = "verified_by_operator"


class ShadowSignalType(str, Enum):
    EMAIL = "email"
    PHONE = "phone"
    PERSON_NAME = "person_name"
    COMPANY_NAME = "company_name"
    ORGANISATION_NUMBER = "organisation_number"
    ADDRESS = "address"
    REPLY_TO = "reply_to"
    SENDER = "sender"
    THREAD_ID = "thread_id"


class ShadowTrustLevel(str, Enum):
    TRUSTED = "trusted"
    OBSERVED = "observed"
    UNTRUSTED = "untrusted"
    PROPOSED = "proposed"
    VERIFIED = "verified"


# Allowed system transitions for shadow observations.
SHADOW_OBSERVATION_TRANSITIONS: dict[ShadowObservationState, frozenset[ShadowObservationState]] = {
    ShadowObservationState.OBSERVED: frozenset({ShadowObservationState.NORMALIZED, ShadowObservationState.SUPERSEDED}),
    ShadowObservationState.NORMALIZED: frozenset({ShadowObservationState.EXTRACTED, ShadowObservationState.SUPERSEDED}),
    ShadowObservationState.EXTRACTED: frozenset({
        ShadowObservationState.MATCH_ASSESSED,
        ShadowObservationState.AWAITING_OPERATOR,
        ShadowObservationState.SUPERSEDED,
    }),
    ShadowObservationState.MATCH_ASSESSED: frozenset({
        ShadowObservationState.AWAITING_OPERATOR,
        ShadowObservationState.SUPERSEDED,
    }),
    ShadowObservationState.AWAITING_OPERATOR: frozenset({
        ShadowObservationState.PROMOTED,
        ShadowObservationState.REJECTED,
        ShadowObservationState.SUPERSEDED,
    }),
    ShadowObservationState.PROMOTED: frozenset(),
    ShadowObservationState.REJECTED: frozenset(),
    ShadowObservationState.SUPERSEDED: frozenset(),
}


def can_transition_shadow_observation(
    current: ShadowObservationState,
    target: ShadowObservationState,
    *,
    operator_action: bool = False,
) -> bool:
    if operator_action:
        if current == ShadowObservationState.AWAITING_OPERATOR and target in {
            ShadowObservationState.PROMOTED,
            ShadowObservationState.REJECTED,
        }:
            return True
        return False
    allowed = SHADOW_OBSERVATION_TRANSITIONS.get(current, frozenset())
    return target in allowed
