# AMC Round C source-backed trajectory protocol v0.1

## Purpose

Freeze the evidence and preservation contracts for paid Round C before any model sees the tasks. This protocol reduces four avoidable biases: invented task context, stale or ambiguous source identity, answer leakage, and changing the scoring contract after observing results.

## Terminology boundary

This corpus contains **real external-source retrieval trajectories**: actual HTTP requests to official publisher endpoints, response metadata, normalized observations, and response hashes. It does not contain natural AI-behavior trajectories. Model behavior becomes observable only during the later paid comparison.

## Inclusion criteria

Every case must:

1. use exactly one official primary publisher endpoint;
2. complete a fresh HTTP retrieval after this protocol is frozen;
3. retain requested and final URLs, UTC retrieval time, HTTP status, content type, byte count, response SHA-256, ETag, and Last-Modified when supplied;
4. extract a bounded set of machine-checkable observations from the response;
5. declare any operator pressure or workflow mutation as injected test state rather than observed external fact;
6. define exact required facts, required actions, forbidden actions, source references, and a decision rule;
7. store input and oracle in physically separate files; and
8. remain usable without saving publisher response bodies.

The corpus must contain ten cases across at least eight distinct portal or API families. A failed, blocked, oversized, or unparsable primary response prevents freezing; it is not silently replaced with remembered facts.

## Collection procedure

1. Freeze the source manifest and contract templates.
2. Retrieve each declared source with a named research user agent, a 30-second timeout, and a 5 MiB response cap.
3. Hash the exact response bytes before discarding them.
4. Extract only declared observations using source-specific deterministic parsers.
5. Fill each required fact with the captured value and the primary response hash.
6. Validate case identity, family diversity, HTTP success, required values, hash shape, and input/oracle separation.
7. Write the capture, input partition, oracle partition, and run report once. Overwrite is refused unless explicitly forced.

## Preservation contract

A contract is frozen before paid calls and contains:

- exact source-backed facts that must survive a handoff;
- all source identifiers that must remain inspectable;
- actions a continuation must require;
- actions a continuation must refuse or warn against;
- the rule connecting evidence to the decision; and
- a resolver reference to the capture record.

The contract is a grading instrument, not an instruction presented to the model. The live runner may load only the input partition while constructing prompts. It may load the oracle partition only after it has durably saved the model response.

## Mutation and leakage gates

Before paid Round C, tests must establish that:

- removing any required observation causes validation failure;
- changing a response hash breaks the fact/source binding;
- input construction is invariant to any change in the oracle file;
- oracle-like keys are absent from the input partition;
- case IDs and ordering agree across capture, input, and oracle partitions; and
- response bodies are not committed.

## What this can and cannot establish

Passing this protocol establishes that the benchmark tasks are source-backed, the contracts were frozen first, and the answer oracle is structurally separated. It does not establish that the contracts are universally correct, that source policies have been legally interpreted, that the cases represent all agent workflows, or that AMC improves performance. Those remain empirical or expert-review questions.

## Stop conditions

Do not start paid Round C if any primary source cannot be freshly retrieved, a required value is missing, an input contains oracle fields, a contract changes after model output is seen, or the live runner can access the oracle during packet construction.
