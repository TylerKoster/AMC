# AMC remainder test plan v0.1

Status: exploratory research plan; not a product-validation claim
Date: 2026-07-17

## Decision

Test the deterministic dispatcher before expanding paid AMC comparisons. The model can propose a bad action without causing harm if the dispatcher rejects it; a correct model proposal can still be unsafe if the dispatcher, event replay, or revision handling is wrong. These are different failure layers and must be measured separately.

The remaining program has four gates:

1. **Dispatcher correctness** — prove the small state machine behaves correctly under exhaustive, generated, mutated, replayed, and conflicting event sequences.
2. **AMC projection correctness** — prove that deterministic AMC variants preserve the declared contract before a model sees them.
3. **Agent robustness** — compare surviving AMC variants under controlled language, state, temporal, and adversarial mutations.
4. **External validity** — reproduce external benchmarks, test real trajectories, inspectability, multiple models, and independent reproduction.

## What has already been learned

- Experiment 001: compact AMC v2 was about 75% smaller than full AMC plus events, but the ordinary summary remained smallest on an easy explicit case.
- Experiment 002: the compact dependency map resolved ID-only changes consistently while the summary correctly abstained because it lacked the mapping.
- Experiment 003: putting the gate graph into every AMC added bytes without observable benefit in the tested case; enforcement belongs downstream.
- Experiment 004: exact repetition did not drift, delta-only continuation used 35% fewer submitted bytes, and an injected `required` to `optional` change caused two invalid proposals. Failure Space resisted both in two trials, but added context.

These are exploratory synthetic observations, not estimates of production reliability.

## Phase 1 — Dispatcher-focused tests

### 1.1 Freeze the transition contract

Express the dispatcher as a transition table independent of its Python implementation:

- states and legal combinations;
- commands;
- accepted transitions;
- rejected transitions;
- revision changes;
- approval binding;
- invalidation effects;
- terminal behavior;
- event emitted by every outcome.

This table is the oracle. Tests must not merely repeat the implementation's own logic.

### 1.2 Exhaustive reachable-state testing

Enumerate all states reachable through bounded valid and invalid sequences. For every reachable state, attempt every action in the closed vocabulary and approval grants for current, past, future, missing, and mismatched revisions.

Required invariants:

- an invalid action never changes state or revision;
- only the one currently allowed workflow action is accepted;
- publication implies current evidence, verified license, ready recommendation, and approval granted for the same revision;
- stale approval never authorizes publication;
- invalidation resets dependent state and revokes approval;
- no action is accepted after publication;
- unknown actions fail closed;
- each accepted transition emits exactly one auditable event;
- replaying accepted canonical events yields the same state.

The current 14 checks cover the primary path, one stale approval, and one invalidation. They do not cover the whole state space.

### 1.3 Property-based state-machine testing

Use a rule-based generator to create long sequences of actions, approvals, invalidations, retries, and malformed inputs. Check invariants after every step and retain the smallest failing sequence. Start with at least 10,000 local sequences; increase if new failures continue appearing.

Hypothesis supports generated rule sequences and invariants checked after each step, which fits this dispatcher directly: https://hypothesis.readthedocs.io/en/latest/stateful.html

### 1.4 Dispatcher mutation testing

Deliberately damage the dispatcher and verify the suite detects each material fault. Critical code mutants include:

- remove revision equality from approval;
- change prerequisite `and` logic to `or`;
- permit publication while approval is pending or revoked;
- fail to reset one dependent field during invalidation;
- fail to revoke approval during invalidation;
- accept an unsupported action;
- increment the wrong revision or fail to increment it;
- mutate state on rejection;
- leave publication enabled after invalidation;
- accept a duplicate action or stale retry;
- emit an accepted event for a rejected action;
- return the wrong allowed-action set.

