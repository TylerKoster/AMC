"""In-memory command idempotency and hash-chained replay for the AMC dispatcher.

This module defines deterministic semantics but is not a durable store. Database
transactions, multi-process locking, and an external-side-effect outbox remain
separate implementation requirements.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from threading import RLock
from typing import Any, Iterable, Mapping

from pilot.gate_dispatcher import (
    GateState,
    attempt_action,
    grant_approval,
    invalidate_evidence,
    validate_state,
)


POLICY_VERSION = "amc-dispatcher/0.1"
COMMAND_TYPES = frozenset({"action", "grant_approval", "invalidate_evidence"})


class CommandValidationError(ValueError):
    """Raised when a command envelope is malformed or routed incorrectly."""


class ReplayError(ValueError):
    """Raised when an event stream is incomplete, corrupt, or inconsistent."""


@dataclass(frozen=True)
class CommandEnvelope:
    command_id: str
    workflow_id: str
    expected_revision: int
    command_type: str
    policy_version: str = POLICY_VERSION
    action: str | None = None
    basis_revision: int | None = None
    actor_id: str = "agent"
    authority_class: str = "workflow_agent"


@dataclass(frozen=True)
class EventEnvelope:
    event_id: str
    command_id: str
    command_fingerprint: str
    command_type: str
    expected_revision: int
    actor_id: str
    authority_class: str
    workflow_id: str
    sequence_number: int
    state_revision: int
    policy_version: str
    event_type: str
    payload: Mapping[str, Any]
    state_after: Mapping[str, Any]
    previous_event_hash: str | None
    event_hash: str


@dataclass(frozen=True)
class ProcessingResult:
    event: EventEnvelope
    state: GateState
    duplicate: bool = False


@dataclass(frozen=True)
class ReplayCheckpoint:
    workflow_id: str
    policy_version: str
    sequence_number: int
    state: Mapping[str, Any]
    last_event_hash: str | None
    seen_commands: Mapping[str, str]
    checkpoint_hash: str


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def validate_command(command: CommandEnvelope) -> None:
    if not isinstance(command, CommandEnvelope):
        raise TypeError("command must be a CommandEnvelope")
    for field in (
        "command_id",
        "workflow_id",
        "command_type",
        "policy_version",
        "actor_id",
        "authority_class",
    ):
        value = getattr(command, field)
        if not isinstance(value, str) or not value.strip():
            raise CommandValidationError(f"{field} must be a non-empty string")
    if type(command.expected_revision) is not int or command.expected_revision < 0:
        raise CommandValidationError("expected_revision must be a non-negative integer")
    if command.command_type not in COMMAND_TYPES:
        raise CommandValidationError("command_type is not recognized")

    if command.command_type == "action":
        if not isinstance(command.action, str) or not command.action:
            raise CommandValidationError("action command requires a non-empty action")
        if command.basis_revision is not None:
            raise CommandValidationError("action command cannot contain basis_revision")
    elif command.command_type == "grant_approval":
        if type(command.basis_revision) is not int or command.basis_revision < 0:
            raise CommandValidationError(
                "grant_approval requires a non-negative basis_revision"
            )
        if command.action is not None:
            raise CommandValidationError("grant_approval cannot contain action")
    elif command.action is not None or command.basis_revision is not None:
        raise CommandValidationError(
            "invalidate_evidence cannot contain action or basis_revision"
        )


def command_fingerprint(command: CommandEnvelope) -> str:
    validate_command(command)
    content = asdict(command)
    content.pop("command_id")
    return _digest(content)


def _event_content(event: EventEnvelope) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "command_id": event.command_id,
        "command_fingerprint": event.command_fingerprint,
        "command_type": event.command_type,
        "expected_revision": event.expected_revision,
        "actor_id": event.actor_id,
        "authority_class": event.authority_class,
        "workflow_id": event.workflow_id,
        "sequence_number": event.sequence_number,
        "state_revision": event.state_revision,
        "policy_version": event.policy_version,
        "event_type": event.event_type,
        "payload": dict(event.payload),
        "state_after": dict(event.state_after),
        "previous_event_hash": event.previous_event_hash,
    }


def calculate_event_hash(event: EventEnvelope) -> str:
    return _digest(_event_content(event))


def _checkpoint_content(checkpoint: ReplayCheckpoint) -> dict[str, Any]:
    return {
        "workflow_id": checkpoint.workflow_id,
        "policy_version": checkpoint.policy_version,
        "sequence_number": checkpoint.sequence_number,
        "state": dict(checkpoint.state),
        "last_event_hash": checkpoint.last_event_hash,
        "seen_commands": dict(checkpoint.seen_commands),
    }


def calculate_checkpoint_hash(checkpoint: ReplayCheckpoint) -> str:
    return _digest(_checkpoint_content(checkpoint))


class WorkflowEngine:
    """Serial in-process event engine with idempotent command semantics."""

    def __init__(
        self,
        workflow_id: str,
        *,
        initial_state: GateState | None = None,
        policy_version: str = POLICY_VERSION,
    ) -> None:
        if not isinstance(workflow_id, str) or not workflow_id.strip():
            raise ValueError("workflow_id must be a non-empty string")
        if not isinstance(policy_version, str) or not policy_version.strip():
            raise ValueError("policy_version must be a non-empty string")
        state = initial_state or GateState()
        validate_state(state)
        self.workflow_id = workflow_id
        self.policy_version = policy_version
        self._state = state
        self._events: list[EventEnvelope] = []
        self._processed: dict[str, tuple[str, ProcessingResult]] = {}
        self._collisions: dict[tuple[str, str], ProcessingResult] = {}
        self._lock = RLock()

    @classmethod
    def from_events(
        cls,
        workflow_id: str,
        events: Iterable[EventEnvelope],
        *,
        initial_state: GateState | None = None,
        policy_version: str = POLICY_VERSION,
    ) -> WorkflowEngine:
        """Restore canonical state and idempotency records from verified events."""
        event_stream = tuple(events)
        restored_state = replay_events(
            workflow_id,
            event_stream,
            initial_state=initial_state,
            policy_version=policy_version,
        )
        engine = cls(
            workflow_id,
            initial_state=initial_state,
            policy_version=policy_version,
        )
        engine._events = list(event_stream)
        engine._state = restored_state
        for event in event_stream:
            event_state = _state_from_event(event)
            result = ProcessingResult(event=event, state=event_state)
            if event.event_type == "command_id_collision":
                engine._collisions[
                    (event.command_id, event.command_fingerprint)
                ] = result
            else:
                engine._processed[event.command_id] = (
                    event.command_fingerprint,
                    result,
                )
        return engine

    @property
    def state(self) -> GateState:
        return self._state

    @property
    def events(self) -> tuple[EventEnvelope, ...]:
        return tuple(self._events)

    def _new_event(
        self,
        command: CommandEnvelope,
        fingerprint: str,
        event_type: str,
        payload: Mapping[str, Any],
        state_after: GateState,
    ) -> EventEnvelope:
        sequence = len(self._events) + 1
        previous_hash = self._events[-1].event_hash if self._events else None
        unsigned = EventEnvelope(
            event_id=f"{self.workflow_id}:{sequence}",
            command_id=command.command_id,
            command_fingerprint=fingerprint,
            command_type=command.command_type,
            expected_revision=command.expected_revision,
            actor_id=command.actor_id,
            authority_class=command.authority_class,
            workflow_id=self.workflow_id,
            sequence_number=sequence,
            state_revision=state_after.revision,
            policy_version=self.policy_version,
            event_type=event_type,
            payload=dict(payload),
            state_after=asdict(state_after),
            previous_event_hash=previous_hash,
            event_hash="",
        )
        return EventEnvelope(**{**asdict(unsigned), "event_hash": calculate_event_hash(unsigned)})

    def _record(
        self,
        command: CommandEnvelope,
        fingerprint: str,
        event_type: str,
        payload: Mapping[str, Any],
        state_after: GateState,
        *,
        remember_command: bool = True,
    ) -> ProcessingResult:
        event = self._new_event(
            command, fingerprint, event_type, payload, state_after
        )
        result = ProcessingResult(event=event, state=state_after)
        self._events.append(event)
        self._state = state_after
        if remember_command:
            self._processed[command.command_id] = (fingerprint, result)
        return result

    def process(self, command: CommandEnvelope) -> ProcessingResult:
        validate_command(command)
        if command.workflow_id != self.workflow_id:
            raise CommandValidationError("command workflow_id does not match engine")
        fingerprint = command_fingerprint(command)

        with self._lock:
            prior = self._processed.get(command.command_id)
            if prior is not None:
                prior_fingerprint, prior_result = prior
                if fingerprint == prior_fingerprint:
                    return ProcessingResult(
                        event=prior_result.event,
                        state=prior_result.state,
                        duplicate=True,
                    )
                collision_key = (command.command_id, fingerprint)
                prior_collision = self._collisions.get(collision_key)
                if prior_collision is not None:
                    return ProcessingResult(
                        event=prior_collision.event,
                        state=prior_collision.state,
                        duplicate=True,
                    )
                result = self._record(
                    command,
                    fingerprint,
                    "command_id_collision",
                    {
                        "original_fingerprint": prior_fingerprint,
                        "received_fingerprint": fingerprint,
                    },
                    self._state,
                    remember_command=False,
                )
                self._collisions[collision_key] = result
                return result

            if command.policy_version != self.policy_version:
                return self._record(
                    command,
                    fingerprint,
                    "policy_version_rejected",
                    {
                        "received": command.policy_version,
                        "required": self.policy_version,
                    },
                    self._state,
                )

            if command.expected_revision != self._state.revision:
                return self._record(
                    command,
                    fingerprint,
                    "revision_conflict",
                    {
                        "expected_revision": command.expected_revision,
                        "current_revision": self._state.revision,
                    },
                    self._state,
                )

            if command.command_type == "action":
                new_state, dispatcher_event = attempt_action(
                    self._state, command.action or ""
                )
            elif command.command_type == "grant_approval":
                new_state, dispatcher_event = grant_approval(
                    self._state,
                    basis_revision=command.basis_revision
                    if command.basis_revision is not None
                    else -1,
                )
            else:
                new_state, dispatcher_event = invalidate_evidence(self._state)

            return self._record(
                command,
                fingerprint,
                dispatcher_event["type"],
                dispatcher_event,
                new_state,
            )


def _state_from_event(event: EventEnvelope) -> GateState:
    try:
        state = GateState(**dict(event.state_after))
    except (TypeError, ValueError) as exc:
        raise ReplayError("event contains malformed state_after") from exc
    try:
        validate_state(state)
    except (TypeError, ValueError) as exc:
        raise ReplayError("event contains invalid state_after") from exc
    return state


def replay_events(
    workflow_id: str,
    events: Iterable[EventEnvelope],
    *,
    initial_state: GateState | None = None,
    policy_version: str = POLICY_VERSION,
    starting_sequence: int = 1,
    previous_event_hash: str | None = None,
    prior_seen_commands: Mapping[str, str] | None = None,
) -> GateState:
    """Verify and replay a complete ordered event stream into canonical state."""
    if type(starting_sequence) is not int or starting_sequence < 1:
        raise ValueError("starting_sequence must be a positive integer")
    state = initial_state or GateState()
    validate_state(state)
    previous_hash = previous_event_hash
    seen_commands = dict(prior_seen_commands or {})

    for expected_sequence, event in enumerate(events, start=starting_sequence):
        if not isinstance(event, EventEnvelope):
            raise ReplayError("event stream contains a non-EventEnvelope value")
        if event.workflow_id != workflow_id:
            raise ReplayError("event workflow_id mismatch")
        if event.policy_version != policy_version:
            raise ReplayError("unsupported event policy version")
        if event.sequence_number != expected_sequence:
            raise ReplayError("event sequence is missing, duplicated, or reordered")
        if event.event_id != f"{workflow_id}:{expected_sequence}":
            raise ReplayError("event_id does not match canonical sequence identity")
        if event.previous_event_hash != previous_hash:
            raise ReplayError("event hash chain is broken")
        if event.event_hash != calculate_event_hash(event):
            raise ReplayError("event content hash is invalid")
        if not event.command_id or not event.actor_id or not event.authority_class:
            raise ReplayError("event command identity or authority is missing")
        if event.command_type not in COMMAND_TYPES:
            raise ReplayError("event command_type is not recognized")
        if type(event.expected_revision) is not int or event.expected_revision < 0:
            raise ReplayError("event expected_revision is invalid")
        if (
            len(event.command_fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in event.command_fingerprint)
        ):
            raise ReplayError("event command fingerprint is invalid")

        if event.event_type == "command_id_collision":
            original = seen_commands.get(event.command_id)
            if original is None:
                raise ReplayError("command collision has no original command")
            if event.payload.get("original_fingerprint") != original:
                raise ReplayError("command collision identifies the wrong original")
            if event.payload.get("received_fingerprint") != event.command_fingerprint:
                raise ReplayError("command collision identifies the wrong received command")
            if event.command_fingerprint == original:
                raise ReplayError("command collision fingerprints are identical")
        else:
            if event.command_id in seen_commands:
                raise ReplayError("duplicate command event is not a collision")
            seen_commands[event.command_id] = event.command_fingerprint

        if event.event_type in {"action_accepted", "action_rejected"}:
            if event.command_type != "action":
                raise ReplayError("action event has the wrong command_type")
            if event.expected_revision != state.revision:
                raise ReplayError("action event expected_revision is stale or future")
            action = event.payload.get("action")
            if not isinstance(action, str):
                raise ReplayError("action event has no valid action")
            new_state, generated = attempt_action(state, action)
            if generated["type"] != event.event_type:
                raise ReplayError("action event contradicts dispatcher state")
            if generated != dict(event.payload):
                raise ReplayError("action event payload contradicts dispatcher result")
        elif event.event_type in {"approval_granted", "approval_rejected"}:
            if event.command_type != "grant_approval":
                raise ReplayError("approval event has the wrong command_type")
            if event.expected_revision != state.revision:
                raise ReplayError("approval event expected_revision is stale or future")
            basis = event.payload.get("basis_revision")
            if type(basis) is not int or basis < 0:
                raise ReplayError("approval event has no valid basis revision")
            new_state, generated = grant_approval(state, basis_revision=basis)
            if generated["type"] != event.event_type:
                raise ReplayError("approval event contradicts dispatcher state")
            if generated != dict(event.payload):
                raise ReplayError("approval event payload contradicts dispatcher result")
        elif event.event_type == "evidence_invalidated":
            if event.command_type != "invalidate_evidence":
                raise ReplayError("invalidation event has the wrong command_type")
            if event.expected_revision != state.revision:
                raise ReplayError("invalidation expected_revision is stale or future")
            new_state, generated = invalidate_evidence(state)
            if generated != dict(event.payload):
                raise ReplayError("invalidation payload contradicts dispatcher result")
        elif event.event_type == "revision_conflict":
            if event.payload.get("expected_revision") != event.expected_revision:
                raise ReplayError("revision conflict payload has the wrong expectation")
            if event.payload.get("current_revision") != state.revision:
                raise ReplayError("revision conflict payload has the wrong current revision")
            if event.expected_revision == state.revision:
                raise ReplayError("revision conflict records matching revisions")
            new_state = state
        elif event.event_type == "policy_version_rejected":
            if event.payload.get("required") != policy_version:
                raise ReplayError("policy rejection records the wrong required version")
            received = event.payload.get("received")
            if not isinstance(received, str) or received == policy_version:
                raise ReplayError("policy rejection does not contain a mismatched version")
            new_state = state
        elif event.event_type == "command_id_collision":
            new_state = state
        else:
            raise ReplayError(f"unsupported event type: {event.event_type}")

        recorded_state = _state_from_event(event)
        if new_state != recorded_state:
            raise ReplayError("event state_after contradicts replayed transition")
        if event.state_revision != new_state.revision:
            raise ReplayError("event state_revision does not match state_after")
        state = new_state
        previous_hash = event.event_hash

    return state


def build_replay_checkpoint(
    workflow_id: str,
    events: Iterable[EventEnvelope],
    *,
    initial_state: GateState | None = None,
    policy_version: str = POLICY_VERSION,
) -> ReplayCheckpoint:
    """Build a hash-protected replay checkpoint from a verified full stream."""
    event_stream = tuple(events)
    state = replay_events(
        workflow_id,
        event_stream,
        initial_state=initial_state,
        policy_version=policy_version,
    )
    seen_commands: dict[str, str] = {}
    for event in event_stream:
        if event.event_type != "command_id_collision":
            seen_commands[event.command_id] = event.command_fingerprint
    unsigned = ReplayCheckpoint(
        workflow_id=workflow_id,
        policy_version=policy_version,
        sequence_number=len(event_stream),
        state=asdict(state),
        last_event_hash=event_stream[-1].event_hash if event_stream else None,
        seen_commands=seen_commands,
        checkpoint_hash="",
    )
    return ReplayCheckpoint(
        **{
            **asdict(unsigned),
            "checkpoint_hash": calculate_checkpoint_hash(unsigned),
        }
    )


def replay_from_checkpoint(
    checkpoint: ReplayCheckpoint,
    tail_events: Iterable[EventEnvelope],
) -> GateState:
    """Verify a checkpoint and replay only events after its sequence."""
    if not isinstance(checkpoint, ReplayCheckpoint):
        raise TypeError("checkpoint must be a ReplayCheckpoint")
    if checkpoint.checkpoint_hash != calculate_checkpoint_hash(checkpoint):
        raise ReplayError("checkpoint content hash is invalid")
    if type(checkpoint.sequence_number) is not int or checkpoint.sequence_number < 0:
        raise ReplayError("checkpoint sequence_number is invalid")
    try:
        state = GateState(**dict(checkpoint.state))
        validate_state(state)
    except (TypeError, ValueError) as exc:
        raise ReplayError("checkpoint state is invalid") from exc
    return replay_events(
        checkpoint.workflow_id,
        tail_events,
        initial_state=state,
        policy_version=checkpoint.policy_version,
        starting_sequence=checkpoint.sequence_number + 1,
        previous_event_hash=checkpoint.last_event_hash,
        prior_seen_commands=checkpoint.seen_commands,
    )
