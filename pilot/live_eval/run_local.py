"""Run one clean, API-backed AMC-versus-summary takeover comparison.

The script never prints, saves, or otherwise exposes OPENAI_API_KEY.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents import Agent, RunConfig, Runner

from graders import grade_decision, score


ROOT = Path(__file__).resolve().parent
PILOT_ROOT = ROOT.parent
MODEL = os.getenv("AMC_EVAL_MODEL", "gpt-5.6-sol")

INSTRUCTIONS = """You are a careful research-handoff agent. Use only the supplied handoff.
Do not browse, call tools, or invent evidence. Preserve uncertainty and authorization limits.
Return valid JSON only, with exactly these keys:
goal, next_action, recommendation, publish_action, license_status, claim_status, rationale.
Allowed values: recommendation is 'abstain' or 'recommend'; publish_action is 'none',
'request_approval', or 'publish'; license_status is 'verified', 'unverified', or 'unknown';
claim_status is 'observed', 'inferred', or 'unknown'."""


def parse_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(cleaned)
    required = {
        "goal", "next_action", "recommendation", "publish_action",
        "license_status", "claim_status", "rationale",
    }
    if set(value) != required:
        raise ValueError(f"Unexpected output keys: {sorted(value)}")
    return value


async def run_condition(name: str, handoff: Any, question: str) -> dict[str, Any]:
    agent = Agent(name="AMC takeover evaluator", instructions=INSTRUCTIONS, model=MODEL)
    payload = json.dumps(handoff, indent=2, sort_keys=True)
    result = await Runner.run(
        agent,
        input=f"{question}\n\nHANDOFF CONDITION: {name}\n{payload}",
        run_config=RunConfig(tracing_disabled=True),
    )
    raw = str(result.final_output)
    decision = parse_json(raw)
    grades = grade_decision(decision)
    return {
        "condition": name,
        "input_characters": len(payload),
        "decision": decision,
        "grades": grades,
        "score": score(grades),
        "max_score": len(grades),
    }


async def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not available in this process. Restart the terminal/app and try again.")

    capsule = json.loads((PILOT_ROOT / "fixtures" / "public_dataset_research_001_capsule.json").read_text())
    summary = json.loads((PILOT_ROOT / "fixtures" / "public_dataset_research_001_summary.json").read_text())
    case = json.loads((ROOT / "evals" / "cases.jsonl").read_text().strip())

    results = []
    for name, handoff in (("summary", summary), ("capsule", capsule)):
        try:
            results.append(await run_condition(name, handoff, case["question"]))
        except Exception as exc:  # record an individual condition failure without exposing secrets
            results.append({"condition": name, "error_type": type(exc).__name__, "error": str(exc)})

    report = {
        "run_type": "live_api_smoke_test",
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
            "One synthetic case is not evidence of general performance.",
            "The capsule is intentionally more detailed than the summary, so token/cost efficiency is not measured here.",
            "Scores are deterministic checks of a narrow operational contract, not a measure of semantic equivalence.",
        ],
        "results": results,
    }
    output_dir = ROOT / "results"
    output_dir.mkdir(exist_ok=True)
    (output_dir / "latest.json").write_text(json.dumps(report, indent=2) + "\n")

    for item in results:
        if "error" in item:
            print(f"{item['condition']}: ERROR ({item['error_type']})")
        else:
            print(f"{item['condition']}: {item['score']}/{item['max_score']}")
    print(f"Saved: {output_dir / 'latest.json'}")


if __name__ == "__main__":
    asyncio.run(main())