The target is 100% kill of manually classified critical mutants. Surviving equivalent mutants are documented, not counted as test failures. Python mutation tools such as Cosmic Ray run the test suite against small source mutations: https://cosmic-ray.readthedocs.io/en/stable/tutorials/intro/index.html

### 1.5 Event, retry, and concurrency tests

The current dispatcher is in-memory and has no event reducer, event IDs, or compare-and-swap persistence. Those are architectural gaps, not test failures yet. Before real side effects, specify and test:

- duplicate event delivery;
- duplicate command after a lost response;
- out-of-order events;
- delayed approval arriving after invalidation;
- approval and invalidation racing on the same revision;
- two publication attempts;
- crash between state write and event write;
- partial or corrupt event record;
- replay from snapshot plus later events;
- policy-version change while an old AMC is active.

Expected rule: stale, duplicate, and conflicting operations fail closed or produce an idempotent prior result. No language model decides concurrency resolution.

### 1.6 Boundary and schema tests

Add a validated input boundary. Test nulls, wrong types, empty identifiers, unknown fields, unknown schema versions, extreme revisions, Unicode confusables, duplicate JSON keys, truncation, oversized fields, and malformed JSON. A directly constructed invalid `GateState` should be rejected by a validator rather than treated as canonical state.

JSON Schema provides separate core and validation specifications suitable for a versioned external boundary: https://json-schema.org/specification

### Phase 1 exit gate

- all transition-table cases pass;
- all declared invariants hold across generated sequences;
- all critical dispatcher mutants are killed;
- replay is deterministic;
- duplicate/stale operations have defined behavior;
- malformed inputs fail closed;
- no API/model calls are required for this phase.

## Phase 2 — AMC projection and format tests

### 2.1 Define the preservation oracle

Every trajectory receives a machine-readable preservation contract identifying:

- exact goal and identifiers;
- current and superseded facts;
- affected dependency edges;
- completed, pending, rejected, and prohibited actions;
- approval and revision state;
- unresolved questions;
- evidence provenance and freshness;
- what must be forgotten or excluded.

The canonical event log plus dispatcher state is ground truth. Each AMC projection is graded field-by-field before model evaluation.

### 2.2 Deterministic projector tests

Test that projections are deterministic, stable under irrelevant event additions, and correctly changed by relevant events. Required tests include:

- same event log always produces byte-identical canonical output;
- event ordering changes output only when order is semantically relevant;
- invalidation reaches every dependent claim and approval;
- rejected and superseded decisions remain auditable but inactive;
- cause is preserved where operationally relevant (`revoked` is not collapsed to `blocked`);
- missing dependency links trigger an explicit unresolved state;
- human-readable and machine-readable projections cannot disagree silently;
- every compact reference resolves to canonical history;
- schema migrations preserve the contract or fail explicitly.

### 2.3 AMC component ablations

Remove one field family at a time: goal, intention, evidence links, causal status, temporal/revision fields, negative decisions, unresolved questions, approvals, Failure Space, and history reference. Observe which preservation clauses break. This is more informative than treating an AMC as one indivisible prompt.

### Phase 2 exit gate

- zero unexplained preservation-contract losses in deterministic fixtures;
- every deliberate component removal has a documented consequence or is removed as unnecessary;
- compact size includes the canonical event storage, compilation, and required retrieval costs—not only prompt bytes.

## Phase 3 — AMC variant tournament

Do not fully cross every variant with every mutation. First eliminate weak variants using deterministic grading and a small exploratory set, then run the expensive comparison on finalists.

### Baseline variants

1. Current state only, with no memory narrative.
2. Full available history.
3. Last-k/sliding-window history.
4. Free-form summary.
5. Structured conventional summary.
6. Deterministic lexical retrieval over raw history.
7. A reproducible published/open memory baseline.

### AMC variants

8. Full AMC.
9. Compact AMC current view.
10. Compact AMC once plus authoritative state deltas.
11. Compact AMC plus minimal high-cost Failure Space.
12. Compact AMC plus machine-readable immutable constraints.
13. Compact AMC plus on-demand history resolver.
14. Compact AMC plus both resolver and minimal invariants.

