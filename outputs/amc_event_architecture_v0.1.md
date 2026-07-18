# AMC event architecture — working design

## Purpose

Treat an Agent Memory Capsule (AMC) as an inspectable **handoff projection**, not as the system's only memory or as a pass/fail test artifact. It should let a new agent and a human reconstruct what the work means, what may happen next, and what must not happen.

This is a design hypothesis. It has not been validated by the one synthetic live evaluation.

## Recommended shape

```text
work events + evidence + approvals + human edits
                    |
                    v
          append-only event record
                    |
          projection / validation rules
                    |
                    +--> AMC (agent handoff)
                    +--> human projection (review)
                    +--> task queue / alerts
                    +--> audit trail
```

The durable record is the event history. AMC is a compact, current view produced from that history. This matters because a standalone file cannot reliably represent correction, expiry, conflict, or revocation after it has been shared.

## Events worth observing

| Event | Upstream cause | AMC effect | Downstream risk if missing |
|---|---|---|---|
| Goal changed | Human reframes task | invalidate old next action and expected output | agent finishes the wrong task |
| Evidence added or removed | Research result, source outage | update claim support and source pointers | unsupported answer is repeated |
| Evidence expired | Time limit, dataset update, license change | mark dependent claims stale | agent acts on old information |
| Claim status changed | observation becomes inference, or is disproved | change certainty label | inference is presented as fact |
| Action state changed | completed, failed, retried, superseded | update queue and idempotency guard | duplicated external action |
| Approval granted, denied, or revoked | human/policy decision | permit, block, or revoke action | unauthorized publication or execution |
| Handoff requested | agent pauses or is replaced | create a frozen, signed projection | hidden state is lost at transfer |
| Human corrects projection | reviewer spots an error | record correction and reason | system learns nothing from review |
| Concurrent agents disagree | different evidence or plans | surface conflict instead of merging silently | contradictory work is published |
| Model or prompt changes | runtime configuration change | attach provenance to output | results cannot be compared or reproduced |

## Triggers to add first

1. **Staleness trigger:** if evidence is older than its declared freshness rule, move dependent claims to `needs_recheck` and block recommendations.
2. **Approval trigger:** an action with `approval_required` cannot be dispatched until a named approval event exists; a revoked approval cancels queued work.
3. **Evidence-change trigger:** a changed or withdrawn source invalidates the claims and actions that rely on it.
4. **Duplicate-action trigger:** a retry with the same idempotency key is marked as a retry, not a new task.
5. **Human-review trigger:** any answer that crosses a defined risk threshold produces a short human projection and waits for review.
6. **Conflict trigger:** incompatible claims or next actions create a review item rather than a silent overwrite.

## Observability record for every event

Each event should carry, at minimum:

- `event_id`, time, actor type (`human`, `agent`, `system`), and task/capsule ID
- previous and new state
- evidence references or an explicit `no_evidence` label
- authorization decision and approver where relevant
- model, prompt/version, and tool configuration for agent-generated events
- idempotency key for anything that could be repeated
- a human-readable reason

Do not put raw private source content, API keys, or broad conversation logs into an AMC by default.

## Experiment program — improvement, not a tournament

| Experiment | What changes | What we observe | Improvement signal |
|---|---|---|---|
| Field-ablation | remove one field from an AMC | which operational decisions become wrong or uncertain | retain fields whose removal changes safe behavior |
| Stale-evidence drill | change a license or update date after handoff | whether recommendation is blocked and claims are rechecked | no recommendation based on invalidated evidence |
| Approval-race drill | revoke approval while an action is queued | whether execution is stopped | zero unauthorized dispatches |
| Retry drill | replay a completed action | whether work is duplicated | idempotency prevents duplicate external work |
| Conflict drill | give two agents incompatible evidence | whether conflict is exposed to a human | no silent merge or fabricated certainty |
| Compression ladder | compare full AMC, compact AMC, and summary | safety, task continuity, human review time, input size | smallest form that preserves required behavior |
| Human inspection drill | ask reviewers to find the intended next action and limits | time, errors, corrections | fast, accurate review with useful corrections |

## What the current live result means

The summary and AMC both passed the five simple safety checks in one synthetic scenario. That is useful only as a harness check. It tells us the scenario was too easy to distinguish the two forms.

The AMC did preserve extra information (claim status, update cadence, approval requirement), but the grader did not demand those distinctions. The next experiments should therefore target events where those fields alter downstream behavior, especially stale evidence, approval changes, retries, and conflicting agent work.

## Minimum next implementation

Add event fixtures and deterministic graders for the six experiments above before adding more model complexity. The first useful deliverable is not a new file format; it is an auditable event-to-AMC projection with explicit invalidation and approval rules.
