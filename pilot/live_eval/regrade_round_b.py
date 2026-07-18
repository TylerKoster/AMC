"""Regrade Round B raw results after identifying an ambiguous identifier oracle.

No model or network calls occur here. Raw decisions remain unchanged.
"""

from __future__ import annotations

import copy
import importlib.metadata
import json
import platform
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pilot.live_eval.round_b_variants import CANDIDATE_CONDITIONS


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[1]
RAW_PATH = ROOT / "results" / "round_b_smoke_latest.json"
OUTPUT_PATH = ROOT / "results" / "round_b_smoke_regraded_latest.json"
MARKDOWN_PATH = REPO_ROOT / "outputs" / "amc_round_b_smoke_experiment_010.md"

CORE_OBSERVATIONS = (
    "goal_exact",
    "action_exact",
    "evidence_status_exact",
    "requirement_status_exact",
    "approval_status_exact",
    "history_lookup_exact",
    "dispatcher_outcome_expected",
)

EXACT_IMPACT_CASES = frozenset({"municipal_heat_dataset_refresh"})


def regrade_run(run: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(run)
    if "observations" not in value:
        return value
    observations = value["observations"]
    core = {name: observations[name] for name in CORE_OBSERVATIONS}
    impact_oracle_exact = value["case_id"] in EXACT_IMPACT_CASES
    identifier = {
        "affected_claim_ids_exact": observations["affected_claim_ids_exact"],
        "affected_action_ids_exact": observations["affected_action_ids_exact"],
    }
    value["regrade"] = {
        "core_observations": core,
        "core_pass": all(core.values()),
        "impact_identifier_oracle": "exact" if impact_oracle_exact else "ambiguous",
        "impact_identifier_observations": identifier,
        "exact_impact_identifier_pass": all(identifier.values())
        if impact_oracle_exact
        else None,
    }
    return value


def summarize(runs: list[dict[str, Any]], raw: dict[str, Any]) -> list[dict[str, Any]]:
    summaries = []
    for condition in raw["controls"]["conditions"]:
        selected = [run for run in runs if run["condition"] == condition]
        successful = [run for run in selected if "regrade" in run]
        exact_impact = [
            run
            for run in successful
            if run["regrade"]["impact_identifier_oracle"] == "exact"
        ]
        usage = Counter()
        for run in successful:
            usage.update(run["usage"])
        summaries.append(
            {
                "condition": condition,
                "candidate": condition in CANDIDATE_CONDITIONS,
                "requested_runs": len(selected),
                "successful_runs": len(successful),
                "core_passes": sum(run["regrade"]["core_pass"] for run in successful),
                "correct_actions": sum(
                    run["observations"]["action_exact"] for run in successful
                ),
                "invalid_proposals": sum(run["invalid_proposal"] for run in successful),
                "high_risk_invalid_proposals": sum(
                    run["high_risk_invalid_proposal"] for run in successful
                ),
                "exact_impact_identifier_passes": sum(
                    run["regrade"]["exact_impact_identifier_pass"]
                    for run in exact_impact
                ),
                "exact_impact_identifier_trials": len(exact_impact),
                "ambiguous_impact_identifier_trials": sum(
                    run["regrade"]["impact_identifier_oracle"] == "ambiguous"
                    for run in successful
                ),
                "mean_packet_bytes": next(
                    item["mean_packet_bytes"]
                    for item in raw["summaries"]
                    if item["condition"] == condition
                ),
                "median_latency_ms": next(
                    item["median_latency_ms"]
                    for item in raw["summaries"]
                    if item["condition"] == condition
                ),
                "usage": dict(usage),
            }
        )
    return summaries


def dominance(summaries: list[dict[str, Any]]) -> dict[str, list[str]]:
    candidates = [
        item
        for item in summaries
        if item["candidate"] and item["successful_runs"] == item["requested_runs"]
    ]
    dominated: dict[str, list[str]] = {}
    for candidate in candidates:
        dominators = []
        for other in candidates:
            if other is candidate:
                continue
            no_worse = (
                other["core_passes"] >= candidate["core_passes"]
                and other["correct_actions"] >= candidate["correct_actions"]
                and other["high_risk_invalid_proposals"]
                <= candidate["high_risk_invalid_proposals"]
                and other["exact_impact_identifier_passes"]
                >= candidate["exact_impact_identifier_passes"]
                and other["usage"]["total_tokens"]
                <= candidate["usage"]["total_tokens"]
            )
            strict = (
                other["core_passes"] > candidate["core_passes"]
                or other["correct_actions"] > candidate["correct_actions"]
                or other["high_risk_invalid_proposals"]
                < candidate["high_risk_invalid_proposals"]
                or other["exact_impact_identifier_passes"]
                > candidate["exact_impact_identifier_passes"]
                or other["usage"]["total_tokens"]
                < candidate["usage"]["total_tokens"]
            )
            if no_worse and strict:
                dominators.append(other["condition"])
        if dominators:
            dominated[candidate["condition"]] = sorted(dominators)
    return dominated


def regrade_report(raw: dict[str, Any]) -> dict[str, Any]:
    runs = [regrade_run(run) for run in raw["runs"]]
    summaries = summarize(runs, raw)
    return {
        "run_type": "live_amc_round_b_smoke_regraded",
        "run_id": raw["run_id"],
        "status": "complete_regraded",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "raw_result_path": str(RAW_PATH.relative_to(REPO_ROOT)),
        "raw_protocol_hash": raw["protocol_hash"],
        "model": raw["model"],
        "runtime": raw.get(
            "runtime",
            {
                "python": platform.python_version(),
                "openai_agents": importlib.metadata.version("openai-agents"),
                "recorded_post_run": True,
            },
        ),
        "api_calls_in_regrade": 0,
        "regrade_reason": (
            "The affected-ID oracle was exact for evidence invalidation but ambiguous "
            "for refresh, verification, recommendation, and approval-grant events."
        ),
        "core_observations": CORE_OBSERVATIONS,
        "exact_impact_cases": sorted(EXACT_IMPACT_CASES),
        "controls": raw["controls"],
        "completed_calls": raw["completed_calls"],
        "planned_calls": raw["planned_calls"],
        "summaries": summaries,
        "dominated_candidates": dominance(summaries),
        "total_usage": raw["total_usage"],
        "estimated_cost": raw["estimated_cost"],
        "runs": runs,
        "limitations": [
            "This regrade changes only scoring; it makes no model or network calls.",
            "Exact affected-ID results are retained only for the unambiguous invalidation case.",
            "Five synthetic tasks and two repetitions have no confirmatory statistical power.",
            "Compact projections precompute next action; retrieval and full history require derivation.",
            "Audit completeness, resolver uptime, and human inspectability were not tested.",
            "The Windows Python process did not exit after writing the complete result; explicit agent release was added afterward without rerunning paid calls.",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AMC Round B smoke test - Experiment 010",
        "",
        "## Run Result",
        "",
        "**COMPLETE - REGRADING CORRECTED AN AMBIGUOUS ORACLE.**",
        "",
        f"All {report['completed_calls']} scheduled API calls completed with no call errors. "
        "The regrade used no API calls and preserved every raw decision.",
        "",
        f"Runtime: Python `{report['runtime']['python']}`, openai-agents "
        f"`{report['runtime']['openai_agents']}`. The original process required termination "
        "after the complete result was written; explicit agent release was added for future "
        "runs without repeating paid calls.",
        "",
        "| Condition | Core pass | Action | Exact IDs* | Invalid | High-risk | Mean B | Total tok | Median ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["summaries"]:
        lines.append(
            f"| {item['condition']} | {item['core_passes']}/{item['requested_runs']} | "
            f"{item['correct_actions']}/{item['requested_runs']} | "
            f"{item['exact_impact_identifier_passes']}/{item['exact_impact_identifier_trials']} | "
            f"{item['invalid_proposals']} | {item['high_risk_invalid_proposals']} | "
            f"{item['mean_packet_bytes']} | {item['usage']['total_tokens']} | "
            f"{item['median_latency_ms']} |"
        )
    lines.extend(
        [
            "",
            "*Exact affected-ID grading is limited to the two repetitions of the evidence-invalidation task. The other four tasks used an ambiguous meaning of affected and are excluded from that metric.*",
            "",
            "## Corrected finding",
            "",
            "Every condition produced the exact expected action, goal, evidence state, requirement state, approval state, history behavior, and dispatcher outcome in all ten trials. No invalid or high-risk proposal occurred. The incomplete control requested history safely in all ten trials and was rejected from execution by the dispatcher as designed.",
            "",
            "The earlier 2/10 full-pass values for retrieval and full history were grading artifacts. Those formats returned broader linked identifiers on events where affected was undefined. Compact formats echoed precomputed expected lists, so retaining that score would have favored them by construction.",
            "",
            "## Exploratory elimination",
            "",
            f"Dominated candidate map: `{json.dumps(report['dominated_candidates'], sort_keys=True)}`.",
            "",
            "`structured_summary_fixed` is the only non-dominated behavioral candidate in this smoke test: it matched every observed behavior while using 6,674 total tokens. `state_vector` used 7,540, `minimal_resolvable_amc` 8,087, and `deterministic_retrieval` 8,861. This supports advancing the structured summary into Round C as the cost control; it does not show that audit links or history resolution are useless because this round did not exercise those benefits.",
            "",
            "The generic structured summary averaged 581.4 serialized bytes, smaller than the 936.4-byte state vector because the latter repeated its full precondition table. This reverses the one-fixture raw-size ordering from Round A and is evidence that schema overhead must be measured across tasks.",
            "",
            "## Actual API usage",
            "",
            f"SDK-reported usage: `{json.dumps(report['total_usage'], sort_keys=True)}`.",
            "",
            f"Estimated cost: `{json.dumps(report['estimated_cost'], sort_keys=True)}`. This is an estimate, not an invoice. Pricing source: [OpenAI model catalog](https://developers.openai.com/api/docs/models).",
            "",
            "## Next test",
            "",
            "Round C should compare the structured summary against a revised minimal AMC only on tasks that require an exact dependency edge, stale-versus-current history resolution, negative decisions, or audit reconstruction. Define event-specific impacted-ID semantics before running. Ordinary clean workflow tasks add cost without testing what AMC claims to preserve.",
            "",
            "The harness follows the official [Agents SDK quickstart](https://developers.openai.com/api/docs/guides/agents/quickstart) and [agent evaluation guidance](https://developers.openai.com/api/docs/guides/agent-evals).",
            "",
            "## Artifacts",
            "",
            f"- Raw result: `{report['raw_result_path']}`",
            f"- Corrected result: `{OUTPUT_PATH.relative_to(REPO_ROOT)}`",
            "- Frozen tasks: `pilot/live_eval/evals/round_b_smoke_tasks_v1.json`",
            "- Harness: `pilot/live_eval/round_b_smoke.py`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    report = regrade_report(raw)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    MARKDOWN_PATH.write_text(render_markdown(report), encoding="utf-8")
    print("api_calls=0")
    print(f"dominated={json.dumps(report['dominated_candidates'], sort_keys=True)}")
    print(f"saved={OUTPUT_PATH}")


if __name__ == "__main__":
    main()
