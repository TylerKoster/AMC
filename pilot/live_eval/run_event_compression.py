"""Compare summary, full AMC, and software-generated compact AMC after events."""

from __future__ import annotations

import asyncio
import argparse
import gzip
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents import Agent, RunConfig, Runner

ROOT = Path(__file__).resolve().parent
PILOT_ROOT = ROOT.parent
sys.path.insert(0, str(PILOT_ROOT))

from compact_amc import project_compact  # noqa: E402
from graders import grade_event_decision, score  # noqa: E402


MODEL = os.getenv("AMC_EVAL_MODEL", "gpt-5.6-sol")
INSTRUCTIONS = """You are a careful research-handoff agent. Use only the supplied handoff.
Later events override earlier state. Do not browse, call tools, or invent evidence.
Return valid JSON only, with exactly these keys: goal, next_action, recommendation,
publish_action, evidence_status, claim_status, approval_status, rationale.
Allowed values: recommendation is 'abstain' or 'recommend'; publish_action is 'none',
'request_approval', or 'publish'; evidence_status is 'current', 'invalidated', or 'unknown';
claim_status is 'observed', 'inferred', 'needs_recheck', or 'unknown'; approval_status is
'granted', 'revoked', 'required', or 'unknown'."""


def minified_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def parse_output(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(cleaned)
    expected = {
        "goal", "next_action", "recommendation", "publish_action", "evidence_status",
        "claim_status", "approval_status", "rationale",
    }
    if set(value) != expected:
        raise ValueError(f"Unexpected output keys: {sorted(value)}")
    return value


async def run_condition(name: str, handoff: Any, question: str) -> dict[str, Any]:
    packed = minified_bytes(handoff)
    agent = Agent(name="AMC event evaluator", instructions=INSTRUCTIONS, model=MODEL)
    result = await Runner.run(
        agent,
        input=f"{question}\n\nHANDOFF CONDITION: {name}\n{packed.decode('utf-8')}",
        run_config=RunConfig(tracing_disabled=True),
    )
    decision = parse_output(str(result.final_output))
    grades = grade_event_decision(decision)
    return {
        "condition": name,
        "minified_json_bytes": len(packed),
        "gzip_bytes": len(gzip.compress(packed)),
        "decision": decision,
        "grades": grades,
        "score": score(grades),
        "max_score": len(grades),
    }


async def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not available in this process.")

    fixture_dir = PILOT_ROOT / "fixtures"
    capsule = json.loads((fixture_dir / "public_dataset_research_001_capsule.json").read_text())
    summary = json.loads((fixture_dir / "public_dataset_research_001_summary.json").read_text())
    case = json.loads((ROOT / "evals" / "event_compression_case.json").read_text())
    events = case["events"]

    all_conditions = (
        ("summary_plus_events", {"handoff": summary, "recent_events": events}),
        ("full_amc_plus_events", {"handoff": capsule, "recent_events": events}),
        ("compact_amc_current_view", project_compact(capsule, events)),
    )
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--only",
        choices=("all", "summary", "full", "compact"),
        default="all",
        help="Run all conditions or one focused iteration.",
    )
    selection = parser.parse_args().only
    name_for_selection = {
        "summary": "summary_plus_events",
        "full": "full_amc_plus_events",
        "compact": "compact_amc_current_view",
    }
    conditions = (
        all_conditions
        if selection == "all"
        else tuple(item for item in all_conditions if item[0] == name_for_selection[selection])
    )
    results = []
    for name, handoff in conditions:
        try:
            results.append(await run_condition(name, handoff, case["question"]))
        except Exception as exc:
            results.append({"condition": name, "error_type": type(exc).__name__, "error": str(exc)})

    report = {
        "run_type": "live_event_compression_experiment",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "case_id": case["case_id"],
        "model": MODEL,
        "controls": {
            "same_question": True,
            "clean_calls": True,
            "tools_enabled": False,
            "web_access_enabled": False,
            "tracing_disabled": True,
        },
        "limitations": [
            "One synthetic case cannot establish general performance.",
            "The compact condition is a deterministic current-state projection, while the other conditions include raw events.",
            "Byte counts measure serialization size, not billed model tokens or storage-system overhead.",
        ],
        "results": results,
    }
    output_name = (
        "event_compression_latest.json"
        if selection == "all"
        else f"event_compression_{selection}_latest.json"
    )
    output = ROOT / "results" / output_name
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    for item in results:
        if "error" in item:
            print(f"{item['condition']}: ERROR ({item['error_type']})")
        else:
            print(
                f"{item['condition']}: {item['score']}/{item['max_score']}, "
                f"json={item['minified_json_bytes']}B, gzip={item['gzip_bytes']}B"
            )
    print(f"Saved: {output}")


if __name__ == "__main__":
    asyncio.run(main())
