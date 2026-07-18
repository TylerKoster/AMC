# Agent Memory Capsule (AMC)

AMC is an experimental, inspectable handoff format for preserving an agent's defined answers, required actions, evidence links, approvals, and forbidden actions across task transitions.

This repository contains the current specification, deterministic dispatcher and storage prototypes, mutation tests, and API-backed comparison experiments. It is research software—not evidence that AMC improves agent performance in production.

## Repository map

- `outputs/` — specifications, experiment plans, evidence tables, and run reports.
- `pilot/` — capsule fixtures, compact projections, dispatcher logic, SQLite adapters, and deterministic tests.
- `pilot/live_eval/` — optional OpenAI API-backed comparison runners and saved experiment results.
- `pilot/live_eval/evals/round_c_real_inputs_v1.json` — frozen source-backed Round C inputs; preservation oracles are stored separately.

## Run deterministic tests

```powershell
python -m pip install -r .\pilot\requirements-dev.txt
python -m pytest .\pilot\tests -q
```

## Run API-backed evaluations

Set `OPENAI_API_KEY` in your environment; never save the key in this repository. Then install the evaluation package and run an individual experiment:

```powershell
python -m pip install -e .\pilot\live_eval
python .\pilot\live_eval\run_local.py
```

See [`pilot/README.md`](pilot/README.md) and [`pilot/live_eval/README.md`](pilot/live_eval/README.md) for scope, commands, and limitations.

## Evidence standard

Deterministic tests establish only that the current code satisfies its encoded contract and kills the included mutations. API-backed results are experimental observations under their recorded conditions; they are not general proof of superiority, safety, compression, or production durability.

Experiment 012 freezes ten fresh official-source retrieval trajectories and held-out preservation contracts before paid Round C. It makes no model-performance claim and used no OpenAI calls.

Experiment 013 adds an oracle-blind live executor, atomic ungraded-response persistence, seeded condition order, and a separate post-persistence grader. Its committed audit is a zero-model readiness check, not a paid Round C result.
