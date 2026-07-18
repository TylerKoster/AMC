from __future__ import annotations

import json
from pathlib import Path

from pilot.gate_dispatcher import GateState, allowed_actions, validate_state
from pilot.live_eval.round_b_smoke import grade_decision
from pilot.live_eval.round_b_variants import (
    ALL_CONDITIONS,
    build_condition_packet,
    build_schedule,
    canonical_json,
    expected_for_condition,
)


SUITE_PATH = (
    Path(__file__).resolve().parents[1]
    / "live_eval"
    / "evals"
    / "round_b_smoke_tasks_v1.json"
)


def load_suite() -> dict:
    return json.loads(SUITE_PATH.read_text(encoding="utf-8"))


def test_five_tasks_cover_each_dispatcher_phase_exactly_once() -> None:
    suite = load_suite()
    assert len(suite["tasks"]) == 5
    expected_actions = []
    for task in suite["tasks"]:
        prior = GateState(**task["prior_gate_state"])
        current = GateState(**task["gate_state"])
        validate_state(prior)
        validate_state(current)
        allowed = allowed_actions(current)
        assert allowed == {task["expected"]["proposed_action"]}
        expected_actions.extend(allowed)
    assert set(expected_actions) == {
        "refresh_evidence",
        "verify_license",
        "form_recommendation",
        "request_publication_approval",
        "publish",
    }


def test_schedule_is_balanced_deterministic_and_has_sixty_calls() -> None:
    suite = load_suite()
    first = build_schedule(suite)
    second = build_schedule(suite)
    assert first == second
    assert len(first) == 60
    cells = {
        (item["case_id"], item["condition"], item["repetition"])
        for item in first
    }
    assert len(cells) == 60
    assert {item["condition"] for item in first} == set(ALL_CONDITIONS)


def test_packets_are_deterministic_and_do_not_leak_expected_oracle() -> None:
    suite = load_suite()
    for task in suite["tasks"]:
        for condition in ALL_CONDITIONS:
            first = build_condition_packet(task, condition)
            second = build_condition_packet(task, condition)
            assert canonical_json(first) == canonical_json(second)
            assert "expected" not in first
            assert task["goal"] in canonical_json(first).decode("utf-8")


def test_incomplete_control_omits_current_state_and_requires_lookup() -> None:
    task = load_suite()["tasks"][0]
    packet = build_condition_packet(task, "incomplete_negative_control")
    expected = expected_for_condition(task, "incomplete_negative_control")
    assert "workflow_state" not in packet
    assert not any(
        isinstance(value, dict) and "evidence_current" in value
        for value in packet.values()
    )
    assert expected["proposed_action"] == "request_history_lookup"
    assert expected["history_lookup"] is True


def test_complete_packet_grade_accepts_exact_oracle_decision() -> None:
    task = load_suite()["tasks"][0]
    expected = expected_for_condition(task, "minimal_resolvable_amc")
    decision = {
        key: value
        for key, value in expected.items()
        if key
        in {
            "goal",
            "proposed_action",
            "evidence_status",
            "requirement_status",
            "approval_status",
            "affected_claim_ids",
            "affected_action_ids",
            "history_lookup",
        }
    }
    decision["rationale"] = "The current gate requires evidence refresh."
    result = grade_decision(decision, task, "minimal_resolvable_amc")
    assert result["primary_pass"] is True
    assert result["dispatcher_event"]["type"] == "action_accepted"


def test_incomplete_control_grade_rewards_safe_lookup_not_execution() -> None:
    task = load_suite()["tasks"][-1]
    expected = expected_for_condition(task, "incomplete_negative_control")
    decision = {
        key: value
        for key, value in expected.items()
        if key
        in {
            "goal",
            "proposed_action",
            "evidence_status",
            "requirement_status",
            "approval_status",
            "affected_claim_ids",
            "affected_action_ids",
            "history_lookup",
        }
    }
    decision["rationale"] = "Current state is intentionally omitted."
    result = grade_decision(decision, task, "incomplete_negative_control")
    assert result["primary_pass"] is True
    assert result["safe_history_abstention"] is True
    assert result["dispatcher_event"]["type"] == "action_rejected"
