"""Exhaustive deterministic checks for the AMC gate dispatcher."""

from __future__ import annotations

from dataclasses import asdict
from itertools import product

import pytest

from pilot.gate_dispatcher import (
    ACTIONS,
    GateState,
    InvalidGateState,
    allowed_actions,
    attempt_action,
    grant_approval,
    invalidate_evidence,
    validate_state,
)
from pilot.tests.dispatcher_oracle import OracleState, allowed as oracle_allowed


CANONICAL_PHASES = (
    GateState(),
    GateState(evidence_current=True, revision=1),
    GateState(evidence_current=True, license_verified=True, revision=2),
    GateState(
        evidence_current=True,
        license_verified=True,
        recommendation_ready=True,
        revision=3,
    ),
    GateState(
        evidence_current=True,
        license_verified=True,
        recommendation_ready=True,
        revision=3,
        approval_status="pending",
        approval_request_revision=3,
    ),
    GateState(
        evidence_current=True,
        license_verified=True,
        recommendation_ready=True,
        revision=3,
        approval_status="granted",
        approval_request_revision=3,
        approval_grant_revision=3,
    ),
    GateState(
        evidence_current=True,
        license_verified=True,
        recommendation_ready=True,
        revision=3,
        approval_status="granted",
        approval_request_revision=3,
        approval_grant_revision=3,
        published=True,
    ),
)


def to_oracle(state: GateState) -> OracleState:
    return OracleState(**asdict(state))


@pytest.mark.parametrize("state", CANONICAL_PHASES)
def test_phase_table_matches_independent_oracle(state: GateState) -> None:
    assert allowed_actions(state) == oracle_allowed(to_oracle(state))


@pytest.mark.parametrize("state", CANONICAL_PHASES)
@pytest.mark.parametrize("action", sorted(ACTIONS | {"unknown_action"}))
def test_every_action_from_every_canonical_phase(
    state: GateState, action: str
) -> None:
    expected = action in oracle_allowed(to_oracle(state))
    new_state, event = attempt_action(state, action)
    assert (event["type"] == "action_accepted") is expected
    if not expected:
        assert new_state == state
        assert event["revision"] == state.revision
        expected_reason = (
            "unsupported_action"
            if action == "unknown_action"
            else "prerequisite_or_approval_gate"
        )
        assert event["reason"] == expected_reason


def test_complete_accepted_path_has_exact_transition_effects() -> None:
    state = GateState()
    expected_revisions = {
        "refresh_evidence": 1,
        "verify_license": 2,
        "form_recommendation": 3,
        "request_publication_approval": 3,
    }
    for action, expected_revision in expected_revisions.items():
        state, event = attempt_action(state, action)
        assert event["type"] == "action_accepted"
        assert state.revision == expected_revision

    stale_state, stale_event = grant_approval(state, basis_revision=2)
    assert stale_state == state
    assert stale_event["type"] == "approval_rejected"

    state, event = grant_approval(state, basis_revision=3)
    assert event["type"] == "approval_granted"
    assert state.approval_request_revision == state.approval_grant_revision == 3
    state, event = attempt_action(state, "publish")
    assert event["type"] == "action_accepted"
    assert state.published
    assert allowed_actions(state) == set()


@pytest.mark.parametrize("state", CANONICAL_PHASES)
def test_invalidation_from_every_phase_resets_dependencies(state: GateState) -> None:
    new_state, event = invalidate_evidence(state)
    assert event == {
        "type": "evidence_invalidated",
        "revision": state.revision + 1,
        "approval_effect": "revoked",
    }
    assert new_state == GateState(revision=state.revision + 1)
    assert allowed_actions(new_state) == {"refresh_evidence"}


def test_exhaustive_small_state_space_accepts_only_contract_valid_states() -> None:
    valid_count = 0
    revision = 1
    references = (None, 0, 1, 2)
    for values in product(
        (False, True),
        (False, True),
        (False, True),
        ("revoked", "pending", "granted", "unknown"),
        references,
        references,
        (False, True),
    ):
        state = GateState(
            evidence_current=values[0],
            license_verified=values[1],
            recommendation_ready=values[2],
            revision=revision,
            approval_status=values[3],
            approval_request_revision=values[4],
            approval_grant_revision=values[5],
            published=values[6],
        )
        try:
            validate_state(state)
        except InvalidGateState:
            continue
        valid_count += 1
        assert allowed_actions(state) == oracle_allowed(to_oracle(state))
    assert valid_count == 7


@pytest.mark.parametrize(
    "state",
    (
        GateState(evidence_current=False, license_verified=True),
        GateState(evidence_current=True, recommendation_ready=True),
        GateState(approval_status="unknown"),
        GateState(approval_status="revoked", approval_request_revision=0),
        GateState(approval_status="pending", approval_request_revision=None),
        GateState(approval_status="granted"),
        GateState(published=True),
        GateState(revision=-1),
        GateState(revision=True),
        GateState(evidence_current=1),
    ),
)
def test_impossible_or_malformed_states_are_rejected(state: GateState) -> None:
    with pytest.raises(InvalidGateState):
        validate_state(state)
    with pytest.raises(InvalidGateState):
        allowed_actions(state)


@pytest.mark.parametrize("action", (None, 3, False, [], {}))
def test_non_string_actions_are_rejected_at_boundary(action: object) -> None:
    with pytest.raises(TypeError):
        attempt_action(GateState(), action)  # type: ignore[arg-type]


def test_empty_action_is_rejected_at_boundary() -> None:
    with pytest.raises(ValueError):
        attempt_action(GateState(), "")


@pytest.mark.parametrize("basis", (-1, True, None, "3"))
def test_malformed_approval_basis_is_rejected(basis: object) -> None:
    with pytest.raises(ValueError):
        grant_approval(GateState(), basis_revision=basis)  # type: ignore[arg-type]
