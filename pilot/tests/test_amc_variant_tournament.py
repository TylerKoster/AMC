from __future__ import annotations

import json
from pathlib import Path

from pilot.amc_variant_tournament import (
    SAFETY_FACTS,
    build_variants,
    evaluate_variant,
    extract_preserved_facts,
    minified_json,
    pareto_frontier,
    transmission_costs,
)
from pilot.compact_amc import project_compact


ROOT = Path(__file__).resolve().parents[1]


def load_inputs() -> tuple[dict, list[dict], dict]:
    capsule = json.loads(
        (ROOT / "fixtures" / "public_dataset_research_001_capsule.json").read_text()
    )
    case = json.loads(
        (ROOT / "live_eval" / "evals" / "id_only_dependency_case_v2.json").read_text()
    )
    summary = json.loads(
        (ROOT / "fixtures" / "public_dataset_research_001_summary.json").read_text()
    )
    return capsule, case["events"], summary


def test_compact_projector_uses_normal_next_action_without_invalidation() -> None:
    capsule, _, _ = load_inputs()
    compact = project_compact(capsule, [])
    assert compact["next"] == capsule["intention"]["next_action"]


def test_all_variants_are_deterministic_and_json_serializable() -> None:
    capsule, events, summary = load_inputs()
    first = build_variants(capsule, events, summary)
    second = build_variants(capsule, events, summary)
    assert set(first) == set(second)
    assert len(first) == 18
    assert {name: minified_json(value) for name, value in first.items()} == {
        name: minified_json(value) for name, value in second.items()
    }


def test_compact_and_state_vector_pass_safety_contract() -> None:
    capsule, events, summary = load_inputs()
    variants = build_variants(capsule, events, summary)
    for name in ("compact_amc", "compact_gated", "compact_machine_constraints", "state_vector"):
        facts = extract_preserved_facts(variants[name], capsule)
        assert set(SAFETY_FACTS) <= facts, name


def test_dependency_edge_is_distinct_from_changed_claim_statuses() -> None:
    capsule, events, summary = load_inputs()
    variants = build_variants(capsule, events, summary)
    compact_facts = extract_preserved_facts(variants["compact_amc"], capsule)
    state_facts = extract_preserved_facts(variants["state_vector"], capsule)
    assert "dependency_link_available" in compact_facts
    assert "dependency_link_available" not in state_facts


def test_targeted_mutations_repair_known_gaps() -> None:
    capsule, events, summary = load_inputs()
    variants = build_variants(capsule, events, summary)
    original = evaluate_variant(
        "structured_summary", variants["structured_summary"], capsule
    )
    repaired = evaluate_variant(
        "structured_summary_fixed", variants["structured_summary_fixed"], capsule
    )
    minimal = evaluate_variant(
        "minimal_resolvable_amc", variants["minimal_resolvable_amc"], capsule
    )
    assert original["safety_pass"] is False
    assert repaired["safety_pass"] is True
    assert minimal["safety_pass"] is True
    assert "dependency_link_available" in minimal["execution_preserved"]
    assert "duplicate_guard" in minimal["execution_preserved"]


def test_full_amc_plus_events_contains_state_but_not_projected_next_action() -> None:
    capsule, events, summary = load_inputs()
    payload = build_variants(capsule, events, summary)["full_amc_plus_events"]
    result = evaluate_variant("full_amc_plus_events", payload, capsule)
    assert result["safety_pass"] is True
    assert "refresh_is_next" in result["execution_missing"]


def test_negative_controls_fail_safety_contract() -> None:
    capsule, events, summary = load_inputs()
    variants = build_variants(capsule, events, summary)
    for name in ("checksum_only", "last_two_events", "incomplete_compact"):
        assert evaluate_variant(name, variants[name], capsule)["safety_pass"] is False


def test_delta_only_requires_base_resolution() -> None:
    capsule, events, summary = load_inputs()
    delta = build_variants(capsule, events, summary)["delta_only"]
    result = evaluate_variant("delta_only", delta, capsule)
    assert result["safety_pass"] is False
    assert "history_resolvable" in result["audit_preserved"]
    assert "goal" in result["safety_missing"]
    assert "affected_claims_derivable" in result["safety_missing"]


def test_two_turn_delta_transport_is_smaller_than_full_repeat() -> None:
    capsule, events, summary = load_inputs()
    compact = build_variants(capsule, events, summary)["compact_amc"]
    costs = transmission_costs(capsule, events, compact)
    assert costs["base_then_delta_two_turn_bytes"] < costs["repeat_full_two_turn_bytes"]
    assert costs["compact_snapshots_two_turn_bytes"] < costs["repeat_full_two_turn_bytes"]


def test_pareto_frontier_contains_only_safety_passing_variants() -> None:
    capsule, events, summary = load_inputs()
    evaluations = [
        evaluate_variant(name, payload, capsule)
        for name, payload in build_variants(capsule, events, summary).items()
    ]
    frontier = set(pareto_frontier(evaluations))
    passing = {item["name"] for item in evaluations if item["safety_pass"]}
    assert frontier
    assert frontier <= passing
