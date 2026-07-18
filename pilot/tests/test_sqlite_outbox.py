"""Transactional outbox and idempotent external-effect failure tests."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from pilot.event_dispatcher import CommandEnvelope
from pilot.gate_dispatcher import GateState
from pilot.sqlite_event_store import InjectedStoreFault, SQLiteWorkflowStore
from pilot.sqlite_outbox import (
    ExternalEffectResponseLost,
    ExternalIdempotencyCollision,
    FakeIdempotentExecutor,
    FakeNonIdempotentExecutor,
    InjectedDeliveryFault,
    OutboxStateError,
    SQLiteOutboxWorker,
)


WORKFLOW_ID = "outbox-workflow-001"


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


def prepare_approved_store(database: Path) -> SQLiteWorkflowStore:
    store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    for command in (
        action("cmd-1", 0, "refresh_evidence"),
        action("cmd-2", 1, "verify_license"),
        action("cmd-3", 2, "form_recommendation"),
        action("cmd-4", 3, "request_publication_approval"),
        grant("cmd-5", 3, 3),
    ):
        store.process(command)
    return store


def prepare_published_store(
    database: Path,
) -> tuple[SQLiteWorkflowStore, SQLiteOutboxWorker]:
    store = prepare_approved_store(database)
    store.process(action("cmd-6", 3, "publish"))
    return store, SQLiteOutboxWorker(database, WORKFLOW_ID)


def test_publish_event_and_outbox_row_commit_together(tmp_path: Path) -> None:
    database = tmp_path / "outbox.sqlite3"
    store, outbox = prepare_published_store(database)
    items = outbox.items
    assert store.state.published
    assert len(store.events) == 6
    assert len(items) == 1
    assert items[0].event_id == store.events[-1].event_id
    assert items[0].effect_type == "publish"
    assert items[0].status == "pending"
    assert items[0].payload["event_hash"] == store.events[-1].event_hash


def test_precommit_publish_fault_rolls_back_event_and_outbox(tmp_path: Path) -> None:
    database = tmp_path / "outbox-rollback.sqlite3"
    store = prepare_approved_store(database)
    command = action("cmd-6", 3, "publish")
    with pytest.raises(InjectedStoreFault, match="after_event_insert_before_commit"):
        store.process(command, fault_point="after_event_insert_before_commit")

    outbox = SQLiteOutboxWorker(database, WORKFLOW_ID)
    assert len(store.events) == 5
    assert not store.state.published
    assert store.state.approval_status == "granted"
    assert outbox.items == ()

    store.process(command)
    assert store.state.published
    assert len(outbox.items) == 1


def test_successful_delivery_completes_once(tmp_path: Path) -> None:
    database = tmp_path / "outbox-success.sqlite3"
    _, outbox = prepare_published_store(database)
    executor = FakeIdempotentExecutor()
    result = outbox.deliver_one(executor, worker_id="worker-1")
    assert result is not None
    assert result.item.status == "completed"
    assert not result.external_result.duplicate
    assert executor.call_count == 1
    assert executor.physical_effect_count == 1
    assert outbox.deliver_one(executor, worker_id="worker-1") is None


def test_fault_after_claim_before_send_recovers_without_prior_effect(
    tmp_path: Path,
) -> None:
    database = tmp_path / "outbox-before-send.sqlite3"
    _, outbox = prepare_published_store(database)
    executor = FakeIdempotentExecutor()
    with pytest.raises(InjectedDeliveryFault, match="after_claim_before_send"):
        outbox.deliver_one(
            executor,
            worker_id="worker-1",
            fault_point="after_claim_before_send",
        )
    assert executor.physical_effect_count == 0
    assert outbox.items[0].status == "inflight"
    assert outbox.recover_inflight(worker_id="worker-1") == 1

    result = outbox.deliver_one(executor, worker_id="worker-2")
    assert result is not None
    assert result.item.attempt_count == 2
    assert result.item.recovery_count == 1
    assert executor.physical_effect_count == 1


def test_effect_applied_but_response_lost_retries_without_duplicate_effect(
    tmp_path: Path,
) -> None:
    database = tmp_path / "outbox-response-lost.sqlite3"
    _, outbox = prepare_published_store(database)
    executor = FakeIdempotentExecutor()
    executor.lose_next_response()
    with pytest.raises(ExternalEffectResponseLost):
        outbox.deliver_one(executor, worker_id="worker-1")
    assert executor.physical_effect_count == 1
    assert outbox.items[0].status == "inflight"
    assert outbox.recover_inflight(worker_id="worker-1") == 1

    result = outbox.deliver_one(executor, worker_id="worker-2")
    assert result is not None
    assert result.external_result.duplicate
    assert result.item.status == "completed"
    assert executor.call_count == 2
    assert executor.physical_effect_count == 1


def test_non_idempotent_provider_duplicates_effect_after_lost_response(
    tmp_path: Path,
) -> None:
    database = tmp_path / "outbox-non-idempotent.sqlite3"
    _, outbox = prepare_published_store(database)
    executor = FakeNonIdempotentExecutor()
    executor.lose_next_response()
    with pytest.raises(ExternalEffectResponseLost):
        outbox.deliver_one(executor, worker_id="worker-1")
    assert executor.physical_effect_count == 1
    outbox.recover_inflight(worker_id="worker-1")

    result = outbox.deliver_one(executor, worker_id="worker-2")
    assert result is not None
    assert executor.call_count == 2
    assert executor.physical_effect_count == 2
    assert outbox.items[0].status == "completed"


def test_ack_received_but_completion_lost_retries_idempotently(
    tmp_path: Path,
) -> None:
    database = tmp_path / "outbox-ack-lost.sqlite3"
    _, outbox = prepare_published_store(database)
    executor = FakeIdempotentExecutor()
    with pytest.raises(InjectedDeliveryFault, match="after_ack_before_completion"):
        outbox.deliver_one(
            executor,
            worker_id="worker-1",
            fault_point="after_ack_before_completion",
        )
    assert executor.physical_effect_count == 1
    assert outbox.items[0].status == "inflight"
    outbox.recover_inflight(worker_id="worker-1")

    result = outbox.deliver_one(executor, worker_id="worker-2")
    assert result is not None and result.external_result.duplicate
    assert executor.physical_effect_count == 1
    assert outbox.items[0].status == "completed"


def test_completion_committed_but_worker_response_lost_does_not_redeliver(
    tmp_path: Path,
) -> None:
    database = tmp_path / "outbox-completion-lost.sqlite3"
    _, outbox = prepare_published_store(database)
    executor = FakeIdempotentExecutor()
    with pytest.raises(InjectedDeliveryFault, match="after_completion_before_response"):
        outbox.deliver_one(
            executor,
            worker_id="worker-1",
            fault_point="after_completion_before_response",
        )
    assert outbox.items[0].status == "completed"
    assert executor.physical_effect_count == 1
    assert outbox.deliver_one(executor, worker_id="worker-2") is None


def test_two_workers_claim_one_pending_effect_once(tmp_path: Path) -> None:
    database = tmp_path / "outbox-workers.sqlite3"
    _, first_worker = prepare_published_store(database)
    second_worker = SQLiteOutboxWorker(database, WORKFLOW_ID)
    executor = FakeIdempotentExecutor()

    def deliver(worker_data: tuple[SQLiteOutboxWorker, str]):
        worker, worker_id = worker_data
        return worker.deliver_one(executor, worker_id=worker_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                deliver,
                ((first_worker, "worker-1"), (second_worker, "worker-2")),
            )
        )
    assert sum(result is not None for result in results) == 1
    assert executor.call_count == 1
    assert executor.physical_effect_count == 1
    assert first_worker.items[0].status == "completed"


def test_fake_executor_rejects_changed_payload_for_same_key() -> None:
    executor = FakeIdempotentExecutor()
    executor.execute(
        idempotency_key="same-key",
        effect_type="publish",
        payload={"revision": 1},
    )
    with pytest.raises(ExternalIdempotencyCollision):
        executor.execute(
            idempotency_key="same-key",
            effect_type="publish",
            payload={"revision": 2},
        )
    assert executor.physical_effect_count == 1


def test_malformed_outbox_payload_stops_delivery(tmp_path: Path) -> None:
    database = tmp_path / "outbox-corrupt.sqlite3"
    _, outbox = prepare_published_store(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE outbox SET payload_json = ? WHERE workflow_id = ?",
            ("{not-json", WORKFLOW_ID),
        )
        connection.commit()
    with pytest.raises(OutboxStateError, match="malformed JSON"):
        _ = outbox.items


def test_nonpublication_actions_do_not_create_outbox_rows(tmp_path: Path) -> None:
    database = tmp_path / "outbox-none.sqlite3"
    store = SQLiteWorkflowStore(database, WORKFLOW_ID)
    store.process(action("cmd-1", 0, "refresh_evidence"))
    store.process(action("cmd-rejected", 1, "publish"))
    assert SQLiteOutboxWorker(database, WORKFLOW_ID).items == ()
    assert store.state == GateState(evidence_current=True, revision=1)


def test_recovery_requires_identity_of_failed_worker(tmp_path: Path) -> None:
    database = tmp_path / "outbox-recovery-identity.sqlite3"
    _, outbox = prepare_published_store(database)
    with pytest.raises(ValueError, match="failed worker"):
        outbox.recover_inflight(worker_id="")
    assert outbox.items[0].status == "pending"