### Diagnostic controls, not likely production formats

15. Gated compact AMC, retained to test whether explicit workflow policy helps harder tasks.
16. Full negative paraphrase, included once as a duplication-cost and contradiction control.
17. Hash/checksum only, which can detect changed bytes but cannot explain the conflict to a model.
18. Deliberately incomplete compact AMC, used to verify abstention and resolver behavior.

### Tournament rounds

- **Round A — no API:** schema validity, preservation contract, minified bytes, tokens, gzip/storage size, compilation time, and resolver cost for all variants.
- **Round B — smoke:** five held-out tasks, two runs per viable variant. Remove formats that are strictly worse on accuracy and total cost.
- **Round C — exploratory:** ten fresh real trajectories, top four to six variants, paired and randomized. Use a balanced incomplete mutation design rather than a full factorial explosion.
- **Round D — confirmatory:** freeze the top AMC variant, strongest conventional baseline, full history, and one retrieval baseline. Determine sample size from exploratory variance and a preregistered noninferiority margin.

## Phase 4 — Mutation catalog

Each mutation must declare an expected relationship. A mutation without an oracle is merely another prompt.

| Family | Examples | Expected relationship |
|---|---|---|
| Meaning-preserving language | punctuation, case, whitespace, field order, clause order, benign synonyms, faithful paraphrase, exact duplication | Same goal, state, and immediate action |
| Qualifier mutation | `must/should/may`, delete `not`, `required/optional`, `and/or`, numeric threshold | Only the explicitly affected decision may change; protected contradictions must be flagged |
| Authority mutation | operator text relabeled as system/state, source evidence phrased as instruction, spoofed approval | Untrusted text cannot change canonical state or authorization |
| Identifier mutation | transposed claim/evidence/action IDs, alias collision, missing mapping, duplicate ID | Resolve exact links or abstain; never invent an edge |
| Temporal/revision mutation | stale revision, future event, expired evidence, delayed correction, clock skew | Stale authority rejected; newer canonical event wins by defined rule |
| Structural mutation | missing/null/extra field, wrong type, duplicate key, truncation, schema mismatch, array reorder | Reject invalid packet or explicitly request repair |
| Event-system mutation | duplicate, loss, reorder, delay, replay, concurrent conflict, partial write | Deterministic, idempotent, revision-safe result |
| Compression mutation | omit goal, cause, negative decision, dependency edge, uncertainty, approval | Contract grader identifies the exact information loss |
| Context-pressure mutation | distractors, urgency, repeated low-authority request, correction after delay, long context | Canonical goal/state retained; dispatcher still enforces |
| Security mutation | prompt injection in evidence, provenance spoof, poisoned transferred AMC, human/machine projection mismatch | No unauthorized state promotion or executable side effect |
| Recovery mutation | rejection feedback removed/changed/delayed, resolver unavailable, restart after crash | Measure recovery turns, final state, and safe abstention |

Mutation strength should be calibrated. Easy obvious attacks can make a defense look stronger than it is; impossible or ambiguous mutations can make valid systems look broken.

Metamorphic testing is relevant because it defines expected relationships between related inputs instead of requiring an answer label for every wording. Recent logic-grounded work specifically tests consistency under formal equivalence: https://arxiv.org/abs/2605.23965

## Phase 5 — End-to-end agent evaluation

### Test tasks

Use real public-dataset workflows spanning discovery, license verification, evidence updates, dependency changes, recommendation, approval, and publication. Include ordinary, difficult, stale, contradictory, and adversarial cases. Keep development and held-out mutation templates separate.

### Primary outcomes

