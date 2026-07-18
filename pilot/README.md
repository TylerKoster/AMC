# AMC Pilot Harness

Status: executable dry run; not evidence that AMC improves agent performance.

## Purpose

This harness tests whether a proposed Agent Memory Capsule contains the minimum information a new agent would need to continue a public-dataset research task safely.

It checks structure and safety-critical fields. It does **not** yet test whether a fresh model can answer better than a normal summary. That requires a separate, clean model context or API-backed runner.

## The first pilot task

Find and assess public datasets for a stated research need. Record sources considered, decisions, evidence, completed searches, open questions, and the next safe action.

The fixture is deliberately synthetic. It exercises the contract without representing a real completed research finding.

## Run

```powershell
python pilot/run_contract_checks.py
```

## What counts as a pass here

- The capsule has an explicit goal, status, next action, and expected output.
- Critical claims name evidence and say whether they are observed or inferred.
- Completed actions have duplicate-action guards.
- Approval-required actions do not claim that approval is already granted.
- The contract’s required answers, required actions, and forbidden actions are all declared.

## What this does not prove

- That an AI can resume from the capsule.
- That the capsule beats a conventional summary.
- That its claimed token savings survive evidence retrieval.
- That it resists memory poisoning.

Those are the next experiment, after a clean model runner is available.
## Event-trigger drill

`run_event_trigger_checks.py` is a local, deterministic experiment showing why AMC needs an event environment: expired evidence invalidates a dependent claim and a revoked approval blocks publication. It does not call a model or network service.

`run_compact_projection_checks.py` verifies that the compact software projection stays smaller while retaining exact evidence-to-claim links, revoked approvals, and a resolver reference to full history.

`run_gate_dispatcher_checks.py` verifies that a downstream software gate—not the language model—rejects premature actions, binds approval to the exact state revision, and revokes approval when evidence changes.

## Dispatcher assurance suite

The primary deterministic dispatcher suite uses an independent reference model, bounded state enumeration, generated rule sequences, and source-level critical mutants.

```powershell
python -m pip install -r .\pilot\requirements-dev.txt
python -m pytest .\pilot\tests -q
```

The suite verifies the v0.1 transition contract and local reference adapters. Production durability, real provider behavior, and exactly-once external effects remain unestablished.

`event_dispatcher.py` now implements command IDs, in-process idempotency, expected-revision conflicts, command fingerprints, hash-chained events, verified full replay, and restoration from a supplied verified stream. By itself, that module does not durably store the stream or provide database transactions, multi-process locking, signed event roots, or an external-side-effect outbox.

`sqlite_event_store.py` is a local transactional reference adapter. It persists the verified event stream, reconstructs state and idempotency across restart, rolls back injected pre-commit failures, and supports verified checkpoints. It does not establish production durability.

`sqlite_outbox.py` adds a local publication-outbox reference and fake idempotent/non-idempotent executors. The tests show that an outbox provides recoverable at-least-once delivery; exactly-once physical effects require a durable external-provider idempotency contract.

Run the local snapshot benchmark with:

```powershell
python .\pilot\run_snapshot_replay_checks.py
```
