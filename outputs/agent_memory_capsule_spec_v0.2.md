# Agent Memory Capsule — Spec v0.2

Status: Pilot workflow confirmed; implementation not yet started

Date: 2026-07-17
Decision: Validate agent memory before document compression or agent-to-agent messaging.

## 1. Product thesis

Long-running agents lose useful state because raw histories are expensive to keep in active context, summaries discard operational details, and retrieved fragments often omit decisions or temporal relationships. An Agent Memory Capsule (AMC) is a portable, inspectable memory object that preserves the answers and actions required for a declared task while progressively loading supporting detail.

The product is not a general-purpose lossless compressor. It performs task-relative semantic compression.

## 2. Initial user and job

Primary user: a developer or operator of a long-running agent.

Job: pause, transfer, resume, or audit an agent without replaying its complete history.

Initial use cases:

1. Resume an interrupted agent task.
2. Transfer task state between agents sharing the same capsule protocol.
3. Inspect what an agent intends to do and why.
4. Retrieve evidence only when a decision or answer requires it.

## 3. Product ranking

1. Agent memory — MVP and primary value hypothesis.
2. Agent-to-agent messages — later transport profile using the same memory object.
3. Document compression — ingestion capability, not the initial product.

## 4. Design principles

- Preserve declared answers and executable actions, not every original word.
- Keep intention, planned actions, completed actions, and outputs human-readable.
- Never treat a generated summary as authoritative evidence.
- Preserve immutable references to source evidence and transformations.
- Load information progressively from intention to evidence.
- Declare uncertainty, contradictions, freshness, and expiry explicitly.
- Prefer a model-neutral structured representation over private latent vectors.
- Make every capsule independently testable.

## 5. Capsule layers

### Layer 0 — Human intention card

- Original goal
- Current interpretation of the goal
- Current status
- Next intended action
- Required approval or blocker
- Expected output

Target: readable in under one minute and fewer than 200 words.

### Layer 1 — Operational state

- Completed actions and outcomes
- Pending actions
- Dependencies and preconditions
- Tool and environment requirements
- Idempotency keys or duplicate-action guards
- Authorization boundaries
- Stop conditions

### Layer 2 — Semantic memory

- Stable facts
- Decisions and rationale
- User preferences explicitly observed
- Entities and relationships
- Contradictions
- Confidence, source, timestamp, and expiry per claim

### Layer 3 — Evidence index

- Source URI or content address
- Content hash
- License or access policy
- Relevant source span or record identifier
- Transformation history
- Retrieval instructions

### Layer 4 — Raw artifacts

Optional embedded files, conversation segments, tool outputs, or external immutable references.

## 6. Minimal logical schema

```json
{
  "format": "amc/0.1",
  "capsule_id": "...",
  "created_at": "...",
  "goal": "...",
  "intention": {
    "status": "...",
    "next_action": "...",
    "approval_required": false,
    "expected_output": "..."
  },
  "actions": [],
  "claims": [],
  "open_questions": [],
  "evidence": [],
  "semantic_tests": [],
  "human_projection": "...",
  "integrity": {
    "content_hash": "...",
    "signature": "..."
  }
}
```

Every claim must support source, confidence, observed/inferred status, timestamp, and optional expiry. Every proposed action must support authorization state, preconditions, expected effect, and duplicate-action protection.

## 7. Required behavior

### Create

Given a task history, the system produces a capsule and a human-readable intention card.

### Resume

Given only the capsule, a compatible agent can identify the goal, answer the declared preservation questions, state the next action, and avoid repeating completed external actions.

### Inspect

A human can determine what the agent believes, what it plans to do, what evidence supports it, and which statements are uncertain or inferred.

### Expand

The agent can retrieve deeper layers or raw evidence when a question cannot be answered safely from compressed state.

### Update

New observations create a versioned update. They do not silently overwrite conflicting memories.

## 8. Semantic preservation contract

Each capsule declares a test suite containing:

