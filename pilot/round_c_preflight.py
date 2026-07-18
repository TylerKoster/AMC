"""No-API Round C preflight for oracle semantics and packet leakage.

This module grades deterministic information availability. It does not grade
model behavior and must not be used to claim that one handoff format is better.
"""

from __future__ import annotations

import copy
import gzip
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUITE_PATH = (
    ROOT / "pilot" / "live_eval" / "evals" / "round_c_preflight_tasks_v1.json"
)
DEFAULT_RESULT_PATH = ROOT / "outputs" / "amc_round_c_preflight_011.json"
DEFAULT_REPORT_PATH = ROOT / "outputs" / "amc_round_c_preflight_experiment_011.md"

CONDITIONS = (
    "structured_summary_v2",
    "minimal_amc_v2",
    "full_history_control",
)
PROHIBITED_ORACLE_KEYS = frozenset(
    {
        "expected",
        "oracle",
        "next_action",
        "proposed_action",
        "affected_claim_ids",
        "affected_action_ids",
        "changed_claim_ids",
        "changed_action_ids",
        "changed_decision_ids",
    }
)
CAPABILITIES = (
    "exact_dependency",
    "stale_history_resolution",
    "negative_decision",
    "audit_reconstruction",
)


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def load_suite(path: Path = DEFAULT_SUITE_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_effect(effect: dict[str, Any]) -> tuple[str, str, str, Any, Any]:
    return (
        effect["entity_type"],
        effect["entity_id"],
        effect["field"],
        effect["before"],
        effect["after"],
    )


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": event["event_id"],
        "type": event["type"],
        "revision": event["revision"],
        "effects": sorted(_normalize_effect(effect) for effect in event["effects"]),
    }


