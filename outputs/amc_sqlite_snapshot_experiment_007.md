# AMC SQLite and snapshot experiment 007

Status: local deterministic storage experiment
Date: 2026-07-17

## Question

Can a local transactional event store preserve dispatcher state and idempotency across restart, roll back injected pre-commit failures, recover from a committed-but-lost response, serialize two connections targeting the same revision, detect stored corruption, and accelerate replay with a verified checkpoint?

## Implementation

`pilot/sqlite_event_store.py` provides a reference SQLite adapter using only the Python standard library.

- Append-only workflow events.
- `BEGIN IMMEDIATE` transaction around restore, command evaluation, and event append.
- Workflow policy and initial-state contract verification.
- Restart reconstruction from verified events.
- Durable identical-command and collision idempotency through event reconstruction.
- Fault injection before insert, after insert/before commit, and after commit/before response.
- Cross-connection serialization.
- Stored column/envelope consistency checks.
- Verified checkpoints containing state, prior hash, sequence, and command fingerprints.
- Snapshot-plus-tail replay with full semantic verification.

SQLite is a reference adapter for the experiment, not a final production database decision.

## Transaction observations

| Case | Observation |
|---|---|
| Complete workflow and new store instance | Six events restored the published state |
| Duplicate after restart | Original result returned; no second event |
| Fault before insert | Transaction rolled back; no event or state change |
| Fault after insert but before commit | Transaction rolled back; no event or state change |
| Fault after commit but before response | Event remained; retry returned the prior result idempotently |
| Two connections submit refresh at revision 0 | One action accepted; one revision conflict |
| Changed payload reuses prior command ID | Collision persisted and remained idempotent after restart |
| Corrupt hash column or event JSON | Load stopped before state was trusted |
| Changed workflow initialization contract | Store rejected the mismatch |
| Collision after checkpoint refers to pre-checkpoint command | Checkpoint command registry preserved validation |

## Snapshot benchmark

The local benchmark generated 1,000 alternating evidence-refresh and evidence-invalidation events, created a checkpoint at event 900, and replayed a 100-event tail. Each method was measured 30 times.

| Measurement | Full replay | Checkpoint + tail |
|---|---:|---:|
| Events replayed | 1,000 | 100 |
| Median local replay time | 15.296 ms | 1.848 ms |
| Replay working bytes | 892,574 B | 163,888 B |

Observed in this fixture:

- checkpoint-plus-tail replay was 8.279 times faster;
- replay working bytes were 81.639% lower;
- final state and revision 1,000 were identical;
- the 74,532-byte checkpoint adds about 8.35% storage overhead to the retained full log.

The canonical event log is still required. The checkpoint is a derived replay accelerator, not event-log compression. Its `seen_commands` registry also grows with command count, so the snapshot is not yet a bounded-size object.

## Verification

```text
136 passed in 2.48s
```

This includes dispatcher state validation, phase/action coverage, 10,000 generated steps, ten critical source mutants, in-memory event replay, restart idempotency, SQLite faults, cross-connection conflicts, corruption detection, and snapshot-tail equivalence.

## Critique and remaining risks

- Injected exceptions are not the same as forcibly terminating a process or losing power.
- Cross-connection threads are not a cross-process stress test.
- SQLite replay currently rebuilds the engine from the full log for every command; checkpoints accelerate explicit state replay but are not yet used in command processing.
- Hash chains require a trusted signed or externally retained root to resist full-stream rewriting.
- No external action is connected, so exactly-once side effects are not demonstrated.
- No outbox, backup/restore drill, migration framework, disk-full test, filesystem-corruption test, or key management exists.
- Timing is a local microbenchmark and should not be generalized to production hardware or workloads.

## Architectural inference

The event store and the AMC solve different problems:

- event store: canonical state, replay, concurrency, audit, and idempotency;
- compact AMC: model/human current-state projection;
- Failure Space: optional model-facing invariant reminder;
- dispatcher: executable policy enforcement.

The AMC should be regenerated from verified canonical state. It must not become a second authority that competes with the database event stream.

## Next experiment

Add a transactional outbox with a fake side-effect executor and idempotency key. Inject failures before send, after send/before acknowledgement, and after acknowledgement/before outbox completion. This is the missing test needed to distinguish durable state correctness from exactly-once external behavior.

## Run Result

**COMPLETED — SQLITE REFERENCE AND SNAPSHOT TESTS PASSED.** The full suite passed 136 tests. Transaction rollback, committed-response recovery, restart idempotency, cross-connection revision conflict, stored corruption, verified checkpoints, and snapshot-tail equivalence behaved as specified. Production durability and exactly-once external effects remain unproven.
