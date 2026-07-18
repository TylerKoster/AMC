# AMC ID-only dependency experiment 002

## Question

When later events contain only structured identifiers, can an agent determine which claims and actions are affected without inventing relationships? Does a software-generated compact AMC preserve the useful links with less input than the full AMC?

## Method

- Model: `gpt-5.6-sol`
- Three isolated runs per condition
- No tools, web access, or shared conversation state
- Same question and event identifiers for all conditions
- Condition-specific expected behavior:
  - summary: admit the evidence-to-claim mapping is absent and request history;
  - full AMC and compact AMC: resolve exact identifier equality in structured fields.

## Observations

| Condition | JSON size | Gzip size | Repeated observations |
|---|---:|---:|---|
| Summary + ID events | 338 B | 232 B | 9/10, 9/10, 9/10 |
| Full AMC + ID events | 2,619 B | 1,080 B | 10/11, 10/11, 11/11 |
| Compact AMC current view | 782 B | 419 B | 11/11, 11/11, 11/11 |

These counts are diagnostic summaries, not pass/fail product scores.

### Summary behavior

All three runs:

- abstained and did not publish;
- recognized invalidated evidence and revoked approval;
- returned no invented claim IDs;
- marked dependency resolution as unavailable and requested history;
- dropped the city-tree/canopy detail from the stated goal.

The summary was safe in this scenario but could not identify the affected claims, as expected from the missing mapping.

### Full AMC behavior

All three runs found `claim-001` and `claim-002` through their exact `evidence_id` references and chose safe downstream behavior. Two runs nevertheless labeled `dependency_resolution` as `unresolved` while their own rationales said the mapping was explicit and returned both correct claim IDs.

This is an output-consistency problem, not a dependency-resolution failure. It suggests that fields derivable from the packet should be computed by software rather than restated probabilistically by the model.

### Compact AMC behavior

All three runs consistently:

- retained the complete goal;
- identified the two exact affected claims;
- recognized the revoked action approval;
- marked the dependency resolved;
- avoided an unnecessary history lookup;
- abstained from recommendation and publication.

The compact form was about 70% smaller than the full AMC plus events, but about 131% larger than the summary plus events. Its added bytes carried the exact dependency edges and full goal that the summary lacked.

## Changes prompted by experiment 001

Experiment 001 used a scalar `claim_status` that could not distinguish event knowledge from dependency knowledge. It also placed changed evidence and claims near one another without recording an explicit edge.

For experiment 002:

- the output contract required exact `affected_claim_ids` and `affected_action_ids`;
- the prompt defined exact equality in structured identifier fields as an explicit mapping;
- the compact projector added `links.evidence_to_claims`.

This changed the compact input from 708 B to 782 B. The 74 added bytes made the dependency relationship explicit and produced consistent behavior in three runs.

## Current architectural inference

The promising object is not simply a compressed document. It is a **software-generated materialized view of an event graph**:

- software calculates affected IDs, invalidations, approval state, and required lookups;
- the model interprets intent, explains the state, and proposes bounded next actions;
- humans inspect readable goals, states, links, and prohibitions;
- full history remains accessible by the capsule ID.

This is still a provisional inference from one synthetic scenario. It requires different tasks, models, adversarial events, and blinded human inspection before it supports a general claim.

## Newly observed upstream/downstream question

Several runs returned `request_approval` while evidence was still invalidated. Their prose generally sequenced rechecking first, but the structured field did not express timing. The next experiment should test gate ordering explicitly:

1. invalidated evidence blocks recommendation;
2. evidence and license rechecks must finish;
3. only then may the system request a new publication approval;
4. publication remains blocked until approval is granted.
