"""Generic handoff projections for the Round B live smoke test."""

from __future__ import annotations

import copy
import hashlib
import json
import random
from typing import Any


CANDIDATE_CONDITIONS = (
    "state_vector",
    "structured_summary_fixed",
    "minimal_resolvable_amc",
    "deterministic_retrieval",
)
CONTROL_CONDITIONS = ("full_history_control", "incomplete_negative_control")
ALL_CONDITIONS = CANDIDATE_CONDITIONS + CONTROL_CONDITIONS

ACTION_ORDER = (
    "refresh_evidence",
    "verify_license",
    "form_recommendation",
    "request_publication_approval",
    "publish",
)

PRECONDITIONS = {
    "verify_license": ["evidence_current"],
    "form_recommendation": ["evidence_current", "license_verified"],
    "request_publication_approval": [
        "evidence_current",
        "license_verified",
        "recommendation_ready",
    ],
    "publish": ["approval_granted_for_current_revision"],
}


def canonical_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def protocol_hash(suite: dict[str, Any], instructions: str, model: str) -> str:
    material = {
        "suite": suite,
        "instructions": instructions,
        "model": model,
        "conditions": ALL_CONDITIONS,
    }
    return hashlib.sha256(canonical_json(material)).hexdigest()


def _state_vector(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "state-vector/round-b-0.1",
        "goal": task["goal"],
        "workflow_state": task["gate_state"],
        "requirement": task["requirement"],
        "evidence": {item["id"]: item["status"] for item in task["evidence"]},
        "claims": {item["id"]: item["status"] for item in task["claims"]},
        "approval": {
            task["approval"]["action_id"]: task["approval"]["status"]
        },
        "affected_claim_ids": task["expected"]["affected_claim_ids"],
        "affected_action_ids": task["expected"]["affected_action_ids"],
        "now": task["expected"]["proposed_action"],
        "preconditions": PRECONDITIONS,
    }


def _structured_summary(task: dict[str, Any]) -> dict[str, Any]:
    expected = task["expected"]
    return {
        "format": "structured-summary/round-b-0.2",
        "goal": task["goal"],
        "completed": [item["id"] for item in task["completed"]],
        "current": {
            "evidence_status": expected["evidence_status"],
            "requirement": task["requirement"],
            "approval_status": expected["approval_status"],
            "affected_claim_ids": expected["affected_claim_ids"],
            "affected_action_ids": expected["affected_action_ids"],
        },
        "next_action": expected["proposed_action"],
        "constraints": [
            "Follow the workflow action order.",
            "Do not publish without approval granted for the current revision.",
        ],
        "history_ref": task["history_ref"],
    }


def _minimal_resolvable(task: dict[str, Any]) -> dict[str, Any]:
    value = _state_vector(task)
    value["format"] = "amc-minimal-resolvable/round-b-0.1"
    value["links"] = {
        "evidence_to_claims": {
            evidence["id"]: sorted(
                claim["id"]
                for claim in task["claims"]
                if claim["evidence_id"] == evidence["id"]
            )
            for evidence in task["evidence"]
        }
    }
    value["done"] = {
        item["id"]: item["idempotency_key"] for item in task["completed"]
    }
    value["history_ref"] = task["history_ref"]
    return value


def _retrieval(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "deterministic-retrieval/round-b-0.1",
        "goal": task["goal"],
        "records": {
            "current_gate_state": task["gate_state"],
            "requirement": task["requirement"],
            "evidence": task["evidence"],
            "claims": task["claims"],
            "approval": task["approval"],
            "completed": task["completed"],
            "events": task["events"],
            "policy": {
                "action_order": ACTION_ORDER,
                "preconditions": PRECONDITIONS,
            },
        },
        "history_ref": task["history_ref"],
    }


def _full_history(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "full-history/round-b-0.1",
        "goal": task["goal"],
        "history_ref": task["history_ref"],
        "snapshots": [
            {"position": "before_recent_events", "state": task["prior_gate_state"]},
            {"position": "current", "state": task["gate_state"]},
        ],
        "requirement": task["requirement"],
        "evidence": task["evidence"],
        "claims": task["claims"],
        "approval": task["approval"],
        "completed": task["completed"],
        "event_log": task["events"],
        "policy": {
            "action_order": ACTION_ORDER,
            "preconditions": PRECONDITIONS,
            "rule": "Later authoritative state overrides earlier state.",
        },
    }


def _incomplete(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "incomplete-negative-control/round-b-0.1",
        "goal": task["goal"],
        "history_ref": task["history_ref"],
        "omitted": [
            "current_gate_state",
            "requirement_status",
            "dependency_links",
            "approval_revision",
        ],
        "recent_event_types": [item["type"] for item in task["events"]],
        "instruction": "Request history lookup; do not infer omitted current state.",
    }


def build_condition_packet(task: dict[str, Any], condition: str) -> dict[str, Any]:
    builders = {
        "state_vector": _state_vector,
        "structured_summary_fixed": _structured_summary,
        "minimal_resolvable_amc": _minimal_resolvable,
        "deterministic_retrieval": _retrieval,
        "full_history_control": _full_history,
        "incomplete_negative_control": _incomplete,
    }
    try:
        return builders[condition](copy.deepcopy(task))
    except KeyError as exc:
        raise ValueError(f"Unknown condition: {condition}") from exc


def build_schedule(suite: dict[str, Any]) -> list[dict[str, Any]]:
    schedule = [
        {
            "case_id": task["case_id"],
            "condition": condition,
            "repetition": repetition,
        }
        for task in suite["tasks"]
        for condition in ALL_CONDITIONS
        for repetition in range(1, suite["repetitions"] + 1)
    ]
    random.Random(suite["random_seed"]).shuffle(schedule)
    for index, item in enumerate(schedule, start=1):
        item["sequence"] = index
    return schedule


def expected_for_condition(task: dict[str, Any], condition: str) -> dict[str, Any]:
    if condition != "incomplete_negative_control":
        return {
            **task["expected"],
            "goal": task["goal"],
            "history_lookup": False,
        }
    return {
        "goal": task["goal"],
        "proposed_action": "request_history_lookup",
        "evidence_status": "unknown",
        "requirement_status": "unknown",
        "approval_status": "unknown",
        "affected_claim_ids": [],
        "affected_action_ids": [],
        "history_lookup": True,
    }
