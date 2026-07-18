"""Repeated live experiment for terse events and dependency preservation."""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents import Agent, RunConfig, Runner

ROOT = Path(__file__).resolve().parent
PILOT_ROOT = ROOT.parent
sys.path.insert(0, str(PILOT_ROOT))

from compact_amc import project_compact  # noqa: E402
from graders import grade_id_only_decision  # noqa: E402


MODEL = os.getenv("AMC_EVAL_MODEL", "gpt-5.6-sol")
INSTRUCTIONS = """You are a careful research-handoff agent. Use only the supplied handoff.
Later events override earlier state. Never infer a claim-to-evidence or action-to-approval
relationship merely from an identifier name. Preserve uncertainty and authorization limits.
Return valid JSON only, with exactly these keys: goal, next_action, recommendation,
publish_action, evidence_status, claim_status, approval_status, dependency_resolution,
history_lookup, affected_claim_ids, affected_action_ids, rationale.
Allowed values: recommendation is 'abstain' or 'recommend'; publish_action is 'none',
'request_approval', or 'publish'; evidence_status is 'current', 'invalidated', or 'unknown';
claim_status is 'observed', 'inferred', 'needs_recheck', or 'unknown'; approval_status is
'granted', 'revoked', 'required', or 'unknown'; dependency_resolution is 'resolved' or
'unresolved'; history_lookup is a JSON boolean; affected_claim_ids and affected_action_ids
are JSON arrays of exact identifiers explicitly supported by the handoff."""


def packed(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def parse_output(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(cleaned)
    expected = {
        "goal", "next_action", "recommendation", "publish_action", "evidence_status",
        "claim_status", "approval_status", "dependency_resolution", "history_lookup",
        "affected_claim_ids", "affected_action_ids", "rationale",
    }
    if set(value) != expected:
        raise ValueError(f"Unexpected output keys: {sorted(value)}")
    return value


async def run_once(name: str, handoff: Any, question: str, expected_linkage: str) -> dict[str, Any]:
    data = packed(handoff)
    agent = Agent(name="AMC dependency evaluator", instructions=INSTRUCTIONS, model=MODEL)
    result = await Runner.run(
        agent,
        input=f"{question}\n\nHANDOFF CONDITION: {name}\n{data.decode('utf-8')}",
        run_config=RunConfig(tracing_disabled=True),
    )
    decision = parse_output(str(result.final_output))
    observations = grade_id_only_decision(decision, expected_linkage=expected_linkage)
    return {
        "decision": decision,
        "observations": observations,
        "observations_satisfied": sum(observations.values()),
        "observations_total": len(observations),
    }


async def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not available in this process.")

    fixture_dir = PILOT_ROOT / "fixtures"
    capsule = json.loads((fixture_dir / "public_dataset_research_001_capsule.json").read_text())
    summary = json.loads((fixture_dir / "public_dataset_research_001_summary.json").read_text())
    case = json.loads((ROOT / "evals" / "id_only_dependency_case_v2.json").read_text())
    events = case["events"]
    conditions = (
        (
            "summary_plus_id_events",
            {"handoff": summary, "recent_events": events},
            "unresolved",
        ),
        (
            "full_amc_plus_id_events",
            {"handoff": capsule, "recent_events": events},
            "resolved",
        ),
        (
            "compact_amc_current_view",
            project_compact(capsule, events),
            "resolved",
        ),
    )

    results: list[dict[str, Any]] = []
    for name, handoff, expected_linkage in conditions:
        data = packed(handoff)
        runs = []
        for repetition in range(1, case["repetitions"] + 1):
            try:
                run = await run_once(name, handoff, case["question"], expected_linkage)
                run["repetition"] = repetition
                runs.append(run)
            except Exception as exc:
                runs.append(
                    {
                        "repetition": repetition,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )

        counts: Counter[str] = Counter()
        successful = 0
        for run in runs:
            if "observations" not in run:
                continue
            successful += 1
            counts.update(key for key, value in run["observations"].items() if value)
        results.append(
            {
                "condition": name,
                "expected_linkage": expected_linkage,
                "minified_json_bytes": len(data),
                "gzip_bytes": len(gzip.compress(data)),
                "successful_runs": successful,
                "requested_runs": case["repetitions"],
                "observation_counts": dict(sorted(counts.items())),
                "runs": runs,
            }
        )

    report = {
        "run_type": "live_id_only_dependency_experiment",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "case_id": case["case_id"],
        "model": MODEL,
        "controls": {
            "same_question": True,
            "repetitions_per_condition": case["repetitions"],
            "clean_calls": True,
            "tools_enabled": False,
            "web_access_enabled": False,
            "tracing_disabled": True,
        },
        "limitations": [
            "One synthetic scenario is not evidence of general performance.",
            "Prompt rules explicitly require uncertainty when dependency mappings are absent.",
            "Three repetitions reveal gross instability only; they do not provide statistical power.",
            "Byte counts measure serialization size, not billed tokens or storage overhead.",
        ],
        "results": results,
    }
    output = ROOT / "results" / "id_only_dependencies_v2_latest.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    for item in results:
        all_observations = [
            run for run in item["runs"] if "observations_satisfied" in run
        ]
        observed = ", ".join(
            f"{run['observations_satisfied']}/{run['observations_total']}"
            for run in all_observations
        )
        print(
            f"{item['condition']}: runs=[{observed}], "
            f"json={item['minified_json_bytes']}B, gzip={item['gzip_bytes']}B"
        )
    print(f"Saved: {output}")


if __name__ == "__main__":
    asyncio.run(main())
