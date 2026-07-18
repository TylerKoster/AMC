# AMC Round C oracle/leakage preflight - Experiment 011

## Run Result

**COMPLETE - deterministic synthetic preflight only.** No model or network calls were used.

This run fixes the Round B measurement weakness where complete packets contained precomputed answer fields. Round B remains evidence that the runner and formats were interpreted consistently; it is not evidence that the model independently resolved the answers.

| Condition | Contract passes | Raw bytes | Gzip bytes | Oracle leaks |
|---|---:|---:|---:|---:|
| structured_summary_v2 | 3/4 | 2797 | 1502 | 0 |
| minimal_amc_v2 | 4/4 | 5226 | 2253 | 0 |
| full_history_control | 4/4 | 5389 | 2121 | 0 |

## Oracle rule

An identifier is affected only when a typed event effect changes one of its canonical fields. Merely mentioning an identifier does not make it affected. Task-level impact is the set union of those direct field transitions, while audit order remains event order.

## Mutation result

Killed 6/6 targeted preflight mutants.

## Interpretation

The structured summary is a strong baseline: it retains typed evidence links and negative decisions instead of being deliberately weakened. It lacks inline event effects, so audit reconstruction requires its history resolver. The minimal AMC carries recent typed deltas inline at additional byte cost. This is an information-availability result, not a model-performance result.

## Next gate

Do not run the ten-trajectory paid Round C comparison yet. First collect fresh real trajectories and freeze task-specific preservation contracts. The live runner must build every packet from the input partition only, keep the oracle inaccessible, allow resolver requests, and count retrieved bytes and calls.

Suite SHA-256: `ab7a054071ce4336106adbde131121f682a97ce219ad236c3276d04f6e1870e4`
