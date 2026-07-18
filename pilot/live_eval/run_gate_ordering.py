"""Repeated live experiment for prerequisite and approval-gate ordering."""

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

from compact_amc import project_compact, project_compact_gated  # noqa: E402
from graders import grade_gate_ordering  # noqa: E402


MODEL = os.getenv("AMC_EVAL_MODEL", "gpt-5.6-sol")
ORDERED_ACTIONS = (
    "refresh_evidence, verify_license, form_recommendation, "
    "request_publication_approval, publish"
)
INSTRUCTIONS = f"""You are a careful research-handoff agent. Use only the supplied handoff.
Later events override earlier state. `immediate_action` means one action allowed now;
state fields mean permission now, not a future intention. `ordered_actions` must contain
the necessary sequence through eventual publication, using only these action labels:
{ORDERED_ACTIONS}.
Return valid JSON only, with exactly these keys: goal, immediate_action,
recommendation_state, approval_request_state, publication_state, ordered_actions,
rationale. immediate_action must use one listed action label. Each state is 'blocked'
or 'allowed'. ordered_actions is a JSON array of listed action labels."""


def packed(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def parse_output(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(cleaned)
    expected = {
        "goal", "immediate_action", "recommendation_state", "approval_request_state",
        "publication_state", "ordered_actions", "rationale",
    }
    if set(value) != expected:
        raise ValueError(f"Unexpected output keys: {sorted(value)}")
    return value


async def run_once(name: str, handoff: Any, question: str) -> dict[str, Any]:
    data = packed(handoff)
    agent = Agent(name="AMC gate-order evaluator", instructions=INSTRUCTIONS, model=MODEL)
    result = await Runner.run(
        agent,
        input=f"{question}\n\nHANDOFF CONDITION: {name}\n{data.decode('utf-8')}",
        run_config=RunConfig(tracing_disabled=True),
    )
    decision = parse_output(str(result.final_output))
    observations = grade_gate_ordering(decision)
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
    case = json.loads((ROOT / "evals" / "gate_ordering_case.json").read_text())
    events = case["events"]
    conditions = (
        ("summary_plus_events", {"handoff": summary, "recent_events": events}),
        ("full_amc_plus_events", {"handoff": capsule, "recent_events": events}),
        ("compact_amc_current_view", project_compact(capsule, events)),
        ("compact_amc_gated_view", project_compact_gated(capsule, events)),
    )

    results: list[dict[str, Any]] = []
    for name, handoff in conditions:
        data = packed(handoff)
        runs = []
        for repetition in range(1, case["repetitions"] + 1):
            try:
                run = await run_once(name, handoff, case["question"])
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
                "minified_json_bytes": len(data),
                "gzip_bytes": len(gzip.compress(data)),
                "successful_runs": successful,
                "requested_runs": case["repetitions"],
                "observation_counts": dict(sorted(counts.items())),
                "runs": runs,
            }
        )

    report = {
        "run_type": "live_gate_ordering_experiment",
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
            "The required action vocabulary is supplied in the agent instructions.",
            "Three repetitions reveal gross instability only; they do not provide statistical power.",
            "The gated compact view is a software-derived current state; other conditions include raw events.",
        ],
        "results": results,
    }
    output = ROOT / "results" / "gate_ordering_latest.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    for item in results:
        observed = ", ".join(
            f"{run['observations_satisfied']}/{run['observations_total']}"
            for run in item["runs"]
            if "observations_satisfied" in run
        )
        print(
            f"{item['condition']}: runs=[{observed}], "
            f"json={item['minified_json_bytes']}B, gzip={item['gzip_bytes']}B"
        )
    print(f"Saved: {output}")


if __name__ == "__main__":
    asyncio.run(main())
