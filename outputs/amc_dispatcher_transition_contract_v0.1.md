# AMC dispatcher transition contract v0.1

Status: independent test oracle
Date: 2026-07-17

## Purpose

This contract defines expected dispatcher behavior independently of the Python control flow. The canonical event log and validated dispatcher state—not an AMC or model statement—determine which side-effecting action is executable.

## Ordered workflow phases

| Phase | State predicate | Only allowed action |
|---|---|---|
| Evidence missing | `evidence_current = false` | `refresh_evidence` |
| License missing | evidence current; `license_verified = false` | `verify_license` |
| Recommendation missing | evidence and license ready; `recommendation_ready = false` | `form_recommendation` |
| Approval available | prerequisites ready; approval neither current-pending nor current-granted | `request_publication_approval` |
| Approval pending | request bound to current revision; no grant | none |
| Approval granted | request and grant bound to current revision | `publish` |
| Published | current-revision approval granted; `published = true` | none |

Earlier unmet prerequisites take priority over every later phase.

## Accepted transition effects

| Command | Required phase | State effect | Revision effect |
|---|---|---|---|
| `refresh_evidence` | Evidence missing | evidence becomes current | +1 |
| `verify_license` | License missing | license becomes verified | +1 |
| `form_recommendation` | Recommendation missing | recommendation becomes ready | +1 |
| `request_publication_approval` | Approval available | approval becomes pending and request binds to current revision | unchanged |
| approval grant event | Approval pending and matching basis revision | approval becomes granted and grant binds to current revision | unchanged |
| `publish` | Approval granted | publication becomes true | unchanged |
| evidence invalidation event | Any valid phase | evidence, license, recommendation and publication become false; approval and revision references are cleared | +1 |

## Rejection contract

- A known action outside the current phase is rejected without changing state or revision.
- An unknown non-empty action is rejected as `unsupported_action` without changing state.
- A malformed action value is rejected at the input boundary.
- An approval grant is rejected unless a request is pending for the exact current basis revision.
- Rejection events state the attempted action or approval basis and the reason.

## State invariants

1. License verification implies current evidence.
2. Recommendation readiness implies license verification.
3. Pending approval has a current request revision and no grant revision.
4. Granted approval has request and grant revisions equal to the current revision.
5. Revoked approval retains no request or grant revision.
6. Pending or granted approval implies recommendation readiness.
7. Publication implies current-revision granted approval and all prerequisites.
8. Revision and approval revisions are non-negative integers, never booleans.
9. No command is allowed after publication.
10. Every accepted state is valid under all invariants.

## Replay and delivery requirements

The current in-memory dispatcher does not yet implement durable replay, event identity, idempotency keys, or concurrency control. Before external writes are enabled, a later contract revision must define duplicate delivery, out-of-order delivery, stale retries, crash recovery, and concurrent approval/invalidation behavior.

## Run Result

**DEFINED.** This document is the dispatcher test oracle for the v0.1 workflow. It does not claim that durable event processing or concurrency safety is implemented.
