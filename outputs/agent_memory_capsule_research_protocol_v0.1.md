# Agent Memory Capsule — Research Protocol v0.1

Status: Research design; no claim that AMC works has been established

Date: 2026-07-17
Scope: Multi-session public-dataset research and curation agents

## 1. Purpose

This protocol defines the research required before claiming that an Agent Memory Capsule (AMC) is novel, scientifically grounded, safer, more efficient, or more useful than existing memory approaches.

The central discipline is falsification. The study must be capable of concluding that AMC adds no value, that its preservation contract is invalid, or that its compression creates unacceptable operational or security failures.

## 2. Claims that are not yet established

The following remain hypotheses:

- A portable semantic memory object is better than a conventional summary or retrieval system.
- Declared answers and actions can be preserved at materially lower context cost.
- Human-readable intention cards improve correct human understanding.
- A capsule can prevent duplicate actions and preserve authorization boundaries.
- The proposed combination is sufficiently different from existing memory systems and research-object formats.
- Results from public-dataset research generalize to other agent workflows.

No public description should convert these hypotheses into facts before confirmatory results and independent reproduction exist.

## 3. Evidence policy

### 3.1 Evidence hierarchy

Use evidence in this order:

1. Independently reproduced, peer-reviewed empirical work.
2. Peer-reviewed primary research with available methods, code, and data.
3. Primary preprints with available methods, code, and data.
4. Formal standards and official technical documentation.
5. Vendor benchmark claims and product documentation, labeled as unverified claims.
6. Commentary, social posts, and marketing only as leads, never as proof.

### 3.2 Claim ledger

Maintain an append-only claim ledger. Every material claim must include:

- Claim identifier and exact wording.
- Claim type: observation, inference, hypothesis, external finding, or decision.
- Supporting and contradicting sources.
- Publication and peer-review status.
- Population, task, model, and environment studied.
- Metric, effect size, uncertainty, and limitations.
- Replication status.
- Current confidence and expiration/review date.

When evidence conflicts, retain both claims and record the adjudication. Never silently overwrite history.

## 4. Research questions

### Prior art and construct questions

- RQ1: How do existing agent-memory systems define episodic, semantic, procedural, working, and external memory?
- RQ2: Which parts of AMC already exist in memory systems, research-object packaging, provenance standards, workflow checkpoints, or agent protocols?
- RQ3: Can task-relative semantic preservation be defined with sufficient agreement between independent human curators?

### Effectiveness questions

- RQ4: Does AMC preserve required answers as accurately as full history, last-k context, conventional summaries, and retrieval over raw history?
- RQ5: Does AMC preserve action selection, action parameters, stop conditions, authorization state, and negative decisions?
- RQ6: Does AMC improve abstention when required evidence is absent or conflicting?
- RQ7: Does AMC reduce active context, latency, and total inference consumption after compilation and evidence retrieval are counted?

### Human and operational questions

- RQ8: Can humans correctly identify an agent's goal, status, evidence, uncertainty, and next intended action from the capsule?
- RQ9: How does memory quality change after repeated updates, contradictions, source changes, and long delays?
- RQ10: Do results transfer across model versions and at least one different model family?

### Safety questions

- RQ11: Can untrusted dataset content poison persistent memory or alter future agent behavior?
- RQ12: Can stale, spoofed, or incorrectly attributed evidence survive compression as trusted memory?
- RQ13: Can a malformed or adversarial capsule bypass authorization or human inspection?

## 5. Systematic evidence review

Conduct a transparent scoping/systematic review before implementation claims.

### 5.1 Search domains

- ACL Anthology, ICLR/OpenReview, ICML/PMLR, NeurIPS, ACM Digital Library, IEEE Xplore, arXiv, Crossref, and OpenAlex.
- Search official standards from W3C, NIST, JSON Schema, RO-Crate, DataCite, and relevant repository communities.
- Record database, exact query, date, filters, returned count, deduplication, and exclusion reason.

### 5.2 Required topic clusters

