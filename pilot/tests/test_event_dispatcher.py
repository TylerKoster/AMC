"""Replay, idempotency, revision, and conflict tests for the event engine."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace

import pytest

from pilot.event_dispatcher import (
    POLICY_VERSION,
    CommandEnvelope,
    CommandValidationError,
    ReplayError,
    WorkflowEngine,
    build_replay_checkpoint,
    calculate_event_hash,
    replay_from_checkpoint,
    replay_events,
    validate_command,
)
from pilot.gate_dispatcher import GateState


WORKFLOW_ID = "workflow-test-001"


def action(command_id: str, revision: int, value: str) -> CommandEnvelope:
    return CommandEnvelope(
        command_id=command_id,
        workflow_id=WORKFLOW_ID,
        expected_revision=revision,
        command_type="action",
        action=value,
    )


def grant(command_id: str, revision: int, basis: int) -> CommandEnvelope:
    return CommandEnvelope(
        command_id=command_id,
        workflow_id=WORKFLOW_ID,
        expected_revision=revision,
        command_type="grant_approval",
        basis_revision=basis,
        authority_class="human_approver",
    )


def invalidate(command_id: str, revision: int) -> CommandEnvelope:
    return CommandEnvelope(
        command_id=command_id,
        workflow_id=WORKFLOW_ID,
        expected_revision=revision,
        command_type="invalidate_evidence",
        authority_class="evidence_monitor",
    )


def complete_workflow(engine: WorkflowEngine) -> None:
    commands = (
        action("cmd-1", 0, "refresh_evidence"),
        action("cmd-2", 1, "verify_license"),
        action("cmd-3", 2, "form_recommendation"),
        action("cmd-4", 3, "request_publication_approval"),
        grant("cmd-5", 3, 3),
        action("cmd-6", 3, "publish"),
    )
    for command in commands:
        engine.process(command)


def test_complete_event_stream_replays_to_identical_state() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    complete_workflow(engine)
    assert engine.state.published
    assert len(engine.events) == 6
    assert replay_events(WORKFLOW_ID, engine.events) == engine.state
    for index, event in enumerate(engine.events):
        assert event.sequence_number == index + 1
        assert event.event_hash == calculate_event_hash(event)
        expected_previous = engine.events[index - 1].event_hash if index else None
        assert event.previous_event_hash == expected_previous


def test_checkpoint_plus_tail_replays_to_same_state_as_full_stream() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    complete_workflow(engine)
    checkpoint = build_replay_checkpoint(WORKFLOW_ID, engine.events[:4])
    from_checkpoint = replay_from_checkpoint(checkpoint, engine.events[4:])
    assert checkpoint.sequence_number == 4
    assert from_checkpoint == replay_events(WORKFLOW_ID, engine.events)
    assert from_checkpoint == engine.state


def test_checkpoint_preserves_command_history_needed_by_later_collision() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    engine.process(action("cmd-before-snapshot", 0, "refresh_evidence"))
    checkpoint = build_replay_checkpoint(WORKFLOW_ID, engine.events)
    engine.process(action("cmd-before-snapshot", 0, "publish"))
    assert replay_from_checkpoint(checkpoint, engine.events[1:]) == engine.state


def test_checkpoint_tampering_is_rejected() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    engine.process(action("cmd-1", 0, "refresh_evidence"))
    checkpoint = build_replay_checkpoint(WORKFLOW_ID, engine.events)
    corrupted = replace(
        checkpoint,
        state=asdict(GateState()),
    )
    with pytest.raises(ReplayError, match="checkpoint content hash"):
        replay_from_checkpoint(corrupted, ())


def test_identical_duplicate_returns_original_result_without_new_event() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    command = action("cmd-duplicate", 0, "refresh_evidence")
    first = engine.process(command)
    second = engine.process(command)
    assert not first.duplicate
    assert second.duplicate
    assert second.event == first.event
    assert second.state == first.state
    assert len(engine.events) == 1
    assert engine.state.revision == 1


def test_verified_restart_restores_command_idempotency_and_sequence() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    first_command = action("cmd-restart-1", 0, "refresh_evidence")
    first = engine.process(first_command)
    restored = WorkflowEngine.from_events(WORKFLOW_ID, engine.events)

    duplicate = restored.process(first_command)
    assert duplicate.duplicate
    assert duplicate.event == first.event
    assert len(restored.events) == 1
    assert restored.state == GateState(evidence_current=True, revision=1)

    continued = restored.process(action("cmd-restart-2", 1, "verify_license"))
    assert continued.event.sequence_number == 2
    assert continued.event.previous_event_hash == first.event.event_hash
    assert replay_events(WORKFLOW_ID, restored.events) == restored.state


def test_same_command_id_with_changed_payload_is_audited_and_not_executed() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    engine.process(action("cmd-collision", 0, "refresh_evidence"))
    changed = action("cmd-collision", 0, "publish")
    collision = engine.process(changed)
    assert collision.event.event_type == "command_id_collision"
    assert engine.state == GateState(evidence_current=True, revision=1)
    assert len(engine.events) == 2

    repeated_collision = engine.process(changed)
    assert repeated_collision.duplicate
    assert repeated_collision.event == collision.event
    assert len(engine.events) == 2
    assert replay_events(WORKFLOW_ID, engine.events) == engine.state


def test_verified_restart_restores_collision_idempotency() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    engine.process(action("cmd-collision-restart", 0, "refresh_evidence"))
    changed = action("cmd-collision-restart", 0, "publish")
    collision = engine.process(changed)

    restored = WorkflowEngine.from_events(WORKFLOW_ID, engine.events)
    repeated = restored.process(changed)
    assert repeated.duplicate
    assert repeated.event == collision.event
    assert len(restored.events) == 2
    assert restored.state == GateState(evidence_current=True, revision=1)


@pytest.mark.parametrize("expected_revision", (0, 2))
def test_stale_and_future_revision_conflicts_do_not_change_state(
    expected_revision: int,
) -> None:
    engine = WorkflowEngine(
        WORKFLOW_ID, initial_state=GateState(evidence_current=True, revision=1)
    )
    result = engine.process(
        action(f"cmd-revision-{expected_revision}", expected_revision, "verify_license")
    )
    assert result.event.event_type == "revision_conflict"
    assert engine.state == GateState(evidence_current=True, revision=1)
    assert replay_events(
        WORKFLOW_ID,
        engine.events,
        initial_state=GateState(evidence_current=True, revision=1),
    ) == engine.state


def test_delayed_approval_after_invalidation_is_rejected_as_stale() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    for command in (
        action("cmd-a", 0, "refresh_evidence"),
        action("cmd-b", 1, "verify_license"),
        action("cmd-c", 2, "form_recommendation"),
        action("cmd-d", 3, "request_publication_approval"),
    ):
        engine.process(command)
    engine.process(invalidate("cmd-invalidate", 3))
    delayed = engine.process(grant("cmd-delayed", 3, 3))
    assert delayed.event.event_type == "revision_conflict"
    assert engine.state == GateState(revision=4)
    assert replay_events(WORKFLOW_ID, engine.events) == engine.state


def test_concurrent_same_revision_commands_serialize_to_one_transition() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    commands = (
        action("cmd-concurrent-a", 0, "refresh_evidence"),
        action("cmd-concurrent-b", 0, "refresh_evidence"),
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(engine.process, commands))
    assert sorted(result.event.event_type for result in results) == [
        "action_accepted",
        "revision_conflict",
    ]
    assert engine.state == GateState(evidence_current=True, revision=1)
    assert len(engine.events) == 2
    assert replay_events(WORKFLOW_ID, engine.events) == engine.state


def test_wrong_policy_is_recorded_without_state_change_and_is_idempotent() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    command = replace(
        action("cmd-policy", 0, "refresh_evidence"),
        policy_version="amc-dispatcher/9.9",
    )
    first = engine.process(command)
    second = engine.process(command)
    assert first.event.event_type == "policy_version_rejected"
    assert second.duplicate
    assert engine.state == GateState()
    assert len(engine.events) == 1
    assert replay_events(WORKFLOW_ID, engine.events) == GateState()


def test_unknown_action_is_recorded_as_dispatcher_rejection() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    result = engine.process(action("cmd-unknown", 0, "launch_rocket"))
    assert result.event.event_type == "action_rejected"
    assert result.event.payload["reason"] == "unsupported_action"
    assert engine.state == GateState()
    assert replay_events(WORKFLOW_ID, engine.events) == engine.state


def test_replay_rejects_missing_reordered_and_content_corruption() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    engine.process(action("cmd-1", 0, "refresh_evidence"))
    engine.process(action("cmd-2", 1, "verify_license"))
    events = engine.events

    with pytest.raises(ReplayError, match="sequence"):
        replay_events(WORKFLOW_ID, events[1:])
    with pytest.raises(ReplayError, match="sequence"):
        replay_events(WORKFLOW_ID, tuple(reversed(events)))

    corrupted = replace(events[0], payload={**events[0].payload, "action": "publish"})
    with pytest.raises(ReplayError, match="content hash"):
        replay_events(WORKFLOW_ID, (corrupted,))


def test_replay_rejects_rehashed_but_semantically_false_state() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    original = engine.process(action("cmd-1", 0, "refresh_evidence")).event
    false_state = asdict(GateState(revision=1))
    unsigned = replace(original, state_after=false_state, event_hash="")
    corrupted = replace(unsigned, event_hash=calculate_event_hash(unsigned))
    with pytest.raises(ReplayError, match="contradicts replayed transition"):
        replay_events(WORKFLOW_ID, (corrupted,))


def test_replay_rejects_rehashed_false_dispatcher_payload() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    original = engine.process(action("cmd-1", 0, "refresh_evidence")).event
    false_payload = {**original.payload, "revision": 999}
    unsigned = replace(original, payload=false_payload, event_hash="")
    corrupted = replace(unsigned, event_hash=calculate_event_hash(unsigned))
    with pytest.raises(ReplayError, match="payload contradicts"):
        replay_events(WORKFLOW_ID, (corrupted,))


def test_replay_rejects_rehashed_missing_authority() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    original = engine.process(action("cmd-1", 0, "refresh_evidence")).event
    unsigned = replace(original, authority_class="", event_hash="")
    corrupted = replace(unsigned, event_hash=calculate_event_hash(unsigned))
    with pytest.raises(ReplayError, match="authority is missing"):
        replay_events(WORKFLOW_ID, (corrupted,))


def test_replay_rejects_duplicate_non_collision_command_event() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    first = engine.process(action("cmd-1", 0, "refresh_evidence")).event
    unsigned = replace(
        first,
        event_id=f"{WORKFLOW_ID}:2",
        sequence_number=2,
        previous_event_hash=first.event_hash,
        event_hash="",
    )
    duplicate = replace(unsigned, event_hash=calculate_event_hash(unsigned))
    with pytest.raises(ReplayError, match="duplicate command"):
        replay_events(WORKFLOW_ID, (first, duplicate))


@pytest.mark.parametrize(
    "command",
    (
        CommandEnvelope("", WORKFLOW_ID, 0, "action", action="refresh_evidence"),
        CommandEnvelope("x", "", 0, "action", action="refresh_evidence"),
        CommandEnvelope("x", WORKFLOW_ID, -1, "action", action="refresh_evidence"),
        CommandEnvelope("x", WORKFLOW_ID, 0, "unknown"),
        CommandEnvelope("x", WORKFLOW_ID, 0, "action"),
        CommandEnvelope(
            "x", WORKFLOW_ID, 0, "action", action="refresh_evidence", basis_revision=0
        ),
        CommandEnvelope("x", WORKFLOW_ID, 0, "grant_approval"),
        CommandEnvelope(
            "x", WORKFLOW_ID, 0, "invalidate_evidence", action="publish"
        ),
    ),
)
def test_malformed_commands_are_rejected_before_event_creation(
    command: CommandEnvelope,
) -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    with pytest.raises(CommandValidationError):
        engine.process(command)
    assert engine.events == ()
    assert engine.state == GateState()


def test_wrong_workflow_is_rejected_before_event_creation() -> None:
    engine = WorkflowEngine(WORKFLOW_ID)
    command = replace(
        action("cmd-wrong-workflow", 0, "refresh_evidence"),
        workflow_id="different-workflow",
    )
    with pytest.raises(CommandValidationError, match="workflow_id"):
        engine.process(command)
    assert engine.events == ()


def test_command_validator_rejects_boolean_revision() -> None:
    command = replace(action("cmd-bool", 0, "refresh_evidence"), expected_revision=True)
    with pytest.raises(CommandValidationError):
        validate_command(command)


def test_policy_constant_is_versioned() -> None:
    assert POLICY_VERSION == "amc-dispatcher/0.1"
