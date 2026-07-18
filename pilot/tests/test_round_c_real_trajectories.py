"""Quality gates for the source-backed Round C corpus."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pilot.round_c_real_trajectories import (
    DEFAULT_CAPTURE_PATH,
    DEFAULT_INPUT_PATH,
    DEFAULT_MANIFEST_PATH,
    DEFAULT_ORACLE_PATH,
    find_prohibited_keys,
    freeze_partitions,
    load_manifest,
    validate_partitions,
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def artifacts() -> tuple[dict, dict, dict, dict]:
    return (
        load_manifest(DEFAULT_MANIFEST_PATH),
        load_json(DEFAULT_CAPTURE_PATH),
        load_json(DEFAULT_INPUT_PATH),
        load_json(DEFAULT_ORACLE_PATH),
    )


def test_frozen_corpus_passes_all_partition_gates() -> None:
    manifest, capture, inputs, oracles = artifacts()
    validate_partitions(manifest, capture, inputs, oracles)
    assert len(inputs["tasks"]) == 10
    assert len({task["portal_family"] for task in inputs["tasks"]}) >= 8


def test_every_capture_is_fresh_hash_bound_and_body_free() -> None:
    _, capture, _, _ = artifacts()
    assert capture["model_calls"] == 0
    assert capture["response_bodies_stored"] is False
    for case in capture["cases"]:
        for source in case["captures"]:
            assert source["http_status"] == 200
            assert len(source["response_sha256"]) == 64
            assert source["content_length_bytes"] > 0
            assert "body" not in source


def test_inputs_contain_no_oracle_contract_keys() -> None:
    _, _, inputs, _ = artifacts()
    assert find_prohibited_keys(inputs) == []
    encoded = json.dumps(inputs, sort_keys=True)
    assert "required_actions" not in encoded
    assert "forbidden_actions" not in encoded
    assert "decision_rule" not in encoded


def test_observed_and_injected_state_are_explicitly_separated() -> None:
    _, _, inputs, _ = artifacts()
    for task in inputs["tasks"]:
        assert task["observed_external_state"]
        assert task["injected_test_state"]["kind"] == "controlled_operator_pressure"
        assert task["injected_test_state"]["authority"] == "untrusted_and_non_mutating"


def test_every_required_fact_is_bound_to_exact_primary_capture() -> None:
    _, capture, _, oracles = artifacts()
    captured = {case["case_id"]: case for case in capture["cases"]}
    for item in oracles["contracts"]:
        primary = next(
            source
            for source in captured[item["case_id"]]["captures"]
            if source["role"] == "primary"
        )
        for fact in item["preservation_contract"]["required_facts"]:
            assert fact["source_id"] == primary["source_id"]
            assert fact["response_sha256"] == primary["response_sha256"]
            assert fact["value"] == primary["observations"][fact["key"]]


def test_oracle_changes_cannot_mutate_physical_input_partition() -> None:
    _, _, inputs, oracles = artifacts()
    before = copy.deepcopy(inputs)
    oracles["contracts"][0]["preservation_contract"]["required_actions"] = [
        "oracle-sentinel"
    ]
    assert inputs == before
    assert load_json(DEFAULT_INPUT_PATH) == before


def test_manifest_contract_mutation_breaks_capture_binding() -> None:
    manifest, capture, inputs, oracles = artifacts()
    broken = copy.deepcopy(manifest)
    broken["cases"][0]["contract_template"]["decision_rule"] = "mutated"
    with pytest.raises(ValueError, match="Capture is not bound"):
        validate_partitions(broken, capture, inputs, oracles)


def test_missing_required_observation_prevents_freeze() -> None:
    manifest, capture, _, _ = artifacts()
    broken = copy.deepcopy(capture)
    primary = next(
        source
        for source in broken["cases"][0]["captures"]
        if source["role"] == "primary"
    )
    primary["observations"].pop("dataset_id")
    with pytest.raises(ValueError, match="Missing required observations"):
        freeze_partitions(manifest, broken)


def test_bad_response_hash_prevents_validation() -> None:
    manifest, capture, inputs, oracles = artifacts()
    broken = copy.deepcopy(capture)
    broken["cases"][0]["captures"][0]["response_sha256"] = "bad"
    with pytest.raises(ValueError, match="Capture SHA-256 does not match"):
        validate_partitions(manifest, broken, inputs, oracles)


def test_contract_fact_mutation_breaks_oracle_partition_integrity() -> None:
    manifest, capture, inputs, oracles = artifacts()
    broken = copy.deepcopy(oracles)
    broken["contracts"][0]["preservation_contract"]["required_facts"][0]["value"] = "mutated"
    with pytest.raises(ValueError, match="Oracle partition SHA-256 does not match"):
        validate_partitions(manifest, capture, inputs, broken)