def derive_impacts(events: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    """Derive changed IDs from typed field transitions, not referenced IDs."""

    changed: dict[str, set[str]] = {
        "claim": set(),
        "action": set(),
        "decision": set(),
    }
    for event in events:
        for effect in event["effects"]:
            if effect["before"] == effect["after"]:
                raise ValueError(
                    f"Event {event['event_id']} contains a non-changing effect"
                )
            entity_type = effect["entity_type"]
            if entity_type not in changed:
                raise ValueError(f"Unsupported effect entity type: {entity_type}")
            changed[entity_type].add(effect["entity_id"])
    return {
        "changed_claim_ids": sorted(changed["claim"]),
        "changed_action_ids": sorted(changed["action"]),
        "changed_decision_ids": sorted(changed["decision"]),
    }


def validate_suite(suite: dict[str, Any]) -> None:
    if suite.get("schema_version") != "round-c-preflight-suite/0.1":
        raise ValueError("Unsupported Round C preflight schema")
    case_ids: set[str] = set()
    for task in suite["tasks"]:
        case_id = task["case_id"]
        if case_id in case_ids:
            raise ValueError(f"Duplicate case_id: {case_id}")
        case_ids.add(case_id)
        required = set(task["required_capabilities"])
        unknown = required - set(CAPABILITIES)
        if unknown:
            raise ValueError(f"Unknown capabilities for {case_id}: {sorted(unknown)}")
        events = task["input"]["events"]
        event_ids = [event["event_id"] for event in events]
        if len(event_ids) != len(set(event_ids)):
            raise ValueError(f"Duplicate event_id in {case_id}")
        revisions = [event["revision"] for event in events]
        if revisions != sorted(revisions):
            raise ValueError(f"Events are not revision ordered in {case_id}")
        derived = derive_impacts(events)
        if derived != task["oracle"]["derived_impacts"]:
            raise ValueError(f"Declared impact oracle disagrees with effects in {case_id}")
        if event_ids != task["oracle"]["audit_event_ids"]:
            raise ValueError(f"Declared audit order disagrees with events in {case_id}")


def _structured_summary(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "structured-summary/round-c-0.1",
        "goal": value["goal"],
        "current": value["current"],
        "requirements": value["requirements"],
        "evidence_notes": [
            {
                "claim_id": claim["id"],
                "evidence_id": claim["evidence_id"],
                "claim_status": claim["status"],
            }
            for claim in value["claims"]
        ],
        "decisions": value["decisions"],
        "history_ref": value["history_ref"],
        "untrusted_operator_message": value["operator_pressure"],
    }


def _minimal_amc(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "amc-minimal-resolvable/round-c-0.2",
        "goal": value["goal"],
        "current": value["current"],
        "requirements": value["requirements"],
        "entities": {
            "evidence": value["evidence"],
            "claims": [
                {"id": claim["id"], "status": claim["status"]}
                for claim in value["claims"]
            ],
            "actions": value["actions"],
        },
        "links": {
            "evidence_to_claims": {
                evidence["id"]: sorted(
                    claim["id"]
                    for claim in value["claims"]
                    if claim["evidence_id"] == evidence["id"]
                )
                for evidence in value["evidence"]
            }
        },
        "decision_ledger": value["decisions"],
        "recent_deltas": value["events"],
        "history_ref": value["history_ref"],
        "authority": {
            "operator_message": value["operator_pressure"],
            "operator_message_can_mutate_state": False,
        },
    }


def _full_history(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "full-history/round-c-0.1",
        "goal": value["goal"],
        "history_ref": value["history_ref"],
        "snapshots": [
            {"position": "prior", "state": value["prior"]},
            {"position": "current", "state": value["current"]},
        ],
        "requirements": value["requirements"],
        "evidence": value["evidence"],
        "claims": value["claims"],
        "actions": value["actions"],
        "decisions": value["decisions"],
        "events": value["events"],
        "untrusted_operator_message": value["operator_pressure"],
    }


def build_packet(task: dict[str, Any], condition: str) -> dict[str, Any]:
    """Build from task input only; the oracle object is never passed to a builder."""

    builders = {
        "structured_summary_v2": _structured_summary,
        "minimal_amc_v2": _minimal_amc,
        "full_history_control": _full_history,
    }
    try:
        builder = builders[condition]
    except KeyError as exc:
        raise ValueError(f"Unknown condition: {condition}") from exc
    return builder(copy.deepcopy(task["input"]))


def find_oracle_leaks(value: Any, path: str = "$") -> list[str]:
    leaks: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if key in PROHIBITED_ORACLE_KEYS:
                leaks.append(child)
            leaks.extend(find_oracle_leaks(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            leaks.extend(find_oracle_leaks(item, f"{path}[{index}]"))
    return leaks


def _dependency_edges(packet: dict[str, Any]) -> set[tuple[str, str]]:
    if "links" in packet:
        return {
            (evidence_id, claim_id)
            for evidence_id, claim_ids in packet["links"][
                "evidence_to_claims"
            ].items()
            for claim_id in claim_ids
        }
    if "evidence_notes" in packet:
        return {
            (item["evidence_id"], item["claim_id"])
            for item in packet["evidence_notes"]
        }
    if "claims" in packet:
        return {(claim["evidence_id"], claim["id"]) for claim in packet["claims"]}
    return set()


def _current_revision(packet: dict[str, Any]) -> int | None:
    if "current" in packet:
        return packet["current"].get("revision")
    for snapshot in packet.get("snapshots", []):
        if snapshot["position"] == "current":
            return snapshot["state"].get("revision")
    return None


def _decisions(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return packet.get("decision_ledger", packet.get("decisions", []))


def _events(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return packet.get("recent_deltas", packet.get("events", []))


def grade_packet(task: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    oracle = task["oracle"]
    expected_edges = {
        (edge["evidence_id"], edge["claim_id"])
        for edge in oracle["dependency_edges"]
    }
    expected_decisions = {
        (item["id"], item["status"], item["reason_code"])
        for item in oracle["negative_decisions"]
    }
    actual_decisions = {
        (item["id"], item["status"], item["reason_code"])
        for item in _decisions(packet)
        if item["status"] in {"rejected", "inactive", "superseded"}
    }
    actual_events = [normalize_event(event) for event in _events(packet)]
    expected_events = [
        normalize_event(event) for event in task["input"]["events"]
    ]
    capabilities = {
        "exact_dependency": _dependency_edges(packet) == expected_edges,
        "stale_history_resolution": _current_revision(packet)
        == oracle["current_revision"],
        "negative_decision": actual_decisions == expected_decisions,
        "audit_reconstruction": actual_events == expected_events,
    }
    required = task["required_capabilities"]
    leaks = find_oracle_leaks(packet)
    return {
        "capabilities": capabilities,
        "required_capabilities": required,
        "required_capabilities_pass": all(capabilities[name] for name in required),
        "history_resolver_available": packet.get("history_ref")
        == task["input"]["history_ref"],
        "oracle_leaks": leaks,
        "contract_pass": not leaks and all(capabilities[name] for name in required),
    }


def packet_metrics(packet: dict[str, Any]) -> dict[str, int]:
    raw = canonical_json(packet)
    return {"raw_bytes": len(raw), "gzip_bytes": len(gzip.compress(raw))}


def _drop_dependency_links(packet: dict[str, Any]) -> None:
    packet.pop("links", None)


def _drop_current_revision(packet: dict[str, Any]) -> None:
    packet["current"].pop("revision", None)


def _activate_negative_decision(packet: dict[str, Any]) -> None:
    for decision in packet["decision_ledger"]:
        if decision["status"] in {"rejected", "inactive", "superseded"}:
            decision["status"] = "active"
            return


def _drop_audit_effects(packet: dict[str, Any]) -> None:
    for event in packet["recent_deltas"]:
        event["effects"] = []


def _reverse_audit_order(packet: dict[str, Any]) -> None:
    packet["recent_deltas"].reverse()


def _inject_answer_field(packet: dict[str, Any]) -> None:
    packet["next_action"] = "publish"


def mutation_results(suite: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = {task["case_id"]: task for task in suite["tasks"]}
    definitions = (
        (
            "drop_dependency_links",
            "dependency_edge_case",
            "exact_dependency",
            _drop_dependency_links,
            "capability",
        ),
        (
            "drop_current_revision",
            "stale_revision_case",
            "stale_history_resolution",
            _drop_current_revision,
            "capability",
        ),
        (
            "activate_negative_decision",
            "negative_decision_case",
            "negative_decision",
            _activate_negative_decision,
            "capability",
        ),
        (
            "drop_audit_effects",
            "audit_sequence_case",
            "audit_reconstruction",
            _drop_audit_effects,
            "capability",
        ),
        (
            "reverse_audit_order",
            "audit_sequence_case",
            "audit_reconstruction",
            _reverse_audit_order,
            "capability",
        ),
        (
            "inject_answer_field",
            "dependency_edge_case",
            "oracle_free",
            _inject_answer_field,
            "leak",
        ),
    )
    results: list[dict[str, Any]] = []
    for name, case_id, target, mutate, mode in definitions:
        task = tasks[case_id]
        packet = build_packet(task, "minimal_amc_v2")
        mutate(packet)
        grade = grade_packet(task, packet)
        killed = bool(grade["oracle_leaks"]) if mode == "leak" else not grade[
            "capabilities"
        ][target]
        results.append(
            {
                "mutant": name,
                "case_id": case_id,
                "target": target,
                "killed": killed,
            }
        )
    return results


def run_preflight(suite: dict[str, Any]) -> dict[str, Any]:
    validate_suite(suite)
    runs: list[dict[str, Any]] = []
    for task in suite["tasks"]:
        for condition in CONDITIONS:
            packet = build_packet(task, condition)
            runs.append(
                {
                    "case_id": task["case_id"],
                    "condition": condition,
                    "metrics": packet_metrics(packet),
                    "grade": grade_packet(task, packet),
                }
            )
    summary: dict[str, Any] = {}
    for condition in CONDITIONS:
        condition_runs = [run for run in runs if run["condition"] == condition]
        summary[condition] = {
            "contract_passes": sum(
                run["grade"]["contract_pass"] for run in condition_runs
            ),
            "tasks": len(condition_runs),
            "total_raw_bytes": sum(run["metrics"]["raw_bytes"] for run in condition_runs),
            "total_gzip_bytes": sum(
                run["metrics"]["gzip_bytes"] for run in condition_runs
            ),
            "oracle_leaks": sum(
                bool(run["grade"]["oracle_leaks"]) for run in condition_runs
            ),
        }
    mutants = mutation_results(suite)
    return {
        "experiment": "AMC Round C oracle/leakage preflight 011",
        "status": "synthetic deterministic preflight",
        "api_calls": 0,
        "suite_sha256": hashlib.sha256(canonical_json(suite)).hexdigest(),
        "impact_semantics": suite["impact_semantics"],
        "summary": summary,
        "mutation_score": {
            "killed": sum(result["killed"] for result in mutants),
            "total": len(mutants),
        },
        "mutations": mutants,
        "runs": runs,
    }


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# AMC Round C oracle/leakage preflight - Experiment 011",
        "",
        "## Run Result",
        "",
        "**COMPLETE - deterministic synthetic preflight only.** No model or network calls were used.",
        "",
        "This run fixes the Round B measurement weakness where complete packets contained precomputed answer fields. Round B remains evidence that the runner and formats were interpreted consistently; it is not evidence that the model independently resolved the answers.",
        "",
        "| Condition | Contract passes | Raw bytes | Gzip bytes | Oracle leaks |",
        "|---|---:|---:|---:|---:|",
    ]
    for condition in CONDITIONS:
        summary = result["summary"][condition]
        lines.append(
            f"| {condition} | {summary['contract_passes']}/{summary['tasks']} | "
            f"{summary['total_raw_bytes']} | {summary['total_gzip_bytes']} | "
            f"{summary['oracle_leaks']} |"
        )
    score = result["mutation_score"]
    lines.extend(
        [
            "",
            "## Oracle rule",
            "",
            "An identifier is affected only when a typed event effect changes one of its canonical fields. Merely mentioning an identifier does not make it affected. Task-level impact is the set union of those direct field transitions, while audit order remains event order.",
            "",
            "## Mutation result",
            "",
            f"Killed {score['killed']}/{score['total']} targeted preflight mutants.",
            "",
            "## Interpretation",
            "",
            "The structured summary is a strong baseline: it retains typed evidence links and negative decisions instead of being deliberately weakened. It lacks inline event effects, so audit reconstruction requires its history resolver. The minimal AMC carries recent typed deltas inline at additional byte cost. This is an information-availability result, not a model-performance result.",
            "",
            "## Next gate",
            "",
            "Do not run the ten-trajectory paid Round C comparison yet. First collect fresh real trajectories and freeze task-specific preservation contracts. The live runner must build every packet from the input partition only, keep the oracle inaccessible, allow resolver requests, and count retrieved bytes and calls.",
            "",
            f"Suite SHA-256: `{result['suite_sha256']}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    suite = load_suite()
    result = run_preflight(suite)
    DEFAULT_RESULT_PATH.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    DEFAULT_REPORT_PATH.write_text(render_markdown(result), encoding="utf-8")
    print(render_markdown(result))


if __name__ == "__main__":
    main()
