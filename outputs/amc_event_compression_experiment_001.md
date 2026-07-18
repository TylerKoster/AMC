# AMC event/compression experiment 001

## Research question

Can a deterministic software projection make an event-aware AMC materially smaller while preserving safe downstream behavior?

This experiment observes failure modes and improvement opportunities. Scores are contract observations, not a product pass/fail decision.

## Conditions and observations

| Condition | Minified JSON | Gzip | Contract observations |
|---|---:|---:|---:|
| Summary plus explicit events | 583 B | 320 B | 7/7 |
| Full AMC plus explicit events | 2,864 B | 1,150 B | 7/7 |
| Compact AMC v1 | 706 B | 399 B | 6/7 |
| Compact AMC v2 | 708 B | 396 B | 7/7 |

Compact v1 preserved that publishing was blocked, but not that approval had specifically been **revoked**. The agent therefore reported `required` instead of `revoked`. Compact v2 retained the transition explicitly and recovered that observation for two additional uncompressed bytes.

Compared with the full AMC plus events, compact v2 used about 75% fewer minified JSON bytes and 66% fewer gzip bytes. It remained about 21% larger than the summary plus explicit events.

## Interpretation

1. A compact AMC can be software. `pilot/compact_amc.py` deterministically projects current operational state from the full capsule and later events.
2. Compression must preserve **why a boundary exists**, not only the resulting boundary. `blocked` and `revoked` can require different downstream handling.
3. The summary condition was smallest and handled this easy, explicit event set correctly. This experiment does not show an AMC advantage.
4. AMC's possible value is dependency resolution: connecting terse event identifiers to affected claims, actions, evidence, and approvals when the event text itself does not explain the consequence.
5. Gzip helps disk or transport size only. The content must normally be decompressed before being sent to a language model, so gzip bytes are not a model-token saving.

## Architecture implication

Use four separable components:

1. Append-only event record: full evidence, action, correction, and approval history.
2. Deterministic projector: resolves dependencies and invalidations.
3. Compact AMC current view: human-readable state needed for the next decision.
4. History resolver: retrieves full records by `capsule_id`, claim ID, evidence ID, or action ID when needed.

The compact AMC should not contain the entire history. It should contain the smallest current state that changes behavior plus resolvable references to the full record.

## Next experiment

Use terse, ID-only later events. The summary will not be given dependency explanations, while the full and compact AMC retain explicit links. Observe whether the agent identifies which claims and actions must change, and whether it asks for missing context rather than inventing a relationship.

Repeat each condition several times before interpreting differences as stable model behavior.
