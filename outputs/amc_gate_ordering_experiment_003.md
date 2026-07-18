# AMC gate-ordering experiment 003

## Question

Does adding an explicit workflow gate graph to the compact AMC improve an agent's ordering of evidence repair, license verification, recommendation, approval, and publication? How much file size does it add?

## Live method

- Model: `gpt-5.6-sol`
- Three isolated runs per condition
- Same events, prompt, action vocabulary, and structured output contract
- No tools, web access, or shared conversation state

## Observations

| Condition | JSON size | Gzip size | Repeated observations |
|---|---:|---:|---|
| Summary + events | 339 B | 238 B | 5/6, 5/6, 5/6 |
| Full AMC + events | 2,620 B | 1,083 B | 6/6, 6/6, 6/6 |
| Compact AMC | 782 B | 419 B | 6/6, 6/6, 6/6 |
| Gated compact AMC | 900 B | 427 B | 6/6, 6/6, 6/6 |

The summary preserved the correct workflow but replaced the research goal with “publish a shortlist including Candidate A” in all three runs. The other conditions retained the original city-tree research goal.

Adding the workflow graph cost 118 minified JSON bytes. It produced no observable improvement over the ordinary compact AMC in this scenario: both produced the same states and order in all three runs.

## Interpretation

The negative result is useful. Repeating deterministic execution policy inside every model-facing AMC may not justify its size. A better separation is:

- AMC: current facts, dependencies, intention, and restrictions for model/human inspection;
- dispatcher: deterministic action prerequisites and authorization enforcement;
- event log: accepted and rejected action attempts, approvals, invalidations, and revisions.

The gate graph can remain available as an inspectable debug projection without being included in every model request.

## Downstream dispatcher experiment

`pilot/gate_dispatcher.py` implements a small deterministic policy layer. It:

- rejects approval requests before evidence, license, and recommendation are ready;
- rejects publication before a valid approval;
- binds approval to the exact workflow revision;
- rejects an approval for the wrong revision;
- revokes approval when evidence changes;
- records accepted and rejected attempts as readable events.

This enforcement does not depend on a model interpreting prose correctly.

## Limits

This remains one synthetic workflow and a supplied action vocabulary. The live result does not show that the gated packet is generally unnecessary. It shows only that it added no observable benefit in this controlled case, while deterministic enforcement remains valuable for side-effecting actions.
