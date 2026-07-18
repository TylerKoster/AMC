"""Experiment 013 gates for Round C packet, execution, and grading separation."""

from __future__ import annotations

import ast
import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from pilot.live_eval.round_c_grade import (
    grade_run,
    grade_saved_responses,
    load_persisted_responses,
)
from pilot.live_eval.round_c_live import atomic_write_json, validate_paid_acknowledgement
from pilot.live_eval.round_c_packet_audit import run_audit
from pilot.live_eval.round_c_protocol import (
    INPUT_PATH,
    PROTOCOL_PATH,
    build_packet,
    build_schedule,
    canonical_json,
    find_prohibited_keys,
    load_inputs,
    load_protocol,
    recover_task,
    protocol_fingerprint,
    sha256_value,
)


LIVE_PATH = Path(__file__).resolve().parents[1] / "live_eval" / "round_c_live.py"


def test_frozen_protocol_matches_input_and_declared_call_count() -> None:
    protocol = load_protocol(PROTOCOL_PATH)
    inputs = load_inputs(INPUT_PATH, protocol=protocol)
    schedule = build_schedule(inputs, protocol)
    assert protocol["status"] == "preregistered-not-run"
    assert len(schedule) == protocol["planned_calls"] == 60
    assert inputs["partition_sha256"] == protocol["input_partition_sha256"]
    assert inputs["capture_sha256"] == protocol["capture_sha256"]


def test_schedule_is_balanced_deterministic_and_randomized() -> None:
    protocol = load_protocol()
    inputs = load_inputs(protocol=protocol)
    first = build_schedule(inputs, protocol)
    second = build_schedule(inputs, protocol)
    assert first == second
    assert Counter(item["condition"] for item in first) == {
        condition: 20 for condition in protocol["conditions"]
    }
    grouped = sorted(
        first,
        key=lambda item: (item["condition"], item["case_id"], item["repetition"]),
    )
    assert first != grouped
    changed = copy.deepcopy(protocol)
    changed["random_seed"] += 1
    assert build_schedule(inputs, changed) != first
    assert len(sha256_value(first)) == 64


def test_all_packets_are_exactly_recoverable_and_answer_free() -> None:
    protocol = load_protocol()
    inputs = load_inputs(protocol=protocol)
    for task in inputs["tasks"]:
        for condition in protocol["conditions"]:
            packet = build_packet(task, condition)
            assert canonical_json(recover_task(packet, condition)) == canonical_json(task)
            assert find_prohibited_keys(packet) == []
            assert condition not in canonical_json(packet).decode("utf-8")


def test_packet_builder_rejects_unknown_condition() -> None:
    task = load_inputs()["tasks"][0]
    with pytest.raises(ValueError, match="Unknown Round C condition"):
        build_packet(task, "unknown")


def test_no_model_audit_passes_without_loading_contracts() -> None:
    result = run_audit()
    assert result["gate_pass"] is True
    assert result["model_calls"] == 0
    assert result["openai_api_calls"] == 0
    assert result["oracle_files_loaded"] == 0
    assert len(result["protocol_sha256"]) == 64
    assert len(result["schedule"]) == 60
    assert result["compression_comparison"]["meaningful_compression_claim"] is False
    assert result["compression_comparison"]["raw_reduction_percent"] < 3
    assert all(summary["semantic_fidelity_passes"] == 10 for summary in result["summaries"].values())


def test_live_executor_has_no_grader_or_contract_reference() -> None:
    source = LIVE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any("round_c_grade" in name for name in imported)
    assert "round_c_real_oracles" not in source
    assert "DEFAULT_CONTRACT_PATH" not in source


def test_atomic_json_write_replaces_complete_document(tmp_path: Path) -> None:
    target = tmp_path / "checkpoint.json"
    atomic_write_json(target, {"version": 1, "items": [1, 2]})
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "version": 1,
        "items": [1, 2],
    }
    atomic_write_json(target, {"version": 2, "items": []})
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "version": 2,
        "items": [],
    }
    assert list(tmp_path.glob("*.tmp")) == []


def test_paid_runner_requires_both_explicit_acknowledgements() -> None:
    with pytest.raises(SystemExit, match="Paid execution is disabled"):
        validate_paid_acknowledgement(False, None, 60)
    with pytest.raises(SystemExit, match="acknowledge-calls 60"):
        validate_paid_acknowledgement(True, 59, 60)
    validate_paid_acknowledgement(True, 60, 60)


def _complete_response_artifact() -> dict:
    return {
        "schema_version": "amc-round-c-live-responses/0.1",
        "status": "responses-persisted-ungraded",
        "responses_persisted": True,
        "planned_calls": 1,
        "completed_calls": 1,
        "runs": [{"decision": {}, "response_saved_at": "2026-07-18T00:00:00Z"}],
    }


def test_response_loader_rejects_partial_artifact(tmp_path: Path) -> None:
    value = _complete_response_artifact()
    value["status"] = "running-ungraded"
    value["responses_persisted"] = False
    path = tmp_path / "partial.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(ValueError, match="persisted-ungraded"):
        load_persisted_responses(path)


