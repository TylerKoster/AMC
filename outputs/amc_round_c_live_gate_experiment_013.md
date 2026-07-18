# AMC Round C live-runner gate - Experiment 013

## Run Result

**COMPLETE - no-model packet audit. Paid Round C was not started.**

- Gate pass: True
- Frozen tasks: 10
- Preregistered paid calls: 60
- Random seed: 13013
- Schedule SHA-256: `6170821c096dcb66316950ff4421fa8d9a2b90e6c9be2a669c6b0891217463c1`
- Protocol SHA-256: `45bee1ef196a55f8609aa8b9ac42c2cd9669cb4364141ead6cd7e05eb166eb9e`
- OpenAI/model calls in this audit: 0
- Held-out contract files loaded in this audit: 0

| Condition | Fidelity | Oracle-key leaks | Label leaks | Raw bytes | Gzip bytes |
|---|---:|---:|---:|---:|---:|
| structured_summary_v2 | 10/10 | 0 | 0 | 18513 | 9489 |
| minimal_amc_v2 | 10/10 | 0 | 0 | 18147 | 9434 |
| full_input_control | 10/10 | 0 | 0 | 18533 | 9504 |

## Architecture gate

Packet construction reads only the frozen input partition and preregistered protocol. The live executor saves raw structured decisions atomically and contains no grader or held-out-contract import. A separate grading process first validates a complete persisted response artifact; only then may it load the held-out contracts.

## Interpretation

This establishes packet fidelity, deterministic randomized ordering, balanced exposure, and execution/grading separation. It does not establish model quality, statistical power, cost, or AMC superiority because no model was called.

The minimal AMC packet is only 1.977% smaller raw and 0.58% smaller under gzip than the strong structured summary. This is not a meaningful document-compression result; any Round C value must come from preservation behavior or operational structure, not this byte difference.

## Paid-run stop rule

The executor requires an explicit paid-run flag and acknowledgement of the exact preregistered call count. Do not run it until this gate and the stacked source-corpus PR are reviewed.