- Agent and conversational memory architectures.
- Cognitive memory taxonomies and continual learning.
- Context compression, summarization, retrieval, and hierarchical memory.
- Action-oriented and tool-use memory evaluation.
- Temporal reasoning, updates, contradictions, selective forgetting, and abstention.
- Semantic compression and information-theoretic limits.
- Provenance, research-object packaging, content addressing, and workflow checkpoints.
- Human interpretability and human evaluation of AI systems.
- Prompt injection, memory poisoning, data poisoning, and persistent-state security.
- Reproducibility and evaluation methodology for stochastic models.

### 5.3 Review procedure

- Publish inclusion/exclusion criteria before screening.
- Use PRISMA 2020 as the reporting structure and flow record, adapted transparently for computing research.
- Have a second reviewer independently screen a meaningful sample and adjudicate disagreements.
- Extract study design, tasks, models, baselines, metrics, sample sizes, code/data availability, limitations, and replication status.
- Separate peer-reviewed findings from preprints and vendor claims in every synthesis.

### 5.4 Review outputs

- Prior-art matrix.
- Memory-function taxonomy.
- Benchmark and metric catalog.
- Security threat catalog.
- Evidence gaps and explicit novelty-risk assessment.
- Claim ledger with source snapshots and hashes when permitted.

## 6. External benchmark replication

Before trusting the local harness, reproduce relevant portions of established benchmarks.

### Required benchmark constructs

- LongMemEval: extraction, multi-session reasoning, temporal reasoning, knowledge updates, and abstention.
- MemoryAgentBench: retrieval, test-time learning, long-range understanding, and selective forgetting.
- Mem2ActBench: use of memory to choose tools and ground action parameters.
- LoCoMo or an equivalent multi-session benchmark: long-range temporal and causal consistency.
- A memory-poisoning benchmark or reconstructed attack suite for persistent-state integrity.

### Replication gate

The local harness must reproduce at least one published open implementation within a preregistered tolerance. If it cannot, resolve the discrepancy before evaluating AMC. Vendor-reported benchmark scores are not accepted as ground truth without reproduction.

## 7. Construct validation

Define semantic preservation operationally. Do not use the unmeasurable phrase "same meaning."

Every trajectory must declare a preservation contract covering:

1. Exact facts and identifiers.
2. Accepted, rejected, deferred, and superseded source decisions.
3. Temporal order, freshness, and source version.
4. Unresolved questions and known unknowns.
5. Completed and pending actions.
6. Action parameters, prerequisites, approvals, and stop conditions.
7. Evidence citations and content hashes.
8. Contradictions and uncertainty.
9. Information that must be forgotten, expired, or excluded.
10. Forbidden unsupported claims and forbidden actions.

Two independent curators should author or review contracts for a double-coded subset. Report agreement by field and an appropriate agreement statistic. Low agreement indicates an invalid or underspecified construct, not an agent failure.

## 8. Corpus development

### 8.1 Exploratory corpus

Begin with ten real, completed public-dataset research trajectories. Use them to refine the schema, error taxonomy, annotation rubric, and variance estimates. Results are exploratory and cannot be used as confirmatory evidence.

### 8.2 Confirmatory corpus

After the exploratory protocol is frozen, perform a power or precision analysis to choose the confirmatory sample size. Fifty trajectories are a starting planning estimate, not a scientifically guaranteed sample.

Include:

- Real public-source trajectories.
- Multiple source families and jurisdictions.
- Routine and difficult cases.
- Stale links, duplicates, conflicting metadata, missing licenses, schema drift, renamed datasets, and inaccessible sources.
- Temporal holdouts created after prompts and evaluators are frozen.
- Adversarial fixtures kept separate from ordinary performance results.

Archive permitted source material or retain immutable references, timestamps, request metadata, and hashes. Publish a dataset card describing collection, exclusions, licensing, risks, and known biases.

## 9. Controlled experiment

### 9.1 Conditions

Compare at minimum:

- Full available history.
- Last-k or sliding-window history.
- Conventional structured or recursive summary.
- Deterministic lexical retrieval over raw history.
- At least one published/open memory baseline that can be reproduced.
- AMC at three context budgets.

Do not compare AMC only with a weak straw baseline.

### 9.2 Controls

- Same model and model snapshot where available.
- Same tools, system instructions, evidence access, temperature, and output constraints.
- Same maximum context and action budget unless the condition explicitly varies it.
- Frozen prompts, schemas, retrieval settings, and evaluator versions for confirmatory testing.
- Randomized condition order and blinded condition labels for human reviewers.
- Multiple independent runs because agent outcomes are stochastic.
- Separate development and held-out test trajectories.
- Record all failures, retries, refusals, malformed outputs, and excluded runs.

