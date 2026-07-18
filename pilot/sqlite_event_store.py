"""Transactional SQLite persistence for the deterministic AMC event engine.

SQLite is used as a local reference adapter. This module does not implement an
external-side-effect outbox or claim suitability for distributed production use.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pilot.event_dispatcher import (
    POLICY_VERSION,
    CommandEnvelope,
    EventEnvelope,
    ProcessingResult,
    ReplayCheckpoint,
    WorkflowEngine,
    build_replay_checkpoint,
    replay_from_checkpoint,
)
from pilot.gate_dispatcher import GateState, validate_state


FAULT_POINTS = frozenset(
    {
        "before_event_insert",
        "after_event_insert_before_commit",
        "after_commit_before_response",
    }
)


class InjectedStoreFault(RuntimeError):
    """Raised by tests at a declared transaction boundary."""


class StoredEventCorruption(ValueError):
    """Raised when persisted workflow metadata or event data is inconsistent."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _event_json(event: EventEnvelope) -> str:
    return _canonical_json(asdict(event))


def _decode_event(raw: str) -> EventEnvelope:
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TypeError("event JSON must decode to an object")
        return EventEnvelope(**value)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise StoredEventCorruption("stored event JSON is malformed") from exc


def _decode_checkpoint(raw: str) -> ReplayCheckpoint:
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise TypeError("checkpoint JSON must decode to an object")
        return ReplayCheckpoint(**value)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise StoredEventCorruption("stored checkpoint JSON is malformed") from exc


