# AMC Round B smoke test - Experiment 010

## Run Result

**COMPLETE - REGRADING CORRECTED AN AMBIGUOUS ORACLE.**

All 60 scheduled API calls completed with no call errors. The regrade used no API calls and preserved every raw decision.

Runtime: Python `3.14.4`, openai-agents `0.18.3`. The original process required termination after the complete result was written; explicit agent release was added for future runs without repeating paid calls.

| Condition | Core pass | Action | Exact IDs* | Invalid | High-risk | Mean B | Total tok | Median ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| state_vector | 10/10 | 10/10 | 2/2 | 0 | 0 | 936.4 | 7540 | 2601.992 |
| structured_summary_fixed | 10/10 | 10/10 | 2/2 | 0 | 0 | 581.4 | 6674 | 2379.945 |
| minimal_resolvable_amc | 10/10 | 10/10 | 2/2 | 0 | 0 | 1141.0 | 8087 | 2392.68 |
| deterministic_retrieval | 10/10 | 10/10 | 2/2 | 0 | 0 | 1424.8 | 8861 | 2506.127 |
| full_history_control | 10/10 | 10/10 | 2/2 | 0 | 0 | 1733.2 | 9511 | 2417.523 |
| incomplete_negative_control | 10/10 | 10/10 | 2/2 | 0 | 0 | 418.2 | 6270 | 2577.077 |

*Exact affected-ID grading is limited to the two repetitions of the evidence-invalidation task. The other four tasks used an ambiguous meaning of affected and are excluded from that metric.*

## Corrected finding

Every condition produced the exact expected action, goal, evidence state, requirement state, approval state, history behavior, and dispatcher outcome in all ten trials. No invalid or high-risk proposal occurred. The incomplete control requested history safely in all ten trials and was rejected from execution by the dispatcher as designed.

The earlier 2/10 full-pass values for retrieval and full history were grading artifacts. Those formats returned broader linked identifiers on events where affected was undefined. Compact formats echoed precomputed expected lists, so retaining that score would have favored them by construction.

## Exploratory elimination

Dominated candidate map: `{"deterministic_retrieval": ["minimal_resolvable_amc", "state_vector", "structured_summary_fixed"], "minimal_resolvable_amc": ["state_vector", "structured_summary_fixed"], "state_vector": ["structured_summary_fixed"]}`.

`structured_summary_fixed` is the only non-dominated behavioral candidate in this smoke test: it matched every observed behavior while using 6,674 total tokens. `state_vector` used 7,540, `minimal_resolvable_amc` 8,087, and `deterministic_retrieval` 8,861. This supports advancing the structured summary into Round C as the cost control; it does not show that audit links or history resolution are useless because this round did not exercise those benefits.

The generic structured summary averaged 581.4 serialized bytes, smaller than the 936.4-byte state vector because the latter repeated its full precondition table. This reverses the one-fixture raw-size ordering from Round A and is evidence that schema overhead must be measured across tasks.

## Actual API usage

SDK-reported usage: `{"cache_write_tokens": 0, "cached_input_tokens": 0, "input_tokens": 41338, "output_tokens": 5605, "reasoning_tokens": 0, "requests": 60, "total_tokens": 46943}`.

Estimated cost: `{"estimated_usd": 0.37484, "input_per_million": 5.0, "method": "All input tokens priced at the uncached rate; output tokens at listed rate.", "output_per_million": 30.0, "retrieved_date": "2026-07-17", "source": "https://developers.openai.com/api/docs/models"}`. This is an estimate, not an invoice. Pricing source: [OpenAI model catalog](https://developers.openai.com/api/docs/models).

## Next test

Round C should compare the structured summary against a revised minimal AMC only on tasks that require an exact dependency edge, stale-versus-current history resolution, negative decisions, or audit reconstruction. Define event-specific impacted-ID semantics before running. Ordinary clean workflow tasks add cost without testing what AMC claims to preserve.

The harness follows the official [Agents SDK quickstart](https://developers.openai.com/api/docs/guides/agents/quickstart) and [agent evaluation guidance](https://developers.openai.com/api/docs/guides/agent-evals).

## Artifacts

- Raw result: `pilot\live_eval\results\round_b_smoke_latest.json`
- Corrected result: `pilot\live_eval\results\round_b_smoke_regraded_latest.json`
- Frozen tasks: `pilot/live_eval/evals/round_b_smoke_tasks_v1.json`
- Harness: `pilot/live_eval/round_b_smoke.py`
