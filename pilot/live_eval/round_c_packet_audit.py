"""No-model packet-construction audit for the frozen Round C protocol."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pilot.live_eval.round_c_protocol import (
    build_packet,
    build_schedule,
    canonical_json,
    find_prohibited_keys,
    load_inputs,
    load_protocol,
    packet_metrics,
    protocol_fingerprint,
    recover_task,
    sha256_value,
)


DEFAULT_RESULT_PATH = REPO_ROOT / "outputs" / "amc_round_c_packet_audit_013.json"
DEFAULT_REPORT_PATH = REPO_ROOT / "outputs" / "amc_round_c_live_gate_experiment_013.md"


def run_audit() -> dict[str, Any]:
    protocol = load_protocol()
    inputs = load_inputs(protocol=protocol)
    schedule = build_schedule(inputs, protocol)
    tasks = {task["case_id"]: task for task in inputs["tasks"]}
    packet_results: list[dict[str, Any]] = []
    for task in inputs["tasks"]:
        for condition in protocol["conditions"]:
            packet = build_packet(task, condition)
            recovered = recover_task(packet, condition)
            packet_results.append(
                {
                    "case_id": task["case_id"],
                    "condition": condition,
                    "semantic_fidelity": canonical_json(recovered) == canonical_json(task),
                    "prohibited_keys": find_prohibited_keys(packet),
                    "condition_label_in_packet": condition in canonical_json(packet).decode("utf-8"),
                    "metrics": packet_metrics(packet),
                }
            )
    condition_counts = Counter(item["condition"] for item in schedule)
    schedule_hash = sha256_value(schedule)
    grouped_order = sorted(
        schedule,
        key=lambda item: (item["condition"], item["case_id"], item["repetition"]),
    )
    summaries: dict[str, Any] = {}
    for condition in protocol["conditions"]:
        selected = [item for item in packet_results if item["condition"] == condition]
        summaries[condition] = {
            "tasks": len(selected),
            "semantic_fidelity_passes": sum(item["semantic_fidelity"] for item in selected),
            "oracle_key_leaks": sum(bool(item["prohibited_keys"]) for item in selected),
            "condition_label_leaks": sum(item["condition_label_in_packet"] for item in selected),
            "unique_raw_bytes": sum(item["metrics"]["raw_bytes"] for item in selected),
            "unique_gzip_bytes": sum(item["metrics"]["gzip_bytes"] for item in selected),
        }
    gate_pass = (
        all(item["semantic_fidelity"] for item in packet_results)
        and not any(item["prohibited_keys"] for item in packet_results)
        and not any(item["condition_label_in_packet"] for item in packet_results)
        and schedule != grouped_order
        and len(schedule) == protocol["planned_calls"]
        and all(
            count == len(inputs["tasks"]) * protocol["repetitions"]
            for count in condition_counts.values()
        )
    )
    summary_baseline = summaries["structured_summary_v2"]
    minimal_amc = summaries["minimal_amc_v2"]
    compression_comparison = {
        "baseline": "structured_summary_v2",
        "candidate": "minimal_amc_v2",
        "raw_reduction_percent": round(
            100
            * (
                summary_baseline["unique_raw_bytes"]
                - minimal_amc["unique_raw_bytes"]
            )
            / summary_baseline["unique_raw_bytes"],
            3,
        ),
        "gzip_reduction_percent": round(
            100
            * (
                summary_baseline["unique_gzip_bytes"]
                - minimal_amc["unique_gzip_bytes"]
            )
            / summary_baseline["unique_gzip_bytes"],
            3,
        ),
        "meaningful_compression_claim": False,
    }
    return {
        "schema_version": "amc-round-c-packet-audit/0.1",
        "experiment": "AMC Round C live gate 013",
        "status": "complete-no-model-audit",
        "gate_pass": gate_pass,
        "model_calls": 0,
        "openai_api_calls": 0,
        "oracle_files_loaded": 0,
        "response_bodies_loaded": 0,
        "input_partition_sha256": inputs["partition_sha256"],
        "capture_sha256": inputs["capture_sha256"],
        "protocol_sha256": protocol_fingerprint(protocol),
        "random_seed": protocol["random_seed"],
        "planned_paid_calls": protocol["planned_calls"],
        "schedule_sha256": schedule_hash,
        "schedule": schedule,
        "condition_counts": dict(condition_counts),
        "summaries": summaries,
        "compression_comparison": compression_comparison,
        "packets": packet_results,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# AMC Round C live-runner gate - Experiment 013",
        "",
        "## Run Result",
        "",
        "**COMPLETE - no-model packet audit. Paid Round C was not started.**",
        "",
        f"- Gate pass: {result['gate_pass']}",
        f"- Frozen tasks: {len({item['case_id'] for item in result['schedule']})}",
        f"- Preregistered paid calls: {result['planned_paid_calls']}",
        f"- Random seed: {result['random_seed']}",
        f"- Schedule SHA-256: `{result['schedule_sha256']}`",
        f"- Protocol SHA-256: `{result['protocol_sha256']}`",
        "- OpenAI/model calls in this audit: 0",
        "- Held-out contract files loaded in this audit: 0",
        "",
        "| Condition | Fidelity | Oracle-key leaks | Label leaks | Raw bytes | Gzip bytes |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for condition, summary in result["summaries"].items():
        lines.append(
            f"| {condition} | {summary['semantic_fidelity_passes']}/{summary['tasks']} | "
            f"{summary['oracle_key_leaks']} | {summary['condition_label_leaks']} | "
            f"{summary['unique_raw_bytes']} | {summary['unique_gzip_bytes']} |"
        )
    lines.extend(
        [
            "",
            "## Architecture gate",
            "",
            "Packet construction reads only the frozen input partition and preregistered protocol. The live executor saves raw structured decisions atomically and contains no grader or held-out-contract import. A separate grading process first validates a complete persisted response artifact; only then may it load the held-out contracts.",
            "",
            "## Interpretation",
            "",
            "This establishes packet fidelity, deterministic randomized ordering, balanced exposure, and execution/grading separation. It does not establish model quality, statistical power, cost, or AMC superiority because no model was called.",
            "",
            f"The minimal AMC packet is only {result['compression_comparison']['raw_reduction_percent']}% smaller raw and {result['compression_comparison']['gzip_reduction_percent']}% smaller under gzip than the strong structured summary. This is not a meaningful document-compression result; any Round C value must come from preservation behavior or operational structure, not this byte difference.",
            "",
            "## Paid-run stop rule",
            "",
            "The executor requires an explicit paid-run flag and acknowledgement of the exact preregistered call count. Do not run it until this gate and the stacked source-corpus PR are reviewed.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    result = run_audit()
    DEFAULT_RESULT_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    DEFAULT_REPORT_PATH.write_text(render_markdown(result), encoding="utf-8")
    print(render_markdown(result))


if __name__ == "__main__":
    main()
