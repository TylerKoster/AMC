# AMC Round C oracle/leakage preflight specification v0.1

Status: frozen synthetic preflight specification; not a live-model result

Date: 2026-07-18

## Problem

Round B successfully exercised the live runner, dispatcher grading, randomized schedule, checkpointing, and six packet conditions. It did not distinguish independent reasoning well because the complete packet builders copied the fixture's expected next action and affected identifiers into the packet under different field names.

That is answer-value leakage even though the literal `expected` object was omitted. It does not make the recorded calls false; it narrows their interpretation to format handling under explicit answers.

## Objective

Before paid Round C calls, establish that:

1. packet builders receive only an input partition and cannot read the oracle partition;
2. no packet contains precomputed next-action or aggregate affected-ID fields;
3. affected identifiers have event-specific, machine-checkable semantics;
4. a strong structured-summary baseline retains legitimate evidence links and negative decisions;
5. omitted dependency, revision, decision, and audit facts are detected by deterministic contract graders;
6. resolver availability is reported separately from inline audit availability;
7. raw and gzip packet sizes are measured without implying model performance.

## Frozen impact semantics

An entity is affected only when a typed event effect changes one of its canonical fields from one value to a different value. Merely mentioning, targeting, or retrieving an identifier does not make it affected.

Task-level affected identifiers are the set union of direct event effects by entity type. Audit reconstruction additionally preserves event identity, revision order, event type, field name, and before/after values.

## Conditions

- `structured_summary_v2`: current state, requirements, typed evidence notes, negative decisions, a history reference, and an explicitly untrusted operator message. It contains no inline event ledger.
- `minimal_amc_v2`: current state plus typed entity links, decision ledger, recent event effects, history reference, and authority labeling.
- `full_history_control`: prior/current snapshots, all entities, decisions, and ordered event effects.

The structured summary is intentionally strong. If it preserves the same facts at lower cost, it should remain the control or replace the AMC component being tested.

## Prohibited oracle fields

Packets must not contain `expected`, `oracle`, `next_action`, `proposed_action`, aggregate `affected_*` fields, or aggregate `changed_*` fields. Raw evidence-to-claim edges and event effects are allowed because they are source facts from which an answer must be derived.

## Capability clauses

- `exact_dependency`: the packet reconstructs exactly the declared evidence-to-claim edges.
- `stale_history_resolution`: the packet identifies the current canonical revision rather than a stale revision.
- `negative_decision`: rejected, inactive, or superseded decisions retain exact identifiers, status, and reason code.
- `audit_reconstruction`: ordered event identities, revisions, types, and typed before/after effects are reconstructable inline.

A history reference is recorded separately. A resolver can make an omitted audit reconstructable during a live task, but its retrieval bytes, calls, latency, and failures must be counted.

## Targeted mutations

1. Remove dependency links.
2. Remove the current revision.
3. Reactivate a negative decision.
4. Remove audit effects.
5. Reverse audit order.
6. Inject a precomputed next-action field.

The preflight exits only if every targeted mutant is killed, every packet is deterministic, changing the oracle partition cannot change a packet, and no unmutated packet triggers the leakage detector.

## Scientific boundary

The four fixtures are synthetic and test the harness contract only. Deterministic information availability is not evidence that a model will use the information, resist pressure, request a resolver correctly, or outperform a structured summary. Round C still requires fresh real trajectories with frozen preservation contracts and randomized repeated live evaluation.
