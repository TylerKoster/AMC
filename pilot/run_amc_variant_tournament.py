"""Run deterministic Round A of the AMC variant tournament without model calls."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pilot.amc_variant_tournament import (
    AUDIT_FACTS,
    EXECUTION_FACTS,
    SAFETY_FACTS,
    build_variants,
    evaluate_variant,
    pareto_frontier,
    transmission_costs,
)


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "pilot"
OUTPUTS = ROOT / "outputs"


def percentage_reduction(smaller: int, larger: int) -> float:
    return round((1 - smaller / larger) * 100, 3)


def _table(evaluations: list[dict[str, Any]], frontier: set[str]) -> list[str]:
    lines = [
        "| Variant | Raw B | Gzip B | Est. tokens* | Safety | Execution | Audit | Frontier |",
        "|---|---:|---:|---:|---:|---:|---:|:---:|",
    ]
    for item in evaluations:
        lines.append(
            "| {name} | {raw} | {gzip} | {tokens} | {safety}/{safety_total} | "
            "{execution}/{execution_total} | {audit}/{audit_total} | {frontier} |".format(
                name=item["name"],
                raw=item["minified_bytes"],
                gzip=item["gzip_bytes"],
                tokens=item["estimated_tokens_4_bytes"],
                safety=len(item["safety_preserved"]),
                safety_total=len(SAFETY_FACTS),
                execution=len(item["execution_preserved"]),
                execution_total=len(EXECUTION_FACTS),
                audit=len(item["audit_preserved"]),
                audit_total=len(AUDIT_FACTS),
                frontier="yes" if item["name"] in frontier else "",
            )
        )
    return lines


def main() -> None:
    capsule_path = PILOT / "fixtures" / "public_dataset_research_001_capsule.json"
    summary_path = PILOT / "fixtures" / "public_dataset_research_001_summary.json"
    case_path = PILOT / "live_eval" / "evals" / "id_only_dependency_case_v2.json"
    capsule = json.loads(capsule_path.read_text())
    summary = json.loads(summary_path.read_text())
    case = json.loads(case_path.read_text())
    events = case["events"]

    variants = build_variants(capsule, events, summary)
    evaluations = sorted(
        (
            evaluate_variant(name, payload, capsule)
            for name, payload in variants.items()
        ),
        key=lambda item: (item["minified_bytes"], item["name"]),
    )
    frontier = pareto_frontier(evaluations)
    frontier_set = set(frontier)
    transport = transmission_costs(capsule, events, variants["compact_amc"])
    by_name = {item["name"]: item for item in evaluations}

    full_current_bytes = by_name["full_amc_plus_events"]["minified_bytes"]
    minimal_bytes = by_name["minimal_resolvable_amc"]["minified_bytes"]
    compact_bytes = by_name["compact_amc"]["minified_bytes"]
    report = {
        "run_type": "deterministic_amc_variant_tournament_round_a",
        "run_id": "amc-variant-tournament-009",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "case_id": case["case_id"],
        "api_calls": 0,
        "network_access": False,
        "variant_count": len(variants),
        "contract": {
            "safety_facts": SAFETY_FACTS,
            "execution_facts": EXECUTION_FACTS,
            "audit_facts": AUDIT_FACTS,
            "pass_rule": "All safety facts must be mechanically extractable.",
        },
        "measurement": {
            "raw": "UTF-8 bytes of canonical minified, key-sorted JSON",
            "gzip": "Python gzip.compress with mtime=0",
            "estimated_tokens_4_bytes": (
                "ceil(raw UTF-8 bytes / 4); a rough planning estimate, not a model tokenizer count"
            ),
        },
        "source_files": [
            str(capsule_path.relative_to(ROOT)),
            str(summary_path.relative_to(ROOT)),
            str(case_path.relative_to(ROOT)),
        ],
        "evaluations": evaluations,
        "pareto_frontier": frontier,
        "transport": {
            **transport,
            "delta_reduction_vs_full_repeat_percent": percentage_reduction(
                transport["base_then_delta_two_turn_bytes"],
                transport["repeat_full_two_turn_bytes"],
            ),
            "compact_snapshot_reduction_vs_full_repeat_percent": percentage_reduction(
                transport["compact_snapshots_two_turn_bytes"],
                transport["repeat_full_two_turn_bytes"],
            ),
        },
        "comparisons": {
            "minimal_resolvable_vs_full_current_percent_smaller": percentage_reduction(
                minimal_bytes, full_current_bytes
            ),
            "minimal_resolvable_vs_compact_percent_smaller": percentage_reduction(
                minimal_bytes, compact_bytes
            ),
        },
        "limitations": [
            "This grader measures information availability, not model comprehension or action quality.",
            "The result uses one synthetic research workflow and cannot establish generality.",
            "The fact extractor is format-aware and could miss valid unrecognized paraphrases.",
            "The four-bytes-per-token value is only a rough estimate; raw bytes are the primary metric.",
            "Gzip size measures storage/transport compression, not context-window usage.",
            "A history reference is counted as resolvable syntactically; this run does not test resolver uptime or authorization.",
        ],
    }

    OUTPUTS.mkdir(exist_ok=True)
    json_path = OUTPUTS / "amc_variant_tournament_round_a_009.json"
    packets_path = OUTPUTS / "amc_variant_tournament_round_a_009_packets.json"
    markdown_path = OUTPUTS / "amc_variant_tournament_experiment_009.md"
    json_path.write_text(json.dumps(report, indent=2) + "\n")
    packets_path.write_text(json.dumps(variants, indent=2) + "\n")

    passing = [item for item in evaluations if item["safety_pass"]]
    failing = [item for item in evaluations if not item["safety_pass"]]
    lines = [
        "# AMC Variant Tournament — Experiment 009, Round A",
        "",
        "## Run Result",
        "",
        "**COMPLETE — deterministic screening only.** No OpenAI API or network calls were used.",
        "",
        f"Tested {len(evaluations)} variants against {len(SAFETY_FACTS)} safety, "
        f"{len(EXECUTION_FACTS)} execution, and {len(AUDIT_FACTS)} audit clauses. "
        f"{len(passing)} variants passed the safety gate; {len(failing)} failed.",
        "",
        "## Result table",
        "",
        *_table(evaluations, frontier_set),
        "",
        "*Estimated tokens are `ceil(raw bytes / 4)`, not tokenizer output. Raw bytes are authoritative.*",
        "",
        "## What survived Round A",
        "",
        f"The non-dominated frontier is: {', '.join(f'`{name}`' for name in frontier)}.",
        "",
        f"- `state_vector` is the smallest safety-passing packet at "
        f"{by_name['state_vector']['minified_bytes']} bytes, but it has no audit facts and no exact dependency edge.",
        f"- `structured_summary_fixed` is {by_name['structured_summary_fixed']['minified_bytes']} bytes. "
        "Adding one typed `license_verified: false` field repaired the original summary's safety failure.",
        f"- `minimal_resolvable_amc` is {minimal_bytes} bytes, passes all safety and execution clauses, "
        "and retains a history reference. It is the strongest compact candidate for the next live round.",
        f"- `deterministic_retrieval` is {by_name['deterministic_retrieval']['minified_bytes']} bytes and "
        "retains all audit facts, but does not precompute every current consequence.",
        "",
        "## Eliminations and diagnostics",
        "",
        "- The plain full AMC failed because it did not include the later invalidation and revocation events. A snapshot without its deltas is stale.",
        "- Delta-only failed as a standalone handoff. It is a transport optimization that requires a verified base resolver.",
        "- The gated, machine-constraint, Failure Space, and negative-paraphrase variants added no new mechanically preserved facts over smaller packets in this case.",
        "- Failure Space remains a live-model diagnostic; Round A does not show that its extra prose improves model behavior.",
        "- The incomplete compact control failed when approval state and dependency links were removed, confirming that small packets can become dangerously incomplete.",
        "",
        "## Size findings",
        "",
        f"`minimal_resolvable_amc` is {report['comparisons']['minimal_resolvable_vs_full_current_percent_smaller']}% "
        "smaller than full AMC plus events and "
        f"{report['comparisons']['minimal_resolvable_vs_compact_percent_smaller']}% smaller than the prior compact AMC.",
        "",
        f"Across two equal temporal endpoints, base-plus-delta used "
        f"{transport['base_then_delta_two_turn_bytes']} bytes versus "
        f"{transport['repeat_full_two_turn_bytes']} for repeating full state, a "
        f"{report['transport']['delta_reduction_vs_full_repeat_percent']}% reduction. "
        "Delta is not independently portable.",
        "",
        f"Two compact current-state snapshots used {transport['compact_snapshots_two_turn_bytes']} bytes, "
        f"a {report['transport']['compact_snapshot_reduction_vs_full_repeat_percent']}% reduction versus full repetition. "
        "They rely on the referenced history for omitted audit detail.",
        "",
        "## Scientific boundary",
        "",
        "This round proves only deterministic preservation and byte size on one fixture. It does not prove that an AI will interpret the variants equally, drift less, or take safer actions. Those claims require blinded live-model evaluation across multiple task families, randomized order, repeated trials, and dispatcher-observed outcomes.",
        "",
        "## Next experiment",
        "",
        "Advance the four frontier variants to a blinded live-model round. Keep the dispatcher authoritative and compare exact action validity, dependency resolution, goal retention, recovery after injected slips, latency, and actual API token usage. Use full AMC plus events as the high-information control and the incomplete compact packet as the negative control.",
        "",
        "## Artifacts",
        "",
        f"- Metrics: `{json_path.relative_to(ROOT)}`",
        f"- Inspectable packets: `{packets_path.relative_to(ROOT)}`",
        "- Generator: `pilot/amc_variant_tournament.py`",
        "- Tests: `pilot/tests/test_amc_variant_tournament.py`",
        "",
    ]
    markdown_path.write_text("\n".join(lines))

    print(f"variants={len(evaluations)} safety_pass={len(passing)} safety_fail={len(failing)}")
    print(f"frontier={','.join(frontier)}")
    print(
        f"minimal_resolvable={minimal_bytes}B full_plus_events={full_current_bytes}B "
        f"reduction={report['comparisons']['minimal_resolvable_vs_full_current_percent_smaller']}%"
    )
    print(f"saved={markdown_path}")


if __name__ == "__main__":
    main()
