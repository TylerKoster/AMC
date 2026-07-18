# AMC dispatcher foundation experiment 005

Status: local deterministic result
Date: 2026-07-17

## Question

Does the in-memory dispatcher conform to an independently stated workflow contract under exhaustive phase/action checks, malformed states, generated action sequences, and ten deliberately damaged source variants?

## Changes

- Added a written transition contract independent of dispatcher control flow.
- Added `validate_state()` and explicit state invariants.
- Added closed action and approval-status vocabularies.
- Unknown non-empty actions now reject with `unsupported_action`.
- Malformed action types, approval bases, and impossible states fail at the boundary.
- Added pytest deterministic, exhaustive, generated state-machine, and source-mutation tests.
- Added a replay/idempotency design specifying behavior that is not yet implemented.

## Test scope

- Seven canonical workflow phases.
- Every known action plus one unknown action from every canonical phase.
- Full accepted path, stale approval, valid approval, publication, and invalidation.
- Invalidation from every canonical phase.
- A 4,096-combination bounded state-structure enumeration; seven combinations satisfied the v0.1 invariants for revision 1.
- Malformed state and command boundaries.
- 200 generated state-machine examples with 50 steps each: 10,000 generated steps.
- Ten source-level critical mutants.

## Critical mutants detected

1. Inverted evidence gate.
2. Inverted license gate.
3. Inverted recommendation gate.
4. Action allowed after publication.
5. Duplicate approval request allowed while pending.
6. Evidence refresh failed to advance revision.
7. License verification failed to advance revision.
8. Recommendation formation failed to advance revision.
9. Approval request bound to the previous revision.
10. Approval grant required the wrong status.

## Result

```text
90 passed in 4.49s
```

The older 14-check dispatcher script also remains relevant as a readable smoke test, but the pytest suite is now the primary deterministic assurance layer.

## Interpretation

The v0.1 in-memory transition logic passed the implemented oracle. This does not establish production safety. The implementation still lacks durable event replay, command identity, idempotent retries, optimistic concurrency, transactional persistence, and an outbox for external side effects.

The state validator is a material architectural improvement: invalid combinations can no longer enter public dispatcher functions silently. It also reduces the meaningful state space and makes some apparent code mutations equivalent because impossible states are rejected before policy evaluation.

## Next step

Implement a pure event reducer and command envelope in memory before choosing a database. Test duplicate delivery, stale revision conflicts, replay equivalence, and simultaneous command behavior. Only then should storage and an outbox be introduced.

## Run Result

**COMPLETED — DETERMINISTIC FOUNDATION PASSED.** Ninety tests passed, 10,000 generated steps preserved the independent model, and all ten critical source mutants were detected. Durable replay and concurrency remain explicitly unimplemented.
