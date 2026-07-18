# AMC Round C live-runner gate specification v0.1

## Decision

Paid Round C must not use the earlier in-process pattern where packet building, model execution, and grading share one runtime. It will use three bounded phases:

1. input-only packet construction and seeded scheduling;
2. model execution with atomic persistence of ungraded responses; and
3. a separate grader that validates completion before loading held-out contracts.

## Frozen protocol

- Inputs: `round_c_real_inputs_v1.json`, exact partition SHA-256 fixed by Experiment 012.
- Conditions: strong structured summary, minimal AMC, and full frozen-input control.
- Tasks: 10.
- Repetitions: 2 per condition and task.
- Planned calls: 60.
- Random seed: 13013.
- Model: `gpt-5.6-sol`.
- Tools, web access, handoffs, and tracing: disabled.
- Maximum turns: 1.

Changing any item requires a new protocol version before seeing model results.

## Packet contract

Every condition must be built from one task in the frozen input partition only. No builder accepts a held-out contract. The strong summary is not intentionally degraded. The deterministic audit must reconstruct the exact frozen task from every packet, find no prohibited oracle keys, and find no explicit condition label in model input.

## Schedule contract

The complete task × condition × repetition schedule is constructed first, shuffled with the frozen seed, assigned an immutable sequence number, and hashed. Every condition receives exactly 20 calls. The recorded schedule—not runtime grouping—controls execution order and resumption.

## Persistence boundary

The live executor must contain no grader import and no held-out-contract path. It writes each response through a same-filesystem temporary file, flushes and fsyncs it, then atomically replaces the checkpoint. A response artifact becomes gradeable only when all 60 structured responses exist and the final state is `responses-persisted-ungraded` with `responses_persisted=true`.

A partial or error checkpoint remains ungradeable. Resumption may reuse only successfully persisted structured responses whose protocol, input, capture, schedule, model, and call-count fields exactly match the frozen run.

## Grading boundary

The grading entry point must call the persisted-response loader first. That loader rejects partial, running, failed, or malformed artifacts. Only after it returns a complete artifact may the held-out contract loader be invoked. Grades are written to a new file and never back into raw responses.

Exact facts and source IDs are machine-scored. Required and forbidden actions use a preregistered token-containment rule because the frozen contracts contain semantic action identifiers but the model produces text. Decision-rule interpretation remains explicitly human-reviewed and unscored.

## Spend boundary

Importing or auditing the runner cannot make a call. Paid execution requires both `--execute-paid-round-c` and `--acknowledge-calls 60`. This gate does not authorize running those flags.

## Acceptance criteria

- 30/30 unique task-condition packets reconstruct the exact frozen task.
- Zero prohibited oracle keys or condition labels appear in packets.
- The 60-call schedule is balanced, deterministically randomized, and hash-recorded.
- Static tests establish that the executor does not import or reference the grader/contracts.
- Mutation tests establish that partial responses prevent contract loading.
- Atomic persistence and resumability checks pass.
- Full AMC regression suite passes.
- The no-model audit records zero OpenAI/model calls and zero contract-file loads.

## Scientific limit

Passing this gate shows that the experiment is preregistered, packet-faithful, randomized, and structurally protected against early oracle access. It says nothing about model performance or AMC superiority until the paid run is executed and analyzed.