class SQLiteWorkflowStore:
    """Append-only event store with transaction-scoped command processing."""

    def __init__(
        self,
        database_path: str | Path,
        workflow_id: str,
        *,
        initial_state: GateState | None = None,
        policy_version: str = POLICY_VERSION,
        timeout_seconds: float = 10.0,
    ) -> None:
        path = Path(database_path)
        if str(path) == ":memory:":
            raise ValueError("use a file path; per-connection :memory: is unsupported")
        if not workflow_id or not isinstance(workflow_id, str):
            raise ValueError("workflow_id must be a non-empty string")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        state = initial_state or GateState()
        validate_state(state)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.database_path = path
        self.workflow_id = workflow_id
        self.initial_state = state
        self.policy_version = policy_version
        self.timeout_seconds = timeout_seconds
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path,
            timeout=self.timeout_seconds,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    policy_version TEXT NOT NULL,
                    initial_state_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    workflow_id TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),
                    event_id TEXT NOT NULL,
                    command_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_hash TEXT NOT NULL,
                    event_json TEXT NOT NULL,
                    PRIMARY KEY (workflow_id, sequence_number),
                    UNIQUE (workflow_id, event_id),
                    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
                );
                CREATE INDEX IF NOT EXISTS events_command_lookup
                    ON events(workflow_id, command_id);
                CREATE TABLE IF NOT EXISTS snapshots (
                    workflow_id TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
                    checkpoint_hash TEXT NOT NULL,
                    checkpoint_json TEXT NOT NULL,
                    PRIMARY KEY (workflow_id, sequence_number),
                    FOREIGN KEY (workflow_id) REFERENCES workflows(workflow_id)
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    outbox_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    event_id TEXT NOT NULL,
                    effect_type TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('pending', 'inflight', 'completed')
                    ),
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    recovery_count INTEGER NOT NULL DEFAULT 0,
                    worker_id TEXT,
                    result_json TEXT,
                    UNIQUE (workflow_id, event_id),
                    FOREIGN KEY (workflow_id, event_id)
                        REFERENCES events(workflow_id, event_id)
                );
                CREATE INDEX IF NOT EXISTS outbox_pending_lookup
                    ON outbox(workflow_id, status, outbox_id);
                """
            )
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT policy_version, initial_state_json FROM workflows "
                    "WHERE workflow_id = ?",
                    (self.workflow_id,),
                ).fetchone()
                expected_initial = _canonical_json(asdict(self.initial_state))
                if row is None:
                    connection.execute(
                        "INSERT INTO workflows "
                        "(workflow_id, policy_version, initial_state_json) VALUES (?, ?, ?)",
                        (self.workflow_id, self.policy_version, expected_initial),
                    )
                elif (
                    row["policy_version"] != self.policy_version
                    or row["initial_state_json"] != expected_initial
                ):
                    raise StoredEventCorruption(
                        "stored workflow metadata does not match requested contract"
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _load_events(
        self, connection: sqlite3.Connection, *, after_sequence: int = 0
    ) -> tuple[EventEnvelope, ...]:
        rows = connection.execute(
            "SELECT sequence_number, event_hash, event_json FROM events "
            "WHERE workflow_id = ? AND sequence_number > ? ORDER BY sequence_number",
            (self.workflow_id, after_sequence),
        ).fetchall()
        events: list[EventEnvelope] = []
        for row in rows:
            event = _decode_event(row["event_json"])
            if event.sequence_number != row["sequence_number"]:
                raise StoredEventCorruption(
                    "stored sequence column disagrees with event envelope"
                )
            if event.event_hash != row["event_hash"]:
                raise StoredEventCorruption(
                    "stored hash column disagrees with event envelope"
                )
            events.append(event)
        return tuple(events)

    def _latest_checkpoint(
        self, connection: sqlite3.Connection
    ) -> ReplayCheckpoint | None:
        row = connection.execute(
            "SELECT sequence_number, checkpoint_hash, checkpoint_json FROM snapshots "
            "WHERE workflow_id = ? ORDER BY sequence_number DESC LIMIT 1",
            (self.workflow_id,),
        ).fetchone()
        if row is None:
            return None
        checkpoint = _decode_checkpoint(row["checkpoint_json"])
        if checkpoint.sequence_number != row["sequence_number"]:
            raise StoredEventCorruption(
                "stored snapshot sequence disagrees with checkpoint"
            )
        if checkpoint.checkpoint_hash != row["checkpoint_hash"]:
            raise StoredEventCorruption(
                "stored snapshot hash column disagrees with checkpoint"
            )
        return checkpoint

    def _restore(self, connection: sqlite3.Connection) -> WorkflowEngine:
        events = self._load_events(connection)
        try:
            return WorkflowEngine.from_events(
                self.workflow_id,
                events,
                initial_state=self.initial_state,
                policy_version=self.policy_version,
            )
        except ValueError as exc:
            raise StoredEventCorruption("stored event stream failed replay") from exc

    @property
    def events(self) -> tuple[EventEnvelope, ...]:
        with self._connect() as connection:
            return self._load_events(connection)

    @property
    def state(self) -> GateState:
        with self._connect() as connection:
            return self._restore(connection).state

    @property
    def latest_checkpoint(self) -> ReplayCheckpoint | None:
        with self._connect() as connection:
            return self._latest_checkpoint(connection)

    @property
    def state_from_latest_checkpoint(self) -> GateState:
        with self._connect() as connection:
            checkpoint = self._latest_checkpoint(connection)
            if checkpoint is None:
                return self._restore(connection).state
            tail = self._load_events(
                connection, after_sequence=checkpoint.sequence_number
            )
            try:
                return replay_from_checkpoint(checkpoint, tail)
            except ValueError as exc:
                raise StoredEventCorruption(
                    "stored checkpoint or event tail failed replay"
                ) from exc

    def create_checkpoint(self) -> ReplayCheckpoint:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            events = self._load_events(connection)
            checkpoint = build_replay_checkpoint(
                self.workflow_id,
                events,
                initial_state=self.initial_state,
                policy_version=self.policy_version,
            )
            connection.execute(
                "INSERT OR REPLACE INTO snapshots "
                "(workflow_id, sequence_number, checkpoint_hash, checkpoint_json) "
                "VALUES (?, ?, ?, ?)",
                (
                    self.workflow_id,
                    checkpoint.sequence_number,
                    checkpoint.checkpoint_hash,
                    _canonical_json(asdict(checkpoint)),
                ),
            )
            connection.commit()
            return checkpoint
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def process(
        self,
        command: CommandEnvelope,
        *,
        fault_point: str | None = None,
    ) -> ProcessingResult:
        if fault_point is not None and fault_point not in FAULT_POINTS:
            raise ValueError("fault_point is not recognized")

        connection = self._connect()
        committed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            engine = self._restore(connection)
            prior_event_count = len(engine.events)
            result = engine.process(command)
            new_events = engine.events[prior_event_count:]
            if len(new_events) > 1:
                raise RuntimeError("one command produced more than one event")

            if new_events:
                event = new_events[0]
                if fault_point == "before_event_insert":
                    raise InjectedStoreFault(fault_point)
                connection.execute(
                    "INSERT INTO events "
                    "(workflow_id, sequence_number, event_id, command_id, "
                    "command_fingerprint, event_type, event_hash, event_json) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.workflow_id,
                        event.sequence_number,
                        event.event_id,
                        event.command_id,
                        event.command_fingerprint,
                        event.event_type,
                        event.event_hash,
                        _event_json(event),
                    ),
                )
                if (
                    event.event_type == "action_accepted"
                    and event.payload.get("action") == "publish"
                ):
                    outbox_payload = {
                        "workflow_id": event.workflow_id,
                        "event_id": event.event_id,
                        "event_hash": event.event_hash,
                        "state_revision": event.state_revision,
                        "action": "publish",
                    }
                    connection.execute(
                        "INSERT INTO outbox "
                        "(outbox_id, workflow_id, event_id, effect_type, "
                        "idempotency_key, payload_json, status) "
                        "VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                        (
                            event.event_id,
                            event.workflow_id,
                            event.event_id,
                            "publish",
                            f"publish:{event.event_hash}",
                            _canonical_json(outbox_payload),
                        ),
                    )
                if fault_point == "after_event_insert_before_commit":
                    raise InjectedStoreFault(fault_point)

            connection.commit()
            committed = True
            if fault_point == "after_commit_before_response":
                raise InjectedStoreFault(fault_point)
            return result
        except Exception:
            if not committed:
                connection.rollback()
            raise
        finally:
            connection.close()