def test_grader_never_loads_contracts_when_response_validation_fails() -> None:
    calls: list[str] = []

    def bad_response_loader(_: Path) -> dict:
        calls.append("responses")
        raise ValueError("partial")

    def contract_loader(_: Path) -> dict:
        calls.append("contracts")
        return {}

    with pytest.raises(ValueError, match="partial"):
        grade_saved_responses(
            Path("responses.json"),
            Path("contracts.json"),
            response_loader=bad_response_loader,
            contract_loader=contract_loader,
        )
    assert calls == ["responses"]


def test_grader_load_order_is_responses_then_contracts() -> None:
    calls: list[str] = []
    protocol = load_protocol()
    inputs = load_inputs(protocol=protocol)
    schedule = build_schedule(inputs, protocol)
    empty_decision = {
        "preserved_facts": [],
        "actions": [],
        "cautions": [],
        "source_refs": [],
    }

    def response_loader(_: Path) -> dict:
        calls.append("responses")
        return {
            "experiment_id": protocol["experiment_id"],
            "status": "responses-persisted-ungraded",
            "protocol_sha256": protocol_fingerprint(protocol),
            "input_partition_sha256": inputs["partition_sha256"],
            "capture_sha256": protocol["capture_sha256"],
            "schedule_sha256": sha256_value(schedule),
            "random_seed": protocol["random_seed"],
            "model": protocol["model"],
            "planned_calls": protocol["planned_calls"],
            "runs": [{**item, "decision": empty_decision} for item in schedule],
        }

    def contract_loader(_: Path) -> dict:
        calls.append("contracts")
        return {
            "partition_sha256": "contracts",
            "capture_sha256": protocol["capture_sha256"],
            "contracts": [
                {
                    "case_id": task["case_id"],
                    "preservation_contract": {
                        "required_facts": [],
                        "required_source_ids": [],
                        "required_actions": [],
                        "forbidden_actions": [],
                    },
                }
                for task in inputs["tasks"]
            ],
        }

    result = grade_saved_responses(
        Path("responses.json"),
        Path("contracts.json"),
        response_loader=response_loader,
        contract_loader=contract_loader,
    )
    assert calls == ["responses", "contracts"]
    assert result["status"] == "graded-after-response-persistence"


def test_schedule_mutation_blocks_contract_loading() -> None:
    calls: list[str] = []
    protocol = load_protocol()
    inputs = load_inputs(protocol=protocol)
    schedule = build_schedule(inputs, protocol)
    mutated_schedule = copy.deepcopy(schedule)
    mutated_schedule[0], mutated_schedule[1] = mutated_schedule[1], mutated_schedule[0]

    def response_loader(_: Path) -> dict:
        calls.append("responses")
        return {
            "protocol_sha256": protocol_fingerprint(protocol),
            "input_partition_sha256": inputs["partition_sha256"],
            "capture_sha256": inputs["capture_sha256"],
            "schedule_sha256": sha256_value(schedule),
            "random_seed": protocol["random_seed"],
            "model": protocol["model"],
            "planned_calls": protocol["planned_calls"],
            "runs": [{**item, "decision": {}} for item in mutated_schedule],
        }

    def contract_loader(_: Path) -> dict:
        calls.append("contracts")
        return {}

    with pytest.raises(ValueError, match="frozen schedule"):
        grade_saved_responses(
            Path("responses.json"),
            Path("contracts.json"),
            response_loader=response_loader,
            contract_loader=contract_loader,
        )
    assert calls == ["responses"]


def test_protocol_mismatch_blocks_contract_loading() -> None:
    calls: list[str] = []

    def response_loader(_: Path) -> dict:
        calls.append("responses")
        return {
            "protocol_sha256": "tampered",
            "input_partition_sha256": "tampered",
            "capture_sha256": "tampered",
            "schedule_sha256": "tampered",
            "random_seed": -1,
            "model": "tampered",
            "planned_calls": -1,
            "runs": [],
        }

    def contract_loader(_: Path) -> dict:
        calls.append("contracts")
        return {}

    with pytest.raises(ValueError, match="frozen protocol field"):
        grade_saved_responses(
            Path("responses.json"),
            Path("contracts.json"),
            response_loader=response_loader,
            contract_loader=contract_loader,
        )
    assert calls == ["responses"]


def test_invalid_fact_json_is_scored_as_failure_not_grader_crash() -> None:
    run = {
        "case_id": "case",
        "condition": "minimal_amc_v2",
        "repetition": 1,
        "sequence": 1,
        "decision": {
            "preserved_facts": [
                {
                    "source_id": "source",
                    "key": "value",
                    "value_json": "not-json",
                    "response_sha256": "a" * 64,
                }
            ],
            "actions": [],
            "cautions": [],
            "source_refs": [],
        },
    }
    contract = {
        "required_facts": [
            {
                "source_id": "source",
                "key": "value",
                "value": 1,
                "response_sha256": "a" * 64,
            }
        ],
        "required_source_ids": [],
        "required_actions": [],
        "forbidden_actions": [],
    }
    grade = grade_run(run, contract)
    assert grade["invalid_fact_encodings"] == 1
    assert grade["observations"]["all_fact_encodings_valid"] is False
    assert grade["primary_pass"] is False
