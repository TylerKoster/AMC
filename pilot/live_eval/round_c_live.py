"""Paid Round C executor that reads frozen inputs and persists ungraded responses."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agents import Agent, RunConfig, Runner
from pydantic import BaseModel, Field

from pilot.live_eval.round_c_protocol import (
    build_packet,
    build_schedule,
    canonical_json,
    load_inputs,
    load_protocol,
    packet_metrics,
    protocol_fingerprint,
    ROUND_C_INSTRUCTIONS,
    sha256_value,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_RESPONSE_PATH = ROOT / "results" / "round_c_live_responses.json"

class PreservedFact(BaseModel):
    source_id: str
    key: str
    value_json: str = Field(
        description="Exact minified JSON encoding of the preserved observation value"
    )
    response_sha256: str


class RoundCDecision(BaseModel):
    preserved_facts: list[PreservedFact]
    actions: list[str]
    cautions: list[str]
    source_refs: list[str]
    rationale: str = Field(max_length=800)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    """Write, fsync, and atomically replace a checkpoint on the same filesystem."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    except Exception:
        if temporary_path.exists():
            temporary_path.unlink()
        raise


def usage_from_result(result: Any) -> dict[str, int]:
    totals = Counter()
    for response in result.raw_responses:
        usage = response.usage
        totals.update(
            {
                "requests": usage.requests,
                "input_tokens": usage.input_tokens,
                "cached_input_tokens": usage.input_tokens_details.cached_tokens,
                "cache_write_tokens": usage.input_tokens_details.cache_write_tokens,
                "output_tokens": usage.output_tokens,
                "reasoning_tokens": usage.output_tokens_details.reasoning_tokens,
                "total_tokens": usage.total_tokens,
            }
        )
    return dict(totals)


def make_message(packet: dict[str, Any]) -> str:
    return canonical_json({"authoritative_handoff": packet}).decode("utf-8")


def result_key(item: dict[str, Any]) -> str:
    return f"{item['sequence']}:{item['case_id']}:{item['condition']}:{item['repetition']}"


async def run_once(
    agent: Agent,
    schedule_item: dict[str, Any],
    task: dict[str, Any],
    *,
    max_turns: int,
) -> dict[str, Any]:
    packet = build_packet(task, schedule_item["condition"])
    started = time.perf_counter()
    result = await Runner.run(
        agent,
        input=make_message(packet),
        max_turns=max_turns,
        run_config=RunConfig(tracing_disabled=True),
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    decision = result.final_output.model_dump(mode="json")
    return {
        **schedule_item,
        "key": result_key(schedule_item),
        "packet": packet_metrics(packet),
        "decision": decision,
        "decision_sha256": hashlib.sha256(canonical_json(decision)).hexdigest(),
        "usage": usage_from_result(result),
        "elapsed_ms": elapsed_ms,
        "response_saved_at": utc_now(),
    }


def validate_paid_acknowledgement(
    execute_paid: bool, acknowledged_calls: int | None, planned_calls: int
) -> None:
    if not execute_paid:
        raise SystemExit(
            "Paid execution is disabled. Run round_c_packet_audit.py for the no-model gate."
        )
    if acknowledged_calls != planned_calls:
        raise SystemExit(
            f"Paid execution requires --acknowledge-calls {planned_calls}."
        )


def _new_response_artifact(
    protocol: dict[str, Any], inputs: dict[str, Any], schedule: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "schema_version": "amc-round-c-live-responses/0.1",
        "experiment_id": protocol["experiment_id"],
        "status": "running-ungraded",
        "started_at": utc_now(),
        "responses_persisted": False,
        "protocol_sha256": protocol_fingerprint(protocol),
        "input_partition_sha256": inputs["partition_sha256"],
        "capture_sha256": inputs["capture_sha256"],
        "schedule_sha256": sha256_value(schedule),
        "random_seed": protocol["random_seed"],
        "model": protocol["model"],
        "planned_calls": len(schedule),
        "completed_calls": 0,
        "runs": [],
    }


def _resume_response_artifact(
    path: Path,
    protocol: dict[str, Any],
    inputs: dict[str, Any],
    schedule: list[dict[str, Any]],
) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    expected = _new_response_artifact(protocol, inputs, schedule)
    for key in (
        "schema_version",
        "experiment_id",
        "protocol_sha256",
        "input_partition_sha256",
        "capture_sha256",
        "schedule_sha256",
        "random_seed",
        "model",
        "planned_calls",
    ):
        if value.get(key) != expected[key]:
            raise ValueError(f"Cannot resume: {key} disagrees with the frozen protocol")
    if value.get("responses_persisted"):
        raise ValueError("Cannot resume a completed response artifact")
    value["runs"] = [run for run in value.get("runs", []) if "decision" in run]
    value["completed_calls"] = len(value["runs"])
    value["status"] = "running-ungraded"
    return value


async def execute(args: argparse.Namespace) -> None:
    protocol = load_protocol()
    inputs = load_inputs(protocol=protocol)
    schedule = build_schedule(inputs, protocol)
    validate_paid_acknowledgement(
        args.execute_paid_round_c, args.acknowledge_calls, len(schedule)
    )
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not available in this process.")
    if args.response_out.exists():
        if not args.resume:
            raise FileExistsError(
                f"Response artifact exists; pass --resume or select a new path: {args.response_out}"
            )
        report = _resume_response_artifact(
            args.response_out, protocol, inputs, schedule
        )
    else:
        report = _new_response_artifact(protocol, inputs, schedule)
        atomic_write_json(args.response_out, report)
    tasks = {task["case_id"]: task for task in inputs["tasks"]}
    completed = {run["key"] for run in report["runs"]}
    agent = Agent(
        name="AMC Round C preservation evaluator",
        instructions=ROUND_C_INSTRUCTIONS,
        model=protocol["model"],
        output_type=RoundCDecision,
    )
    for item in schedule:
        key = result_key(item)
        if key in completed:
            continue
        try:
            run = await run_once(
                agent,
                item,
                tasks[item["case_id"]],
                max_turns=protocol["max_turns"],
            )
        except Exception as exc:
            report["status"] = "stopped-after-call-error"
            report["last_error"] = {
                **item,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "saved_at": utc_now(),
            }
            atomic_write_json(args.response_out, report)
            raise SystemExit(
                "Stopped after a live-call error; persisted successful responses remain resumable."
            ) from exc
        report["runs"].append(run)
        report["completed_calls"] = len(report["runs"])
        atomic_write_json(args.response_out, report)
        print(f"[{report['completed_calls']}/{len(schedule)}] response persisted", flush=True)
    report["status"] = "responses-persisted-ungraded"
    report["responses_persisted"] = True
    report["completed_at"] = utc_now()
    atomic_write_json(args.response_out, report)
    print(f"responses_saved={args.response_out}", flush=True)
    print("grading_not_started=true", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-paid-round-c", action="store_true")
    parser.add_argument("--acknowledge-calls", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--response-out", type=Path, default=DEFAULT_RESPONSE_PATH)
    return parser.parse_args()


def main() -> None:
    asyncio.run(execute(parse_args()))


if __name__ == "__main__":
    main()
