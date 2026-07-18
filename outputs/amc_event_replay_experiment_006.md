# AMC event replay experiment 006

Status: local deterministic result
Date: 2026-07-17

## Question

Can the dispatcher survive duplicate commands, command-ID collisions, stale revisions, delayed approval, same-process command races, and event replay without relying on a language model?

## Implementation

`pilot/event_dispatcher.py` adds:

- versioned command envelopes;
- workflow and command IDs;
- expected revisions;
- command type, actor, and authority metadata;
- canonical command fingerprints;
- identical-command idempotency;
- changed-payload collision detection;
- in-process serialization with a lock;
- sequenced, hash-chained event envelopes;
- dispatcher state recorded after every outcome;
- independent replay that regenerates and verifies transitions.
- restoration of state and command/collision idempotency records from a verified full stream.

## Observed cases

| Case | Observation |
|---|---|
| Full workflow | Six events replayed to byte-equivalent canonical state |
| Identical retry | Original result returned; no second event or transition |
| Same command ID, changed action | Collision event recorded; changed command not executed |
| Stale revision | Rejected without state change |
| Future revision | Rejected without state change |
| Approval delayed until after invalidation | Rejected as a revision conflict |
| Two concurrent refresh commands at revision 0 | One accepted; one revision conflict; final revision 1 |
| Wrong policy version | Recorded rejection; retry idempotent |
| Unknown action | Dispatcher rejection recorded and replayed |
| Missing or reordered event | Replay stopped |
| Changed payload without new hash | Replay stopped on hash failure |
| Rehashed but false state or dispatcher payload | Replay stopped on semantic contradiction |
| Missing authority metadata | Replay stopped |
| Repeated command event not marked as collision | Replay stopped |
| Restart from verified full stream | State, command idempotency, collision idempotency, sequence, and prior hash restored |

## Verification

The complete dispatcher suite now reports:

```text
117 passed in 2.04s
```

The original AMC contract, event-trigger, compact-projection, and 14 dispatcher smoke checks also pass.

## Critique and limits

This is not exactly-once production execution. The engine uses an in-process lock and memory collections. It does not survive process restart and does not coordinate multiple service instances. The hash chain detects changes only when a trusted prior hash or signed root is retained; an attacker who can rewrite the entire unanchored stream can recompute every hash.

Not implemented:

- database transaction spanning state, event, and idempotency record;
- optimistic compare-and-swap across processes;
- transactional outbox and idempotent external tools;
- snapshot plus tail replay;
- key management or signed checkpoint roots;
- event schema migration;
- durable recovery after injected crash points.

AMC and Failure Space remain model-facing projections. They do not participate in replay authority or concurrency resolution.

## Next step

Before selecting a database, define a storage adapter contract and run the same engine tests against an in-memory transactional fake. Add crash-point tests at pre-write, partial-write, committed-response-lost, and side-effect-pending stages. Then implement one local durable adapter, likely SQLite, and compare full replay with snapshot-plus-tail replay.

## Run Result

**COMPLETED — IN-MEMORY REPLAY AND IDEMPOTENCY PASSED.** The expanded suite passed 117 tests. Duplicate, collision, revision, delayed-approval, concurrent-command, restart-restoration, corrupt-stream, and semantic-replay cases behaved according to the v0.1 contract. Durable and cross-process guarantees remain unimplemented.