- Questions that must remain answerable.
- Actions that must remain executable or explicitly blocked.
- Facts that must be preserved exactly.
- Forbidden unsupported claims.
- Expected citations or evidence references.

A capsule passes only if a fresh agent, without the original history, satisfies the declared tests.

## 9. Human inspectability requirements

- Intention and outputs must be plain language.
- Every inferred claim must be labeled as inferred.
- No latent-only field may be required to understand intended behavior.
- Model-specific embeddings may be included only as optional indexes.
- Actions affecting external systems must remain explicit and reviewable.
- A human-readable diff must accompany every capsule revision.

## 10. MVP exclusions

- Lossless reconstruction of the full history.
- A new tokenizer or foundation model.
- Cryptocurrency or incentive design.
- Hidden agent languages.
- Autonomous execution across untrusted organizations.
- A universal ontology for all agent tasks.
- Standardization before the preservation experiment succeeds.

## 11. Validation experiment

Dataset: 50 completed agent trajectories from one bounded workflow.

For each trajectory:

1. Define preservation questions, required actions, and forbidden errors before compression.
2. Generate an AMC at three size targets.
3. Give the capsule to a fresh agent without the original history.
4. Test answers, next-action selection, duplicate-action avoidance, citations, and human auditability.
5. Compare with full history, a conventional summary, and retrieval over raw history.

Primary pass thresholds:

- At least 95% accuracy on required answers.
- 100% preservation of authorization and stop conditions.
- Zero repeated irreversible actions.
- Zero fabricated evidence references.
- At least 80% reduction in active context tokens.
- Human reviewer identifies intention and next action in under 60 seconds.
- Capsule generation plus retrieval costs less than replaying full history for the target workflow.

## 12. Failure criteria

Stop or redesign if:

- Operational errors increase relative to a conventional summary.
- Reviewers cannot distinguish observations from inferences.
- Cross-agent resumption requires the original model or hidden latent state.
- Compression savings disappear after evidence retrieval and decoder overhead are counted.
- Maintaining semantic tests costs more than the workflow value they protect.

## 13. Expansion path

If the memory experiment passes:

1. Define an agent-to-agent message profile that transmits capsule deltas.
2. Add domain-specific profiles and validators.
3. Add document ingestion that creates evidence-backed memory layers.
4. Test cross-model interoperability.
5. Consider an open specification only after two independent implementations interoperate.

## 14. Implementation discipline

- Begin on a dedicated branch such as `codex/agent-memory-capsule-poc`.
- Keep the first implementation local and fixture-driven.
- Separate schema, compressor, evaluator, and human renderer.
- Commit the schema and tests before optimizing compression.
- Do not publish a format or open a standards proposal until the MVP thresholds are met.

## 15. Confirmed pilot workflow

The first pilot is a multi-session public-dataset research and curation agent. The agent discovers, evaluates, rejects, shortlists, and documents datasets while preserving citations, source assessments, decisions, completed searches, and the remaining action queue.

Safety boundary: read-only research over public, explicitly accessible sources. The pilot does not publish datasets, submit upstream changes, create accounts, or perform irreversible external actions.

## 16. Required agent skills

Keep these as independently testable modules rather than one broad prompt:

1. **Source discovery** — find candidate datasets and record the exact query and discovery path.
2. **Source qualification** — assess authority, access method, freshness, geographic and subject coverage, and stated license.
3. **Dataset profiling** — inspect schema, file type, row counts, date coverage, nulls, identifiers, and update cadence without silently changing the source.
4. **Claim and evidence extraction** — turn observations into typed claims with citations, timestamps, confidence, and observed/inferred status.
5. **Decision ledger** — preserve accept, reject, defer, and revisit decisions with rationale.
6. **Action-state management** — track completed, pending, blocked, and approval-required actions with duplicate-action guards.
7. **Memory compilation** — produce progressively loaded AMC layers from the append-only trajectory.
8. **Memory resumption** — reconstruct the declared answers and next actions using the capsule without original history.
9. **Semantic evaluation** — run preservation questions, forbidden-error checks, citation checks, and baseline comparisons.
10. **Human rendering** — generate a plain-language intention card, evidence view, and version diff.

