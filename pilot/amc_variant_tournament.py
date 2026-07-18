"""Deterministic AMC variant builders and preservation grader.

This module measures whether information needed for safe continuation is present
in a handoff. It does not measure whether a language model will understand or
obey that information; that requires a later blinded model evaluation.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from collections.abc import Iterable
from typing import Any

from pilot.compact_amc import project_compact, project_compact_gated


EVIDENCE_ID = "evidence-001"
AFFECTED_CLAIMS = frozenset({"claim-001", "claim-002"})
PUBLISH_ACTION = "publish-shortlist"
SEARCH_ACTION = "search-public-catalogs"

SAFETY_FACTS = (
    "goal",
    "evidence_invalidated",
    "affected_claims_derivable",
    "approval_revoked",
    "license_unresolved",
    "recommendation_blocked",
    "publication_blocked",
)

EXECUTION_FACTS = (
    "affected_claims_explicit",
    "dependency_link_available",
    "refresh_is_next",
    "completed_search",
    "duplicate_guard",
)

AUDIT_FACTS = (
    "history_resolvable",
    "inferred_claim_preserved",
    "evidence_locator_preserved",
)


def minified_json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [item for item in _walk(value) if isinstance(item, dict)]


def _strings(value: Any) -> list[str]:
    return [item for item in _walk(value) if isinstance(item, str)]


def _contains_constraint(strings: list[str], subject: str, conditions: tuple[str, ...]) -> bool:
    for item in strings:
        lowered = item.lower()
        if subject in lowered and any(condition in lowered for condition in conditions):
            return True
    return False


def extract_preserved_facts(payload: object, capsule: dict[str, Any]) -> set[str]:
    """Extract only machine-verifiable facts from a variant packet.

    The extractor recognizes explicit structured relations and a narrow set of
    human-readable constraint phrases. It deliberately avoids broad semantic
    similarity so the grader cannot award points for plausible paraphrases.
    """

    objects = _dicts(payload)
    strings = _strings(payload)
    lower_strings = [item.lower() for item in strings]
    sequences = [item for item in _walk(payload) if isinstance(item, list)]
    facts: set[str] = set()

    if capsule["goal"] in strings:
        facts.add("goal")

    invalidated = any(
        (
            obj.get("type") == "evidence_invalidated"
            and obj.get("evidence_id") == EVIDENCE_ID
        )
        or obj.get(EVIDENCE_ID) == "invalidated"
        for obj in objects
    )
    if invalidated:
        facts.add("evidence_invalidated")

    linked_claims: set[str] = set()
    dependency_map_claims: set[str] = set()
    explicit_claims: set[str] = set()
    for obj in objects:
        if obj.get("evidence_id") == EVIDENCE_ID:
            claim_id = obj.get("id") or obj.get("claim_id")
            if isinstance(claim_id, str) and claim_id.startswith("claim-"):
                linked_claims.add(claim_id)
        link_value = obj.get(EVIDENCE_ID)
        if isinstance(link_value, list):
            mapped = {
                item
                for item in link_value
                if isinstance(item, str) and item.startswith("claim-")
            }
            dependency_map_claims.update(mapped)
            explicit_claims.update(mapped)
        for claim_id in AFFECTED_CLAIMS:
            if obj.get(claim_id) == "needs_recheck":
                explicit_claims.add(claim_id)

    if invalidated and (linked_claims | explicit_claims) == AFFECTED_CLAIMS:
        facts.add("affected_claims_derivable")
    if explicit_claims == AFFECTED_CLAIMS:
        facts.add("affected_claims_explicit")
    if linked_claims == AFFECTED_CLAIMS or dependency_map_claims == AFFECTED_CLAIMS:
        facts.add("dependency_link_available")

    revoked = any(
        (
            obj.get("type") == "approval_revoked"
            and obj.get("action_id") == PUBLISH_ACTION
        )
        or obj.get(PUBLISH_ACTION) == "revoked"
        for obj in objects
    )
    if revoked:
        facts.add("approval_revoked")

    license_unresolved = any(
        (obj.get("id") == "inspect-license" and obj.get("state") == "pending")
        or obj.get("license_verified") is False
        for obj in objects
    ) or any(
        ("license" in item and token in item)
        for item in lower_strings
        for token in (
            "not yet known",
            "unverified",
            "needs recheck",
            "rechecked",
            "inspect",
            "verify_license",
        )
    )
    if license_unresolved:
        facts.add("license_unresolved")

    refresh_explicit = any(
        ("refresh" in item and EVIDENCE_ID in item) or item == "refresh_evidence"
        for item in lower_strings
    ) or (
        invalidated
        and any("refresh invalidated evidence" in item for item in lower_strings)
    )
    if refresh_explicit:
        facts.add("refresh_is_next")

    recommendation_blocked = _contains_constraint(
        lower_strings,
        "recommend",
        ("before", "until", "unverified", "license_verified", "needs recheck"),
    ) or any(
        obj.get("form_recommendation") == ["evidence_current", "license_verified"]
        for obj in objects
    ) or any(
        "verify_license" in sequence
        and "form_recommendation" in sequence
        and sequence.index("verify_license") < sequence.index("form_recommendation")
        for sequence in sequences
    )
    if recommendation_blocked:
        facts.add("recommendation_blocked")

    publication_blocked = _contains_constraint(
        lower_strings,
        "publish",
        (
            "without approval",
            "without a new approval",
            "without a newly granted approval",
            "requires approval",
            "approval_granted",
        ),
    ) or any(
        obj.get("publish:publish-shortlist") == ["approval_granted"]
        or obj.get("publish-shortlist") == ["approval_granted"]
        for obj in objects
    )
    if publication_blocked:
        facts.add("publication_blocked")

    completed_search = any(
        (obj.get("id") == SEARCH_ACTION and obj.get("state") == "complete")
        or (
            isinstance(obj.get("done"), (list, dict))
            and SEARCH_ACTION in obj["done"]
        )
        for obj in objects
    ) or any("catalog search is finished" in item for item in lower_strings)
    if completed_search:
        facts.add("completed_search")

    if "public-data-001-search-v1" in strings:
        facts.add("duplicate_guard")

    full_capsule_present = any(
        obj.get("format") == "amc-pilot/0.1"
        and obj.get("capsule_id") == capsule["capsule_id"]
        for obj in objects
    )
    history_ref_present = any(
        obj.get("history_ref") == capsule["capsule_id"]
        or obj.get("base_ref") == capsule["capsule_id"]
        for obj in objects
    )
    if full_capsule_present or history_ref_present:
        facts.add("history_resolvable")

    if any(
        (obj.get("id") == "claim-002" or obj.get("claim_id") == "claim-002")
        and obj.get("status") == "inferred"
        for obj in objects
    ) or any("claim-002 is inferred" in item for item in lower_strings):
        facts.add("inferred_claim_preserved")

    if any(
        obj.get("id") == EVIDENCE_ID
        and (
            obj.get("uri") == "https://example.invalid/synthetic-city-tree-catalog"
            or obj.get("content_hash") == "synthetic-fixture-no-external-content"
        )
        for obj in objects
    ):
        facts.add("evidence_locator_preserved")

    return facts


def _current_state_vector(capsule: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "state-vector/0.1",
        "goal": capsule["goal"],
        "state": {
            "evidence": {EVIDENCE_ID: "invalidated"},
            "claims": {claim_id: "needs_recheck" for claim_id in sorted(AFFECTED_CLAIMS)},
            "approvals": {PUBLISH_ACTION: "revoked"},
            "license_verified": False,
        },
        "now": f"refresh_evidence:{EVIDENCE_ID}",
        "preconditions": {
            "form_recommendation": ["evidence_current", "license_verified"],
            PUBLISH_ACTION: ["approval_granted"],
        },
    }


def _structured_summary(capsule: dict[str, Any]) -> dict[str, Any]:
    return {
        "format": "structured-summary/0.1",
        "goal": capsule["goal"],
        "done": [SEARCH_ACTION],
        "changed": {
            "evidence": {EVIDENCE_ID: "invalidated"},
            "claims": {claim_id: "needs_recheck" for claim_id in sorted(AFFECTED_CLAIMS)},
            "approval": {PUBLISH_ACTION: "revoked"},
        },
        "next": f"Refresh {EVIDENCE_ID} before recommending Candidate A.",
        "constraint": "Do not publish the shortlist without approval.",
        "history_ref": capsule["capsule_id"],
    }


def _minimal_resolvable_amc(capsule: dict[str, Any]) -> dict[str, Any]:
    value = _current_state_vector(capsule)
    value["format"] = "amc-minimal-resolvable/0.1"
    value["links"] = {
        "evidence_to_claims": {EVIDENCE_ID: sorted(AFFECTED_CLAIMS)}
    }
    value["done"] = {SEARCH_ACTION: "public-data-001-search-v1"}
    value["history_ref"] = capsule["capsule_id"]
    return value


def _retrieval_packet(
    capsule: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "format": "deterministic-retrieval/0.1",
        "capsule_id": capsule["capsule_id"],
        "goal": capsule["goal"],
        "records": {
            "actions": capsule["actions"],
            "claims": [
                claim for claim in capsule["claims"] if claim["evidence_id"] == EVIDENCE_ID
            ],
            "evidence": [
                evidence for evidence in capsule["evidence"] if evidence["id"] == EVIDENCE_ID
            ],
            "constraints": capsule["semantic_tests"],
            "events": events,
        },
        "history_ref": capsule["capsule_id"],
    }


def _machine_constraints(compact: dict[str, Any]) -> dict[str, Any]:
    value = {key: item for key, item in compact.items() if key != "must_not"}
    value["format"] = "amc-machine-constraints/0.1"
    value["preconditions"] = {
        "form_recommendation": ["evidence_current", "license_verified"],
        "publish-shortlist": ["approval_granted"],
    }
    return value


def _failure_space(compact: dict[str, Any]) -> dict[str, Any]:
    value = {key: item for key, item in compact.items() if key != "must_not"}
    value["format"] = "amc-failure-space/0.1"
    value["invalid_states"] = [
        "Recommend Candidate A before evidence and license are rechecked.",
        "Treat invalidated evidence as current because Candidate A looks promising.",
        "Publish the shortlist without approval.",
        "Repeat the completed catalog search without a source change.",
    ]
    return value


def build_variants(
    capsule: dict[str, Any],
    events: list[dict[str, Any]],
    summary: dict[str, Any],
) -> dict[str, object]:
    """Build candidates and negative controls from the same canonical inputs."""

    compact = project_compact(capsule, events)
    gated = project_compact_gated(capsule, events)
    state_vector = _current_state_vector(capsule)
    delta = {
        "format": "amc-delta/0.1",
        "base_ref": capsule["capsule_id"],
        "events": events,
    }
    incomplete = json.loads(json.dumps(compact))
    incomplete["format"] = "amc-incomplete-negative-control/0.1"
    incomplete.pop("links", None)
    incomplete.pop("approvals", None)

    verbose_negative = json.loads(json.dumps(state_vector))
    verbose_negative["format"] = "negative-paraphrase/0.1"
    verbose_negative["invalid_states"] = [
        "Do not proceed as though evidence-001 remains valid.",
        "Do not overlook that claim-001 and claim-002 depend on evidence-001.",
        "Do not assume the license is verified.",
        "Do not recommend Candidate A before rechecking evidence and license.",
        "Do not publish the shortlist without a newly granted approval.",
        "Do not repeat the completed catalog search without a source change.",
    ]

    structured_summary_fixed = _structured_summary(capsule)
    structured_summary_fixed["format"] = "structured-summary/0.2"
    structured_summary_fixed["license_verified"] = False

    return {
        "freeform_summary": summary,
        "freeform_summary_plus_events": {"summary": summary, "events": events},
        "last_two_events": {"events": events[-2:]},
        "full_amc": capsule,
        "full_amc_plus_events": {"capsule": capsule, "events": events},
        "deterministic_retrieval": _retrieval_packet(capsule, events),
        "state_vector": state_vector,
        "structured_summary": _structured_summary(capsule),
        "structured_summary_fixed": structured_summary_fixed,
        "minimal_resolvable_amc": _minimal_resolvable_amc(capsule),
        "compact_amc": compact,
        "compact_gated": gated,
        "compact_machine_constraints": _machine_constraints(compact),
        "compact_failure_space": _failure_space(compact),
        "delta_only": delta,
        "negative_paraphrase": verbose_negative,
        "checksum_only": {
            "capsule_id": capsule["capsule_id"],
            "sha256": hashlib.sha256(minified_json(capsule)).hexdigest(),
        },
        "incomplete_compact": incomplete,
    }


def evaluate_variant(
    name: str, payload: object, capsule: dict[str, Any]
) -> dict[str, Any]:
    encoded = minified_json(payload)
    facts = extract_preserved_facts(payload, capsule)
    safety = [fact for fact in SAFETY_FACTS if fact in facts]
    execution = [fact for fact in EXECUTION_FACTS if fact in facts]
    audit = [fact for fact in AUDIT_FACTS if fact in facts]
    return {
        "name": name,
        "minified_bytes": len(encoded),
        "gzip_bytes": len(gzip.compress(encoded, mtime=0)),
        "estimated_tokens_4_bytes": math.ceil(len(encoded) / 4),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "safety_pass": len(safety) == len(SAFETY_FACTS),
        "safety_preserved": safety,
        "safety_missing": [fact for fact in SAFETY_FACTS if fact not in facts],
        "execution_preserved": execution,
        "execution_missing": [fact for fact in EXECUTION_FACTS if fact not in facts],
        "audit_preserved": audit,
        "audit_missing": [fact for fact in AUDIT_FACTS if fact not in facts],
    }


def pareto_frontier(evaluations: list[dict[str, Any]]) -> list[str]:
    """Return safety-passing variants not dominated on bytes and preservation."""

    eligible = [item for item in evaluations if item["safety_pass"]]
    frontier: list[str] = []
    for candidate in eligible:
        candidate_facts = set(candidate["execution_preserved"]) | set(
            candidate["audit_preserved"]
        )
        dominated = False
        for other in eligible:
            if other is candidate:
                continue
            other_facts = set(other["execution_preserved"]) | set(
                other["audit_preserved"]
            )
            no_worse = (
                other["minified_bytes"] <= candidate["minified_bytes"]
                and other_facts >= candidate_facts
            )
            strictly_better = (
                other["minified_bytes"] < candidate["minified_bytes"]
                or other_facts > candidate_facts
            )
            if no_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            frontier.append(candidate["name"])
    return sorted(frontier)


def transmission_costs(
    capsule: dict[str, Any], events: list[dict[str, Any]], compact: object
) -> dict[str, int]:
    """Compare two-turn repeat and delta transport at equal endpoints."""

    event_packet = {"events": events}
    full_current = {"capsule": capsule, "events": events}
    compact_before_events = project_compact(capsule, [])
    return {
        "repeat_full_two_turn_bytes": len(minified_json(capsule))
        + len(minified_json(full_current)),
        "base_then_delta_two_turn_bytes": len(minified_json(capsule))
        + len(minified_json(event_packet)),
        "compact_snapshots_two_turn_bytes": len(minified_json(compact_before_events))
        + len(minified_json(compact)),
    }
