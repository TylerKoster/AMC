# AMC dispatcher replay and idempotency design v0.1

Status: local SQLite reference implemented; production durability not established
Date: 2026-07-17

## Problem

The current dispatcher correctly evaluates one in-memory state transition at a time. A durable system must also survive retries, duplicate delivery, reordered messages, concurrent commands, and crashes without executing an action twice or accepting stale authorization.

## Required command envelope

Every command should contain:

- `command_id`: globally unique idempotency key;
- `workflow_id`: canonical workflow identity;
- `expected_revision`: revision the caller observed;
- `policy_version`: dispatcher contract used by the caller;
- `action`: closed-vocabulary command;
- `actor_id` and `authority_class`;
- `issued_at`: audit metadata, not ordering authority;
- `payload_hash`: canonical hash used to detect command-ID reuse with different content.

The AMC may display these values, but it does not authoritatively assign them.

## Required event envelope

Every accepted or rejected result should contain:

- `event_id`;
- `command_id` when caused by a command;
- `workflow_id`;
- monotonically assigned `sequence_number`;
- resulting `state_revision`;
- `policy_version`;
- event type and typed payload;
- `previous_event_hash` and canonical event hash where tamper evidence is required.

## Processing rules

1. Validate schema and policy version.
2. Look up `command_id`.
3. If the identical command was already processed, return its recorded result without executing again.
4. If the same ID has a different payload hash, reject it as an idempotency-key collision.
5. Compare `expected_revision` with canonical state revision.
6. Reject stale or future revisions without mutating state.
7. Apply the deterministic transition inside one transaction.
8. Store new state, outcome event, and idempotency result atomically.
9. Dispatch external side effects from a transactional outbox keyed by event ID.

Rules 1–6, deterministic event recording/replay, and restoration of the idempotency registry from a verified stream are implemented in `pilot/event_dispatcher.py`. `pilot/sqlite_event_store.py` implements rules 7 and 8 as a local append-only reference: the event envelope contains resulting state and is committed atomically, while state and idempotency are reconstructed from verified events. `pilot/sqlite_outbox.py` implements a local Rule 9 reference for publication effects. The negative control demonstrates that the outbox provides at-least-once delivery; preventing duplicate physical effects additionally requires a durable idempotency contract at the external provider.

## Conflict behavior

| Situation | Required result |
|---|---|
| Identical command delivered twice | Return the original outcome; execute at most once |
| Same command ID, changed payload | Reject collision and alert |
| Two commands target the same revision | One may commit; the loser is rejected as a revision conflict |
| Approval arrives after invalidation | Reject because the basis revision is stale |
| Publication races with invalidation | Only the transaction matching canonical revision may commit; invalidation must prevent stale publication |
| Response is lost after commit | Retry returns the stored prior result |
| Crash before commit | No state or event becomes visible |
| Crash after commit but before external side effect | Outbox retries the side effect using the event idempotency key |
| Duplicate event during replay | Deduplicate by event ID or reject a broken sequence |
| Gap or broken prior hash during replay | Stop replay and report corruption; do not infer missing state |

## Replay contract

- Replay starts from a verified snapshot or initial state.
- Events are applied in canonical sequence order, never arrival time.
- Every event's workflow, sequence, previous hash, schema, and policy version are checked.
- Replaying the same verified stream produces byte-equivalent canonical state.
- Projections are regenerated from canonical state and events; stored AMC prose is not replay authority.
- Unknown event types or unsupported migrations stop replay explicitly.

## Tests required before implementation is considered complete

- duplicate command, same payload;
- duplicate command, different payload;
- stale, future, and missing expected revision;
- simultaneous commands from the same state;
- invalidation racing with approval and publication;
- lost response followed by retry;
- crash at each transaction boundary;
- duplicate, missing, reordered, corrupted, and unknown events;
- snapshot plus tail replay equivalence to full replay;
- policy upgrade and unsupported downgrade;
- outbox side effect retried without duplication.

## Architectural conclusion

The dispatcher remains the enforcement layer, but a database transaction, idempotency registry, event reducer, and outbox are necessary for durable safety. Failure Space and AMC variants can improve model proposals; they cannot provide exactly-once processing or concurrency control.

## Run Result

**REFERENCE IMPLEMENTED.** Command envelopes, idempotency, revision conflicts, command fingerprints, hash-chained events, verified replay, checkpoints, SQLite transactions, rollback fault injection, restart restoration, cross-connection serialization, and a publication outbox are implemented locally. Actual process termination, cross-process stress, filesystem failure, signed roots, backups, schema migration, provider idempotency durability, worker leases, and real external effects remain unverified or unimplemented. No production durability or exactly-once claim is made.
