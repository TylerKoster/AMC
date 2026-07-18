# AMC Variant Tournament — Experiment 009, Round A

## Run Result

**COMPLETE — deterministic screening only.** No OpenAI API or network calls were used.

Tested 18 variants against 7 safety, 5 execution, and 3 audit clauses. 10 variants passed the safety gate; 8 failed.

## Result table

| Variant | Raw B | Gzip B | Est. tokens* | Safety | Execution | Audit | Frontier |
|---|---:|---:|---:|---:|---:|---:|:---:|
| checksum_only | 118 | 121 | 30 | 0/7 | 0/5 | 0/3 |  |
| freeform_summary | 141 | 131 | 36 | 1/7 | 0/5 | 0/3 |  |
| last_two_events | 179 | 130 | 45 | 2/7 | 0/5 | 0/3 |  |
| delta_only | 243 | 167 | 61 | 2/7 | 0/5 | 1/3 |  |
| freeform_summary_plus_events | 331 | 224 | 83 | 3/7 | 0/5 | 0/3 |  |
| state_vector | 512 | 302 | 128 | 7/7 | 2/5 | 0/3 | yes |
| structured_summary | 536 | 338 | 134 | 6/7 | 3/5 | 1/3 |  |
| structured_summary_fixed | 561 | 353 | 141 | 7/7 | 3/5 | 1/3 | yes |
| incomplete_compact | 684 | 392 | 171 | 6/7 | 3/5 | 1/3 |  |
| minimal_resolvable_amc | 700 | 372 | 175 | 7/7 | 5/5 | 1/3 | yes |
| compact_amc | 782 | 418 | 196 | 7/7 | 4/5 | 1/3 |  |
| compact_machine_constraints | 788 | 417 | 197 | 7/7 | 4/5 | 1/3 |  |
| compact_gated | 900 | 421 | 225 | 7/7 | 4/5 | 1/3 |  |
| negative_paraphrase | 911 | 465 | 228 | 7/7 | 2/5 | 0/3 |  |
| compact_failure_space | 929 | 475 | 233 | 7/7 | 4/5 | 1/3 |  |
| deterministic_retrieval | 2104 | 863 | 526 | 7/7 | 3/5 | 3/3 | yes |
| full_amc | 2422 | 1014 | 606 | 4/7 | 3/5 | 3/3 |  |
| full_amc_plus_events | 2612 | 1068 | 653 | 7/7 | 3/5 | 3/3 |  |

*Estimated tokens are `ceil(raw bytes / 4)`, not tokenizer output. Raw bytes are authoritative.*

## What survived Round A

The non-dominated frontier is: `deterministic_retrieval`, `minimal_resolvable_amc`, `state_vector`, `structured_summary_fixed`.

- `state_vector` is the smallest safety-passing packet at 512 bytes, but it has no audit facts and no exact dependency edge.
- `structured_summary_fixed` is 561 bytes. Adding one typed `license_verified: false` field repaired the original summary's safety failure.
- `minimal_resolvable_amc` is 700 bytes, passes all safety and execution clauses, and retains a history reference. It is the strongest compact candidate for the next live round.
- `deterministic_retrieval` is 2104 bytes and retains all audit facts, but does not precompute every current consequence.

## Eliminations and diagnostics

- The plain full AMC failed because it did not include the later invalidation and revocation events. A snapshot without its deltas is stale.
- Delta-only failed as a standalone handoff. It is a transport optimization that requires a verified base resolver.
- The gated, machine-constraint, Failure Space, and negative-paraphrase variants added no new mechanically preserved facts over smaller packets in this case.
- Failure Space remains a live-model diagnostic; Round A does not show that its extra prose improves model behavior.
- The incomplete compact control failed when approval state and dependency links were removed, confirming that small packets can become dangerously incomplete.

## Size findings

`minimal_resolvable_amc` is 73.201% smaller than full AMC plus events and 10.486% smaller than the prior compact AMC.

Across two equal temporal endpoints, base-plus-delta used 2601 bytes versus 5034 for repeating full state, a 48.331% reduction. Delta is not independently portable.

Two compact current-state snapshots used 1400 bytes, a 72.189% reduction versus full repetition. They rely on the referenced history for omitted audit detail.

## Scientific boundary

This round proves only deterministic preservation and byte size on one fixture. It does not prove that an AI will interpret the variants equally, drift less, or take safer actions. Those claims require blinded live-model evaluation across multiple task families, randomized order, repeated trials, and dispatcher-observed outcomes.

## Next experiment

Advance the four frontier variants to a blinded live-model round. Keep the dispatcher authoritative and compare exact action validity, dependency resolution, goal retention, recovery after injected slips, latency, and actual API token usage. Use full AMC plus events as the high-information control and the incomplete compact packet as the negative control.

## Artifacts

- Metrics: `outputs\amc_variant_tournament_round_a_009.json`
- Inspectable packets: `outputs\amc_variant_tournament_round_a_009_packets.json`
- Generator: `pilot/amc_variant_tournament.py`
- Tests: `pilot/tests/test_amc_variant_tournament.py`
