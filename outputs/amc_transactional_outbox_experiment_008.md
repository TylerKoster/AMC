# AMC transactional outbox experiment 008

Status: local deterministic side-effect experiment
Date: 2026-07-17

## Question

Can publication state and a pending external effect be committed together, and can an outbox recover safely when failure occurs before send, after the physical effect but before acknowledgement, after acknowledgement but before outbox completion, or after completion but before the worker responds?

## Implementation

- An accepted `publish` event creates an outbox row in the same SQLite transaction.
- The outbox payload is bound to the accepted event ID, event hash, workflow, action, and state revision.
- Workers claim only pending rows under `BEGIN IMMEDIATE`.
- Claimed rows become `inflight` with a worker identity and attempt count.
- Recovery requires the explicitly identified failed worker; there is no recover-all operation.
- Completed rows retain the external receipt.
- The fake idempotent executor stores a content fingerprint for each idempotency key and rejects changed payloads.
- A non-idempotent fake executor is retained as a negative control.

## Observations

| Failure point or condition | Idempotent provider | Non-idempotent provider |
|---|---|---|
| Publish transaction fails before commit | Event and outbox both rolled back | Same |
| Failure after claim, before send | No physical effect; recovered delivery succeeds | Same |
| Effect applied, response lost | Two calls, one physical effect | Two calls, two physical effects |
| Acknowledgement received, completion not stored | Retry recognized duplicate; one physical effect | Would duplicate on retry |
| Completion stored, worker response lost | Completed row was not redelivered | Same, because no retry was attempted |
| Two workers target one pending row | One claim and one physical effect | Same in the tested no-failure path |
| Same idempotency key with changed payload | Collision rejected | No protection |

Additional observations:

- Non-publication and rejected publication actions created no outbox row.
- Corrupt outbox payload JSON stopped delivery.
- Attempt and recovery counts remained inspectable.
- The outbox row referenced the exact accepted publication event hash.

## Verification

```text
149 passed in 4.20s
```

The full suite now covers dispatcher invariants, 10,000 generated state-machine steps, source mutants, event replay, SQLite transactions and corruption, checkpoints, snapshot-tail equivalence, outbox failure boundaries, worker claims, and provider-idempotency controls.

## Interpretation

The transactional outbox closes the database-to-worker gap but does not independently provide exactly-once external effects. It provides recoverable **at-least-once delivery**. A duplicate physical effect is prevented only when the external system durably binds an idempotency key to the original payload and result.

This distinction matters for AMC architecture:

- AMC may preserve the intention to publish.
- The dispatcher decides whether publication is authorized.
- The event transaction records that publication was accepted and queues an effect.
- The outbox retries delivery.
- The external provider determines whether a retry duplicates the physical effect.

No prompt or Failure Space representation can substitute for that provider contract.

## Limits

- Both fake providers are in-memory test doubles; provider restart and idempotency-key expiration are untested.
- Worker recovery is manual and has no lease, heartbeat, or timeout policy.
- Incorrectly declaring a live worker dead could cause simultaneous delivery attempts.
- Only publication is mapped to an effect.
- There is no real network, rate limiting, exponential backoff, dead-letter queue, cancellation, receipt verification, or reconciliation job.
- Injected exceptions do not reproduce operating-system termination or power loss.
- The test does not establish production exactly-once behavior.

## Next experiment

The next bounded work should return to AMC variants rather than deepen infrastructure indefinitely. The deterministic safety substrate is now sufficient for an exploratory variant tournament where every model proposal is separated from actual execution. Run no-API preservation and size filtering first, then compare the finalists through live model calls.

## Run Result

**COMPLETED — TRANSACTIONAL OUTBOX REFERENCE PASSED.** The complete suite passed 149 tests. All declared failure boundaries behaved as specified. The idempotent-provider condition produced one physical effect after a lost response; the non-idempotent negative control produced two, disproving any claim that the outbox alone guarantees exactly-once effects.
