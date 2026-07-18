"""Tests for the Round C oracle/leakage preflight."""

from __future__ import annotations

import copy

import pytest

from pilot.round_c_preflight import (
    CONDITIONS,
    build_packet,
    canonical_json,
    derive_impacts,
    find_oracle_leaks,
    grade_packet,
    load_suite,
    mutation_results,
    run_preflight,
    validate_suite,
)


def task_by_id(case_id: str) -> dict:
    return next(task for task in load_suite()["tasks"] if task["case_id"] == case_id)


def test_suite_has_frozen_event_effect_semantics() -> None:
    suite = load_suite()
    validate_suite(suite)
    assert suite["status"] == "synthetic-preflight-not-real-trajectories"
    assert len(suite["tasks"]) == 4


def test_impact_oracle_counts_changes_not_mentions() -> None:
    events = [
        {
            "event_id": "event-1",
            "type": "evidence_reviewed",
            "revision": 1,
            "referenced_claim_id": "claim-mentioned-only",
            "effects": [
                {
                    "entity_type": "claim",
                    "entity_id": "claim-actually-changed",
                    "field": "status",
                    "before": "unknown",
                    "after": "supported",
                }
            ],
        }
    ]
    assert derive_impacts(events) == {
        "changed_claim_ids": ["claim-actually-changed"],
        "changed_action_ids": [],
        "changed_decision_ids": [],
    }


def test_nonchanging_effect_is_rejected() -> None:
    events = [
        {
            "event_id": "event-1",
            "type": "bad_event",
            "revision": 1,
            "effects": [
                {
                    "entity_type": "claim",
                    "entity_id": "claim-1",
                    "field": "status",
                    "before": "supported",
                    "after": "supported",
                }
            ],
        }
    ]
    with pytest.raises(ValueError, match="non-changing effect"):
        derive_impacts(events)


def test_packet_builders_are_deterministic_and_oracle_partitioned() -> None:
    for task in load_suite()["tasks"]:
        altered = copy.deepcopy(task)
        altered["oracle"] = {
            "sentinel": "A packet builder must never see this object."
        }
        for condition in CONDITIONS:
            first = build_packet(task, condition)
            second = build_packet(task, condition)
            altered_packet = build_packet(altered, condition)
            assert canonical_json(first) == canonical_json(second)
            assert canonical_json(first) == canonical_json(altered_packet)
            assert find_oracle_leaks(first) == []


def test_strong_summary_keeps_edges_and_negative_decisions_without_answers() -> None:
    dependency_task = task_by_id("dependency_edge_case")
    packet = build_packet(dependency_task, "structured_summary_v2")
    grade = grade_packet(dependency_task, packet)
    assert grade["capabilities"]["exact_dependency"] is True
    assert grade["capabilities"]["negative_decision"] is True
    assert "next_action" not in packet
    assert "affected_claim_ids" not in canonical_json(packet).decode("utf-8")


def test_summary_requires_resolver_for_exact_audit_reconstruction() -> None:
    task = task_by_id("audit_sequence_case")
    summary = grade_packet(task, build_packet(task, "structured_summary_v2"))
    minimal = grade_packet(task, build_packet(task, "minimal_amc_v2"))
    full = grade_packet(task, build_packet(task, "full_history_control"))
    assert summary["capabilities"]["audit_reconstruction"] is False
    assert summary["history_resolver_available"] is True
    assert minimal["capabilities"]["audit_reconstruction"] is True
    assert full["capabilities"]["audit_reconstruction"] is True


def test_all_targeted_preflight_mutants_are_killed() -> None:
    results = mutation_results(load_suite())
    assert len(results) == 6
    assert all(result["killed"] for result in results)


def test_preflight_reports_expected_information_availability() -> None:
    result = run_preflight(load_suite())
    assert result["api_calls"] == 0
    assert result["summary"]["structured_summary_v2"]["contract_passes"] == 3
    assert result["summary"]["minimal_amc_v2"]["contract_passes"] == 4
    assert result["summary"]["full_history_control"]["contract_passes"] == 4
    assert result["mutation_score"] == {"killed": 6, "total": 6}


def test_leak_detector_reports_nested_answer_fields() -> None:
    packet = {"safe": {"items": [{"next_action": "publish"}]}}
    assert find_oracle_leaks(packet) == ["$.safe.items[0].next_action"]