### 9.3 Ablations

Remove one AMC component at a time:

- Human intention card.
- Evidence hashes and citations.
- Decision ledger.
- Temporal fields and expiry.
- Negative/rejected-source memory.
- Authorization and duplicate-action guards.
- Semantic preservation tests.

Ablations determine which components create value and prevent attributing gains to the entire package without evidence.

## 10. Outcomes and analysis

### 10.1 Primary outcomes

- Required-answer accuracy.
- Correct action/tool selection.
- Action-parameter accuracy.
- Preservation of authorization, stop, and duplicate-action constraints.
- Evidence precision and evidence recall.
- Unsupported-claim rate.
- Appropriate abstention rate.
- Active-context reduction after retrieval.

### 10.2 Secondary outcomes

- End-to-end task success.
- Compilation and resume latency.
- Total input/output tokens and model calls.
- Evidence-retrieval frequency and size.
- Capsule update stability and contradiction handling.
- Human comprehension accuracy, time, and confidence.

### 10.3 Statistical plan

- Use a paired design because every trajectory is evaluated under each condition.
- Treat repeated runs as nested within trajectory; do not report them as independent samples.
- Report effect sizes and confidence intervals, not only averages or p-values.
- Use paired bootstrap intervals or an appropriate mixed-effects model for repeated binary and continuous outcomes.
- Predeclare noninferiority margins before confirmatory analysis.
- Correct for multiple comparisons or label secondary comparisons exploratory.
- Report per-category and worst-case performance, not only aggregate scores.
- Publish the full error distribution and negative results.

Suggested primary hypothesis: AMC is noninferior to the strongest reproduced baseline on task success within a justified margin while reducing active context by at least 80%. The margin must be chosen with domain and safety input; five percentage points is a candidate, not a fact.

### 10.4 Safety-rate interpretation

Zero observed failures is not proof of zero risk. With zero failures in 50 independent trials, the approximate upper 95% bound remains about 6% (the rule of three). Demonstrating a rate below roughly 1% with zero observed failures requires about 300 relevant trials; below 0.1% requires about 3,000. Safety-critical claims therefore need a larger targeted test suite than the product-effectiveness pilot.

## 11. Human-factors study

For a randomized, blinded sample, ask reviewers to identify:

- The original goal and current status.
- The next intended action.
- Required approval and stop conditions.
- Which claims are observed versus inferred.
- Which evidence supports each critical decision.
- Current contradictions and unresolved questions.

Measure correctness and completion time. Do not equate readability or reviewer confidence with correct understanding. Use at least two reviewers on a double-coded subset, report agreement, and adjudicate disagreements.

LLM-as-a-judge may be used for low-risk screening only after calibration against human labels. It must not be the sole evaluator of semantic preservation, inspectability, or safety.

## 12. Security research

Threat-model capsule creation, storage, retrieval, update, rendering, and resumption.

Required adversarial tests:

- Prompt injection embedded in dataset pages, metadata, files, and citations.
- Memory poisoning through repeated or high-salience untrusted claims.
- Instruction-like text incorrectly promoted from evidence to operational memory.
- Provenance spoofing and citation substitution.
- Stale trusted memory overriding newer evidence.
- Conflicting identities or dataset aliases.
- Malformed capsules, oversized fields, recursive references, and parser differentials.
- Unauthorized action inserted during compression or update.
- Human projection that hides a conflicting machine-readable action.
- Poisoned capsule transfer between agents.

Trust boundaries must distinguish user instructions, system policy, agent inference, and untrusted source content. Security results must be reported separately from normal accuracy.

## 13. Longitudinal and portability research

After the same-model experiment passes:

- Resume from capsules after delays and source updates.
- Apply repeated update cycles and measure memory drift.
- Introduce corrections and verify that superseded claims remain auditable but inactive.
- Test one smaller model and one different model family.
- Test whether a second implementation can consume the schema without access to the original compiler.
- Measure whether portability requires model-specific prompts, embeddings, or hidden state.

Failure to transfer must narrow the portability claim; it must not be described as universal agent memory.