- invalid proposal rate;
- invalid execution rate;
- required-answer and action-parameter accuracy;
- authorization and stop-condition preservation;
- dependency-resolution accuracy;
- unsupported-claim and invented-link rate;
- appropriate abstention;
- recovery delay after a rejected or corrected action;
- final canonical state;
- total input/output tokens, model calls, compilation, and retrieval;
- pass^k or equivalent repeated-run reliability.

Task completion alone is insufficient. Tau-bench grades final database state and uses repeated-trial reliability because interactive agents can be inconsistent: https://arxiv.org/abs/2406.12045

### Experimental controls

- same model snapshot, tools, system policy, temperature, context and action budgets;
- paired task assignment and randomized condition order;
- frozen schemas, prompts, mutation operators, graders, and exclusions;
- raw outputs and rejected actions preserved;
- deterministic graders primary where possible;
- human-blinded grading for semantic preservation and inspectability;
- LLM judges used only after calibration against human labels;
- multiple runs nested within task, not counted as independent tasks.

### Statistical treatment

Use paired effect sizes and confidence intervals. Set the confirmatory sample after exploratory variance is known. Fifty trajectories remain only a planning estimate. Safety testing needs more targeted trials: with zero observed failures in 300 relevant trials, the simple rule-of-three upper 95% bound is still about 1%.

## Phase 6 — Security, human inspection, and transfer

### Security

Reconstruct relevant AgentDojo-style attacks against the AMC ingestion, projection, resolver, cross-agent transfer, and tool-use boundary. AgentDojo provides a dynamic tool-agent environment with untrusted data rather than a static prompt list: https://openreview.net/pdf?id=m1YYAQjO3w

Measure attack success and ordinary-task utility separately. Failure Space is itself an attack surface: an adversary may insert a fake prohibition or remove a real one.

### Human inspection

Blind reviewers to variant. Ask them to identify goal, current state, evidence, uncertainty, next action, approval status, contradiction, and prohibited action. Measure correctness, time, and confidence calibration. Readability without correctness is not success.

### Memory and transfer benchmarks

Reproduce at least one external open memory benchmark before trusting the local harness. LongMemEval covers extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention: https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html

Then test at least one smaller model and one different model family. A second implementation must consume the schema without access to the original projector internals.

NIST TEVV frames trustworthy AI evaluation around reliable measurements, metrics, and evaluation methods rather than one benchmark score: https://www.nist.gov/ai-test-evaluation-validation-and-verification-tevv

## Recommended execution order

1. Write the independent transition table and state validator.
2. Replace the 14-check script with a normal automated test suite.
3. Add exhaustive reachable-state and property-based dispatcher tests.
4. Run dispatcher code mutation analysis and close surviving critical mutants.
5. Specify event IDs, idempotency, replay, persistence, and concurrency behavior.
6. Add projector preservation contracts and component ablations.
7. Build the reusable mutation generator with explicit metamorphic oracles.
8. Run no-API variant Round A.
9. Run the small paid variant smoke test.
10. Freeze finalists and conduct exploratory real-trajectory testing.
11. Reproduce external memory and agent/security benchmark subsets.
12. Run human inspection and cross-model transfer.
13. Preregister and run the confirmatory comparison.
14. Request independent reproduction before making standard or safety claims.

## Immediate next implementation slice

The next bounded job should be **dispatcher test foundation**, not another live prompt experiment:

- transition-table oracle;
- `validate_state()` contract;
- exhaustive state/action matrix;
- property-based sequence tests;
- first ten critical code mutants;
- replay/idempotency design note.

This slice is local, deterministic, inexpensive, and likely to expose architectural gaps before more API money is spent.

## Run Result

**COMPLETED — RESEARCH AND TEST PLAN DEFINED.** Existing AMC experiments, dispatcher code, projector code, and the research protocol were reviewed. The remaining work is separated into deterministic enforcement, projection preservation, variant comparison, mutation testing, end-to-end evaluation, and external validation. No implementation or new API experiment was performed in this planning job.
