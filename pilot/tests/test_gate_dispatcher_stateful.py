"""Generated rule-sequence testing against an independent dispatcher model."""

from __future__ import annotations

from dataclasses import asdict

from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from pilot.gate_dispatcher import (
    GateState,
    allowed_actions,
    attempt_action,
    grant_approval,
    invalidate_evidence,
    validate_state,
)
from pilot.tests.dispatcher_oracle import (
    ACTIONS,
    OracleState,
    allowed as oracle_allowed,
    attempt as oracle_attempt,
    grant as oracle_grant,
    invalidate as oracle_invalidate,
)


@settings(max_examples=200, stateful_step_count=50, deadline=None, derandomize=True)
class DispatcherStateMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.actual = GateState()
        self.expected = OracleState()

    @rule(action=st.sampled_from((*ACTIONS, "unknown_action")))
    def attempt(self, action: str) -> None:
        self.expected, expected_event = oracle_attempt(self.expected, action)
        self.actual, actual_event = attempt_action(self.actual, action)
        assert actual_event["type"] == expected_event

    @rule(offset=st.integers(min_value=-2, max_value=2))
    def approval(self, offset: int) -> None:
        basis = max(0, self.expected.revision + offset)
        self.expected, expected_event = oracle_grant(self.expected, basis)
        self.actual, actual_event = grant_approval(
            self.actual, basis_revision=basis
        )
        assert actual_event["type"] == expected_event

    @rule()
    def invalidate(self) -> None:
        self.expected, expected_event = oracle_invalidate(self.expected)
        self.actual, actual_event = invalidate_evidence(self.actual)
        assert actual_event["type"] == expected_event

    @invariant()
    def states_and_allowed_actions_match(self) -> None:
        validate_state(self.actual)
        assert asdict(self.actual) == asdict(self.expected)
        assert allowed_actions(self.actual) == oracle_allowed(self.expected)


TestDispatcherStateMachine = DispatcherStateMachine.TestCase
