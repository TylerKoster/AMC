"""Transactional, crash-point, and cross-connection SQLite adapter tests."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

import pytest

from pilot.event_dispatcher import CommandEnvelope, replay_events
from pilot.gate_dispatcher import GateState
from pilot.sqlite_event_store import (
    InjectedStoreFault,
    SQLiteWorkflowStore,
    StoredEventCorruption,
)


WORKFLOW_ID = "sqlite-workflow-001"


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


def test_full_workflow_persists_and_replays_after_new_store_instance(
    tmp_path: Path,
) -> None:
    database = tmp_path / "events.sqlite3"
    store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    commands = (
        action("cmd-1", 0, "refresh_evidence"),
        action("cmd-2", 1, "verify_license"),
        action("cmd-3", 2, "form_recommendation"),
        action("cmd-4", 3, "request_publication_approval"),
        grant("cmd-5", 3, 3),
        action("cmd-6", 3, "publish"),
    )
    for command in commands:
        store.process(command)

    restarted = SQLiteWorkflowStore(database, WORKFLOW_ID)
    assert restarted.state.published
    assert len(restarted.events) == 6
    assert replay_events(WORKFLOW_ID, restarted.events) == restarted.state


def test_duplicate_after_restart_returns_prior_result_without_new_event(
    tmp_path: Path,
) -> None:
    database = tmp_path / "events.sqlite3"
    command = action("cmd-restart", 0, "refresh_evidence")
    first_store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    first = first_store.process(command)

    restarted = SQLiteWorkflowStore(database, WORKFLOW_ID)
    duplicate = restarted.process(command)
    assert duplicate.duplicate
    assert duplicate.event == first.event
    assert len(restarted.events) == 1
    assert restarted.state == GateState(evidence_current=True, revision=1)


def test_sqlite_checkpoint_plus_tail_matches_full_replay(tmp_path: Path) -> None:
    database = tmp_path / "snapshot.sqlite3"
    store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    for command in (
        action("cmd-1", 0, "refresh_evidence"),
        action("cmd-2", 1, "verify_license"),
        action("cmd-3", 2, "form_recommendation"),
        action("cmd-4", 3, "request_publication_approval"),
    ):
        store.process(command)
    checkpoint = store.create_checkpoint()
    store.process(grant("cmd-5", 3, 3))
    store.process(action("cmd-6", 3, "publish"))

    assert checkpoint.sequence_number == 4
    assert store.latest_checkpoint == checkpoint
    assert store.state_from_latest_checkpoint == store.state
    assert store.state_from_latest_checkpoint.published


def test_sqlite_checkpoint_preserves_precheckpoint_collision_identity(
    tmp_path: Path,
) -> None:
    database = tmp_path / "snapshot-collision.sqlite3"
    store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    store.process(action("cmd-before-snapshot", 0, "refresh_evidence"))
    store.create_checkpoint()
    store.process(action("cmd-before-snapshot", 0, "publish"))
    assert store.state_from_latest_checkpoint == store.state


def test_corrupt_checkpoint_hash_column_is_detected(tmp_path: Path) -> None:
    database = tmp_path / "corrupt-snapshot.sqlite3"
    store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    store.process(action("cmd-1", 0, "refresh_evidence"))
    store.create_checkpoint()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE snapshots SET checkpoint_hash = ? WHERE workflow_id = ?",
            ("0" * 64, WORKFLOW_ID),
        )
        connection.commit()
    with pytest.raises(StoredEventCorruption, match="snapshot hash"):
        _ = store.state_from_latest_checkpoint


@pytest.mark.parametrize(
    "fault_point", ("before_event_insert", "after_event_insert_before_commit")
)
def test_precommit_fault_rolls_back_state_event_and_idempotency(
    tmp_path: Path, fault_point: str
) -> None:
    database = tmp_path / f"{fault_point}.sqlite3"
    store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    command = action("cmd-fault", 0, "refresh_evidence")

    with pytest.raises(InjectedStoreFault, match=fault_point):
        store.process(command, fault_point=fault_point)
    assert store.events == ()
    assert store.state == GateState()

    retry = store.process(command)
    assert not retry.duplicate
    assert retry.event.event_type == "action_accepted"
    assert len(store.events) == 1


def test_lost_response_after_commit_is_recovered_by_idempotent_retry(
    tmp_path: Path,
) -> None:
    database = tmp_path / "committed.sqlite3"
    store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    command = action("cmd-committed", 0, "refresh_evidence")

    with pytest.raises(InjectedStoreFault, match="after_commit_before_response"):
        store.process(command, fault_point="after_commit_before_response")
    assert len(store.events) == 1
    assert store.state == GateState(evidence_current=True, revision=1)

    retry = SQLiteWorkflowStore(database, WORKFLOW_ID).process(command)
    assert retry.duplicate
    assert len(store.events) == 1


def test_two_store_instances_serialize_same_revision_commands(
    tmp_path: Path,
) -> None:
    database = tmp_path / "concurrent.sqlite3"
    first_store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    second_store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    work = (
        (first_store, action("cmd-concurrent-a", 0, "refresh_evidence")),
        (second_store, action("cmd-concurrent-b", 0, "refresh_evidence")),
    )

    def run(item: tuple[SQLiteWorkflowStore, CommandEnvelope]):
        store, command = item
        return store.process(command)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, work))

    assert sorted(result.event.event_type for result in results) == [
        "action_accepted",
        "revision_conflict",
    ]
    verifier = SQLiteWorkflowStore(database, WORKFLOW_ID)
    assert verifier.state == GateState(evidence_current=True, revision=1)
    assert len(verifier.events) == 2
    assert replay_events(WORKFLOW_ID, verifier.events) == verifier.state


def test_collision_and_collision_retry_survive_restart(tmp_path: Path) -> None:
    database = tmp_path / "collision.sqlite3"
    store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    store.process(action("cmd-collision", 0, "refresh_evidence"))
    changed = action("cmd-collision", 0, "publish")
    collision = store.process(changed)
    assert collision.event.event_type == "command_id_collision"

    restarted = SQLiteWorkflowStore(database, WORKFLOW_ID)
    retry = restarted.process(changed)
    assert retry.duplicate
    assert retry.event == collision.event
    assert len(restarted.events) == 2


def test_wrong_workflow_command_rolls_back_without_event(tmp_path: Path) -> None:
    database = tmp_path / "wrong-workflow.sqlite3"
    store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    command = replace(
        action("cmd-wrong", 0, "refresh_evidence"),
        workflow_id="different-workflow",
    )
    with pytest.raises(ValueError, match="workflow_id"):
        store.process(command)
    assert store.events == ()
    assert store.state == GateState()


def test_corrupt_hash_column_is_detected_before_replay(tmp_path: Path) -> None:
    database = tmp_path / "corrupt.sqlite3"
    store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    store.process(action("cmd-corrupt", 0, "refresh_evidence"))
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE events SET event_hash = ? WHERE workflow_id = ?",
            ("0" * 64, WORKFLOW_ID),
        )
        connection.commit()
    with pytest.raises(StoredEventCorruption, match="hash column"):
        _ = store.events


def test_corrupt_event_json_is_detected(tmp_path: Path) -> None:
    database = tmp_path / "corrupt-json.sqlite3"
    store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    store.process(action("cmd-corrupt", 0, "refresh_evidence"))
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE events SET event_json = ? WHERE workflow_id = ?",
            ("{not-json", WORKFLOW_ID),
        )
        connection.commit()
    with pytest.raises(StoredEventCorruption, match="malformed"):
        _ = store.state


def test_existing_workflow_rejects_changed_initial_contract(tmp_path: Path) -> None:
    database = tmp_path / "metadata.sqlite3"
    SQLiteWorkflowStore(database, WORKFLOW_ID)
    with pytest.raises(StoredEventCorruption, match="metadata"):
        SQLiteWorkflowStore(
            database,
            WORKFLOW_ID,
            initial_state=GateState(evidence_current=True, revision=1),
        )


def test_unknown_fault_point_is_rejected_before_transaction(tmp_path: Path) -> None:
    store = SQLiteWorkflowStore(tmp_path / "fault.sqlite3", WORKFLOW_ID)
    with pytest.raises(ValueError, match="fault_point"):
        store.process(
            action("cmd-fault", 0, "refresh_evidence"), fault_point="unknown"
        )
    assert store.events == ()


def test_memory_database_is_rejected_because_connections_are_separate() -> None:
    with pytest.raises(ValueError, match="file path"):
        SQLiteWorkflowStore(":memory:", WORKFLOW_ID)