## 17. Minimum tool stack

### Runtime and contracts

- Python runtime for the reference implementation.
- JSON Schema 2020-12 for the portable capsule contract.
- A JSON Schema validation library and typed application models.
- A command-line interface; no web application is required for the pilot.

### Research and data inspection

- Read-only web/HTTP client with captured request URLs, timestamps, response status, and content hashes.
- Dataverse Search, Data Access, and metadata APIs as one source family.
- DuckDB for local inspection of CSV, JSON, and Parquet datasets.
- MIME/type detection, SHA-256 hashing, and safe size limits before parsing files.
- Optional browser automation only for public sources that cannot be evaluated through an API or direct download.

### State and evidence

- Append-only JSON Lines event log as the canonical trajectory.
- SQLite for local indexes, run metadata, and experiment results.
- Local content-addressed evidence directory keyed by SHA-256.
- Git for schema, fixture, prompt, and evaluator versioning.

### Evaluation and observability

- Deterministic test runner for schema, action, citation, and preservation tests.
- Structured traces linking every model call, tool call, claim, evidence record, and capsule version.
- Token, byte, latency, and model-call accounting.
- Human review worksheet with pass/fail fields and adjudication notes.

### Model access

- One capable model for research and memory compilation.
- The same model in a fresh context for the first resumption test.
- A cheaper or smaller model is useful as a harder decoder test, but is not required for v0.2.
- Model name, version, parameters, prompt version, and structured output must be recorded for every run.

## 18. Required data and people

### Evaluation corpus

- 50 completed research trajectories from the same bounded workflow.
- Three to five approved public source families, including one Dataverse installation.
- A predeclared answer/action contract for every trajectory.
- A conventional summary, retrieval-over-history, and full-history baseline for comparison.
- Deliberate fixtures containing stale sources, duplicated datasets, conflicting metadata, missing licenses, and changed schemas.

### Human resources

- One domain curator to define ground truth and adjudicate ambiguous source decisions.
- One agent/evaluation engineer to implement the schema, compiler, resumer, and test harness.
- One product owner to enforce scope and decide whether failures invalidate the thesis.
- Privacy/security review before using any non-public trajectory. Public-only data is mandatory for the first pilot.

One person can cover multiple roles, but the agent must not grade its own ambiguous semantic decisions without human adjudication.

### Expected experiment volume

- 50 source trajectories.
- Three capsule size targets per trajectory.
- At least three resumption repetitions per capsule target.
- Three baselines per trajectory.
- Approximately 900–1,500 model-assisted compile, resume, and evaluation runs, depending on retries.
- Approximately 25–40 curator hours for contracts, review, and disagreement resolution.

These are planning estimates, not pass criteria. Actual token and dollar budgets must be calculated after ten pilot trajectories.

## 19. Component boundary

```text
public sources
    -> research agent
    -> append-only trajectory + evidence hashes
    -> AMC compiler
    -> schema-validated capsule + human intention card
    -> fresh resumption agent
    -> deterministic semantic evaluator
    -> human adjudication report
```

The trajectory remains the audit source. The capsule is a derived, versioned artifact. The compiler may never delete or rewrite the trajectory.

## 20. Explicitly unnecessary for the pilot

- Vector database.
- Distributed message broker.
- Knowledge-graph database.
- Custom tokenizer or foundation-model training.
- Fine-tuning before prompt-and-schema baselines exist.
- MCP server.
- Cloud deployment or Kubernetes.
- Multi-organization identity federation.
- Latent-only memory fields.
- Autonomous publishing or write access to Dataverse.

These may become justified by measured bottlenecks. Adding them before the preservation experiment would reduce what the experiment can teach us.

## 21. Open decisions for v0.3

- Which two agent implementations will test portability?
- Should raw evidence be embedded, content-addressed, or both?
- What maximum capsule size should the MVP target?
- Which public Dataverse installation and two to four additional source families will form the approved source set?
- What exact research question defines a complete trajectory?