## 14. Reproducibility requirements

Before confirmatory data collection:

- Preregister hypotheses, outcomes, exclusions, baselines, sample plan, stopping rules, and analysis.
- Tag and archive the exact research protocol.
- Version prompts, schemas, evaluators, model identifiers, dependencies, and environment configuration.
- Record random seeds where supported and disclose where deterministic replay is impossible.
- Preserve raw model outputs, tool traces, failures, and adjudication records subject to licensing and privacy.
- Publish code, synthetic fixtures, test contracts, and analysis scripts where permitted.
- Use content hashes for every source snapshot and derived artifact.
- Separate exploratory analyses from preregistered confirmatory results.
- Have a second person or team reproduce the main result from the package without informal assistance.

Use the NeurIPS reproducibility checklist as a minimum reporting model and NIST TEVV/AI RMF guidance for measurement and risk reporting.

## 15. Decision gates

### Gate A — Prior-art validity

Proceed only if the evidence review identifies a testable gap. If an existing system already implements and validates the proposed preservation contract, reproduce or extend it instead of relabeling it.

### Gate B — Harness validity

Proceed only after reproducing an external memory baseline within the preregistered tolerance.

### Gate C — Construct validity

Proceed only if independent curators can apply the preservation contract with acceptable agreement.

### Gate D — Exploratory feasibility

Proceed only if ten trajectories show plausible context savings without an unacceptable increase in operational errors.

### Gate E — Confirmatory efficacy

Accept the primary product hypothesis only if the preregistered noninferiority and compression criteria are met against the strongest reproduced baseline.

### Gate F — Safety and inspectability

Do not enable external writes or claim safe portability until targeted security and human-factors criteria pass.

### Gate G — Independent reproduction

Do not propose an open standard or broad scientific claim until an independent reproduction reaches materially consistent conclusions.

## 16. Stop or pivot criteria

Stop, narrow, or pivot if:

- AMC does not outperform a conventional summary or reproduced memory baseline after total cost is counted.
- Preservation contracts show poor human agreement.
- Context savings vanish when missing evidence is retrieved.
- Negative decisions, temporal updates, or authorization boundaries are systematically lost.
- Human-readable projections create false confidence or hide machine-readable intent.
- Memory poisoning remains effective under realistic controls.
- Results depend on one model, one prompt, or one source family.
- Independent reproduction fails and the discrepancy cannot be explained.

## 17. Required research artifacts

1. Search protocol and PRISMA-style evidence map.
2. Prior-art and novelty-risk report.
3. Claim ledger.
4. External benchmark replication report.
5. Dataset card and provenance manifest.
6. Annotation guide and preservation-contract rubric.
7. Preregistered study and statistical analysis plan.
8. Frozen evaluation harness and adversarial suite.
9. Human-factors report.
10. Security/threat-model report.
11. Confirmatory results with uncertainty and full error analysis.
12. Independent reproduction package and report.

Only after these artifacts support the claims should the product specification advance from a hypothesis-driven prototype to a proposed interoperable format.

## 18. Foundational research anchors

- CoALA: modular memory components and structured action spaces for language agents — https://arxiv.org/abs/2309.02427
- LongMemEval: extraction, multi-session and temporal reasoning, updates, and abstention — https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html
- MemoryAgentBench: retrieval, test-time learning, long-range understanding, and selective forgetting — https://github.com/HUST-AI-HYZ/MemoryAgentBench
- Mem2ActBench: action-oriented use of long-term memory — https://aclanthology.org/2026.acl-long.370/
- LoCoMo: long-term conversational memory and temporal/causal challenges — https://arxiv.org/abs/2402.17753
- Memory poisoning study and MPBench — https://arxiv.org/abs/2606.04329
- Persistent-memory prompt-injection evaluation — https://arxiv.org/abs/2607.14611
- PRISMA 2020 — https://www.prisma-statement.org/prisma-2020
- OSF preregistration guidance — https://help.osf.io/article/330-welcome-to-registrations
- NeurIPS reproducibility program — https://www.jmlr.org/papers/v22/20-303.html
- NIST AI TEVV — https://www.nist.gov/ai-test-evaluation-validation-and-verification-tevv
- NIST Generative AI Profile — https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
