"""Transactional-outbox worker and idempotent fake external executor."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Protocol


DELIVERY_FAULT_POINTS = frozenset(
    {
        "after_claim_before_send",
        "after_ack_before_completion",
        "after_completion_before_response",
    }
)


class InjectedDeliveryFault(RuntimeError):
    """Raised by tests at a declared outbox delivery boundary."""


class ExternalEffectResponseLost(RuntimeError):
    """The provider applied an effect but its response was not received."""


class ExternalIdempotencyCollision(ValueError):
    """An idempotency key was reused with different effect content."""


class OutboxStateError(RuntimeError):
    """The stored outbox row cannot be safely claimed or completed."""


@dataclass(frozen=True)
class OutboxItem:
    outbox_id: str
    workflow_id: str
    event_id: str
    effect_type: str
    idempotency_key: str
    payload: Mapping[str, Any]
    status: str
    attempt_count: int
    recovery_count: int
    worker_id: str | None
    result: Mapping[str, Any] | None


@dataclass(frozen=True)
class ExternalEffectResult:
    idempotency_key: str
    effect_type: str
    receipt_id: str
    duplicate: bool


@dataclass(frozen=True)
class DeliveryResult:
    item: OutboxItem
    external_result: ExternalEffectResult


class ExternalExecutor(Protocol):
    def execute(
        self,
        *,
        idempotency_key: str,
        effect_type: str,
        payload: Mapping[str, Any],
    ) -> ExternalEffectResult: ...


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(effect_type: str, payload: Mapping[str, Any]) -> str:
    content = _canonical_json(
        {"effect_type": effect_type, "payload": dict(payload)}
    ).encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _decode_json(raw: str | None, *, field: str) -> Mapping[str, Any] | None:
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OutboxStateError(f"{field} is malformed JSON") from exc
    if not isinstance(value, dict):
        raise OutboxStateError(f"{field} must decode to an object")
    return value


class FakeIdempotentExecutor:
    """Local stand-in for a provider that honors idempotency keys."""

    def __init__(self) -> None:
        self._effects: dict[str, tuple[str, ExternalEffectResult]] = {}
        self._lock = RLock()
        self._lose_next_response = False
        self.call_count = 0
        self.physical_effect_count = 0

    def lose_next_response(self) -> None:
        self._lose_next_response = True

    def execute(
        self,
        *,
        idempotency_key: str,
        effect_type: str,
        payload: Mapping[str, Any],
    ) -> ExternalEffectResult:
        if not idempotency_key or not effect_type:
            raise ValueError("idempotency_key and effect_type must be non-empty")
        fingerprint = _fingerprint(effect_type, payload)
        with self._lock:
            self.call_count += 1
            prior = self._effects.get(idempotency_key)
            if prior is not None:
                prior_fingerprint, prior_result = prior
                if prior_fingerprint != fingerprint:
                    raise ExternalIdempotencyCollision(
                        "external idempotency key reused with changed payload"
                    )
                result = ExternalEffectResult(
                    idempotency_key=prior_result.idempotency_key,
                    effect_type=prior_result.effect_type,
                    receipt_id=prior_result.receipt_id,
                    duplicate=True,
                )
            else:
                self.physical_effect_count += 1
                result = ExternalEffectResult(
                    idempotency_key=idempotency_key,
                    effect_type=effect_type,
                    receipt_id=f"fake-receipt-{self.physical_effect_count}",
                    duplicate=False,
                )
                self._effects[idempotency_key] = (fingerprint, result)

            if self._lose_next_response:
                self._lose_next_response = False
                raise ExternalEffectResponseLost(
                    "effect applied but simulated provider response was lost"
                )
            return result


class FakeNonIdempotentExecutor:
    """Negative control showing that an outbox alone can duplicate effects."""

    def __init__(self) -> None:
        self.call_count = 0
        self.physical_effect_count = 0
        self._lose_next_response = False

    def lose_next_response(self) -> None:
        self._lose_next_response = True

    def execute(
        self,
        *,
        idempotency_key: str,
        effect_type: str,
        payload: Mapping[str, Any],
    ) -> ExternalEffectResult:
        del payload
        self.call_count += 1
        self.physical_effect_count += 1
        result = ExternalEffectResult(
            idempotency_key=idempotency_key,
            effect_type=effect_type,
            receipt_id=f"non-idempotent-receipt-{self.physical_effect_count}",
            duplicate=False,
        )
        if self._lose_next_response:
            self._lose_next_response = False
            raise ExternalEffectResponseLost(
                "effect applied but simulated provider response was lost"
            )
        return result


class SQLiteOutboxWorker:
    """Claims pending rows and completes them after external acknowledgement."""

    def __init__(
        self,
        database_path: str | Path,
        workflow_id: str,
        *,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.database_path = Path(database_path)
        self.workflow_id = workflow_id
        self.timeout_seconds = timeout_seconds
        if not workflow_id or not isinstance(workflow_id, str):
            raise ValueError("workflow_id must be a non-empty string")

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

    @staticmethod
    def _item(row: sqlite3.Row) -> OutboxItem:
        payload = _decode_json(row["payload_json"], field="outbox payload")
        result = _decode_json(row["result_json"], field="outbox result")
        if payload is None:
            raise OutboxStateError("outbox payload is missing")
        return OutboxItem(
            outbox_id=row["outbox_id"],
            workflow_id=row["workflow_id"],
            event_id=row["event_id"],
            effect_type=row["effect_type"],
            idempotency_key=row["idempotency_key"],
            payload=payload,
            status=row["status"],
            attempt_count=row["attempt_count"],
            recovery_count=row["recovery_count"],
            worker_id=row["worker_id"],
            result=result,
        )

    @property
    def items(self) -> tuple[OutboxItem, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM outbox WHERE workflow_id = ? ORDER BY outbox_id",
                (self.workflow_id,),
            ).fetchall()
            return tuple(self._item(row) for row in rows)

    def recover_inflight(self, *, worker_id: str) -> int:
        if not worker_id or not isinstance(worker_id, str):
            raise ValueError("worker_id must identify the failed worker")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE outbox SET status = 'pending', worker_id = NULL, "
                "recovery_count = recovery_count + 1 "
                "WHERE workflow_id = ? AND status = 'inflight' AND worker_id = ?",
                (self.workflow_id, worker_id),
            )
            connection.commit()
            return cursor.rowcount
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _claim(self, worker_id: str) -> OutboxItem | None:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT o.* FROM outbox o "
                "JOIN events e ON e.workflow_id = o.workflow_id "
                "AND e.event_id = o.event_id "
                "WHERE o.workflow_id = ? AND o.status = 'pending' "
                "ORDER BY e.sequence_number LIMIT 1",
                (self.workflow_id,),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            cursor = connection.execute(
                "UPDATE outbox SET status = 'inflight', worker_id = ?, "
                "attempt_count = attempt_count + 1 "
                "WHERE outbox_id = ? AND status = 'pending'",
                (worker_id, row["outbox_id"]),
            )
            if cursor.rowcount != 1:
                raise OutboxStateError("outbox claim lost its pending state")
            claimed = connection.execute(
                "SELECT * FROM outbox WHERE outbox_id = ?",
                (row["outbox_id"],),
            ).fetchone()
            connection.commit()
            if claimed is None:
                raise OutboxStateError("claimed outbox row disappeared")
            return self._item(claimed)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _complete(
        self,
        item: OutboxItem,
        worker_id: str,
        result: ExternalEffectResult,
    ) -> OutboxItem:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE outbox SET status = 'completed', result_json = ?, "
                "worker_id = NULL WHERE outbox_id = ? "
                "AND status = 'inflight' AND worker_id = ?",
                (_canonical_json(asdict(result)), item.outbox_id, worker_id),
            )
            if cursor.rowcount != 1:
                raise OutboxStateError(
                    "outbox completion does not own the inflight row"
                )
            row = connection.execute(
                "SELECT * FROM outbox WHERE outbox_id = ?",
                (item.outbox_id,),
            ).fetchone()
            connection.commit()
            if row is None:
                raise OutboxStateError("completed outbox row disappeared")
            return self._item(row)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def deliver_one(
        self,
        executor: ExternalExecutor,
        *,
        worker_id: str,
        fault_point: str | None = None,
    ) -> DeliveryResult | None:
        if not worker_id or not isinstance(worker_id, str):
            raise ValueError("worker_id must be a non-empty string")
        if fault_point is not None and fault_point not in DELIVERY_FAULT_POINTS:
            raise ValueError("fault_point is not recognized")
        item = self._claim(worker_id)
        if item is None:
            return None
        if fault_point == "after_claim_before_send":
            raise InjectedDeliveryFault(fault_point)

        external_result = executor.execute(
            idempotency_key=item.idempotency_key,
            effect_type=item.effect_type,
            payload=item.payload,
        )
        if fault_point == "after_ack_before_completion":
            raise InjectedDeliveryFault(fault_point)

        completed = self._complete(item, worker_id, external_result)
        if fault_point == "after_completion_before_response":
            raise InjectedDeliveryFault(fault_point)
        return DeliveryResult(item=completed, external_result=external_result)
