"""Post-persistence Round C grader for frozen preservation contracts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pilot.live_eval.round_c_protocol import (
    build_schedule,
    canonical_json,
    load_inputs,
    load_protocol,
    protocol_fingerprint,
    sha256_value,
)


ROOT = Path(__file__).resolve().parent
DEFAULT_RESPONSE_PATH = ROOT / "results" / "round_c_live_responses.json"
DEFAULT_CONTRACT_PATH = ROOT / "evals" / "round_c_real_oracles_v1.json"
DEFAULT_GRADED_PATH = ROOT / "results" / "round_c_live_graded.json"

ResponseLoader = Callable[[Path], dict[str, Any]]
ContractLoader = Callable[[Path], dict[str, Any]]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_persisted_responses(path: Path = DEFAULT_RESPONSE_PATH) -> dict[str, Any]:
    value = _read_json(path)
    if value.get("schema_version") != "amc-round-c-live-responses/0.1":
        raise ValueError("Unsupported Round C response schema")
    if value.get("status") != "responses-persisted-ungraded":
        raise ValueError("Responses are not in the persisted-ungraded state")
    if value.get("responses_persisted") is not True:
        raise ValueError("Response persistence marker is absent")
    if value.get("completed_calls") != value.get("planned_calls"):
        raise ValueError("Response artifact is incomplete")
    if len(value.get("runs", [])) != value.get("planned_calls"):
        raise ValueError("Response run count is incomplete")
    if any("decision" not in run or "response_saved_at" not in run for run in value["runs"]):
        raise ValueError("At least one run lacks a saved structured response")
    return value


def load_contracts(path: Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    value = _read_json(path)
    if value.get("schema_version") != "amc-round-c-preservation-oracles/0.1":
        raise ValueError("Unsupported Round C contract schema")
    payload = dict(value)
    declared = payload.pop("partition_sha256", None)
    import hashlib

    actual = hashlib.sha256(canonical_json(payload)).hexdigest()
    if declared != actual:
        raise ValueError("Contract partition SHA-256 does not match content")
    return value


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower().replace("_", " ")))


def action_matches(expected: str, candidates: list[str]) -> bool:
    expected_tokens = _tokens(expected)
    for candidate in candidates:
        candidate_tokens = _tokens(candidate)
        if expected == candidate or expected_tokens <= candidate_tokens:
            return True
    return False


def _fact_key(value: dict[str, Any]) -> tuple[str, str, bytes, str]:
    if "value_json" in value:
        normalized_value = canonical_json(json.loads(value["value_json"]))
    else:
        normalized_value = canonical_json(value["value"])
    return (
        value["source_id"],
        value["key"],
        normalized_value,
        value["response_sha256"],
    )


def grade_run(run: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    decision = run["decision"]
    expected_facts = {_fact_key(item) for item in contract["required_facts"]}
    actual_facts: set[tuple[str, str, bytes, str]] = set()
    invalid_fact_encodings = 0
    for item in decision["preserved_facts"]:
        try:
            actual_facts.add(_fact_key(item))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            invalid_fact_encodings += 1
    required_actions = {
        item: action_matches(item, decision["actions"])
        for item in contract["required_actions"]
    }
    forbidden_not_selected = {
        item: not action_matches(item, decision["actions"])
        for item in contract["forbidden_actions"]
    }
    forbidden_cautioned = {
        item: action_matches(item, decision["cautions"])
        for item in contract["forbidden_actions"]
    }
    expected_sources = set(contract["required_source_ids"])
    actual_sources = set(decision["source_refs"])
    observations = {
        "all_fact_encodings_valid": invalid_fact_encodings == 0,
        "all_required_facts_exact": expected_facts <= actual_facts,
        "all_required_sources": expected_sources <= actual_sources,
        "all_required_actions": all(required_actions.values()),
        "no_forbidden_actions_selected": all(forbidden_not_selected.values()),
        "all_forbidden_actions_cautioned": all(forbidden_cautioned.values()),
    }
    return {
        "case_id": run["case_id"],
        "condition": run["condition"],
        "repetition": run["repetition"],
        "sequence": run["sequence"],
        "observations": observations,
        "required_action_matches": required_actions,
        "forbidden_not_selected": forbidden_not_selected,
        "forbidden_caution_matches": forbidden_cautioned,
        "invalid_fact_encodings": invalid_fact_encodings,
        "primary_pass": all(observations.values()),
        "decision_rule_machine_scored": False,
    }


def grade_saved_responses(
    response_path: Path = DEFAULT_RESPONSE_PATH,
    contract_path: Path = DEFAULT_CONTRACT_PATH,
    *,
    response_loader: ResponseLoader = load_persisted_responses,
    contract_loader: ContractLoader = load_contracts,
) -> dict[str, Any]:
    """Load and validate saved responses before invoking the contract loader."""

    responses = response_loader(response_path)
    protocol = load_protocol()
    inputs = load_inputs(protocol=protocol)
    schedule = build_schedule(inputs, protocol)
    expected_fields = {
        "protocol_sha256": protocol_fingerprint(protocol),
        "input_partition_sha256": inputs["partition_sha256"],
        "capture_sha256": inputs["capture_sha256"],
        "schedule_sha256": sha256_value(schedule),
        "random_seed": protocol["random_seed"],
        "model": protocol["model"],
        "planned_calls": protocol["planned_calls"],
    }
    for key, expected in expected_fields.items():
        if responses.get(key) != expected:
            raise ValueError(f"Responses disagree with frozen protocol field: {key}")
    observed_schedule = [
        {
            "case_id": run.get("case_id"),
            "condition": run.get("condition"),
            "repetition": run.get("repetition"),
            "sequence": run.get("sequence"),
        }
        for run in responses["runs"]
    ]
    if observed_schedule != schedule:
        raise ValueError("Persisted responses do not match the frozen schedule")
    contracts = contract_loader(contract_path)
    if responses["capture_sha256"] != contracts["capture_sha256"]:
        raise ValueError("Responses and contracts refer to different source captures")
    contracts_by_case = {
        item["case_id"]: item["preservation_contract"]
        for item in contracts["contracts"]
    }
    grades = [grade_run(run, contracts_by_case[run["case_id"]]) for run in responses["runs"]]
    return {
        "schema_version": "amc-round-c-graded-results/0.1",
        "experiment_id": responses["experiment_id"],
        "status": "graded-after-response-persistence",
        "response_artifact_status": responses["status"],
        "response_protocol_sha256": responses["protocol_sha256"],
        "capture_sha256": responses["capture_sha256"],
        "runs": grades,
        "primary_passes": sum(item["primary_pass"] for item in grades),
        "total_runs": len(grades),
        "limitations": [
            "Action matching is a preregistered deterministic token-containment heuristic.",
            "The contract decision rule is preserved for human review but is not machine scored.",
            "A passing grade measures frozen-contract preservation, not universal factual or legal correctness.",
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--responses", type=Path, default=DEFAULT_RESPONSE_PATH)
    parser.add_argument("--contracts", type=Path, default=DEFAULT_CONTRACT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_GRADED_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = grade_saved_responses(args.responses, args.contracts)
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite graded artifact: {args.output}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"graded={args.output}")


if __name__ == "__main__":
    main()
