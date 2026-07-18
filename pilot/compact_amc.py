"""Deterministic full-AMC to compact-current-view projection.

The compact form is software-generated. It is not a new secret language: field
names remain readable and every changed state keeps an identifier that can be
resolved against the full event record.
"""

from __future__ import annotations

from typing import Any


def project_compact(capsule: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    invalidated_evidence = {
        event["evidence_id"]
        for event in events
        if event["type"] == "evidence_invalidated"
    }
    revoked_actions = {
        event["action_id"]
        for event in events
        if event["type"] == "approval_revoked"
    }
    affected_claims = [
        claim["id"]
        for claim in capsule["claims"]
        if claim["evidence_id"] in invalidated_evidence
    ]
    evidence_to_claims = {
        evidence_id: sorted(
            claim["id"]
            for claim in capsule["claims"]
            if claim["evidence_id"] == evidence_id
        )
        for evidence_id in sorted(invalidated_evidence)
    }
    completed_actions = [
        action["id"] for action in capsule["actions"] if action["state"] == "complete"
    ]

    return {
        "format": "amc-compact/0.1",
        "capsule_id": capsule["capsule_id"],
        "goal": capsule["goal"],
        "status": "needs_recheck" if affected_claims else capsule["intention"]["status"],
        "next": (
            "Refresh invalidated evidence, recheck dependent claims, then inspect the "
            "license and update cadence."
            if affected_claims
            else capsule["intention"]["next_action"]
        ),
        "changed": {
            "evidence": {item: "invalidated" for item in sorted(invalidated_evidence)},
            "claims": {item: "needs_recheck" for item in sorted(affected_claims)},
        },
        "approvals": {item: "revoked" for item in sorted(revoked_actions)},
        "links": {"evidence_to_claims": evidence_to_claims},
        "done": completed_actions,
        "must_not": [
            "Recommend Candidate A until evidence and license are rechecked.",
            "Publish the shortlist without a new approval.",
        ],
        "history_ref": capsule["capsule_id"],
    }


def project_compact_gated(
    capsule: dict[str, Any], events: list[dict[str, Any]]
) -> dict[str, Any]:
    """Project the current view plus a compact, human-readable gate sequence."""
    view = project_compact(capsule, events)
    view["format"] = "amc-compact-gated/0.2"
    view.pop("next", None)
    view.pop("must_not", None)
    invalidated = sorted(view["changed"]["evidence"])
    first_evidence = invalidated[0] if invalidated else "evidence"
    view["workflow"] = {
        "now": [f"refresh_evidence:{first_evidence}"],
        "then": [
            "verify_license",
            "form_recommendation",
            "request_publication_approval:publish-shortlist",
            "publish:publish-shortlist",
        ],
        "gates": {
            "request_publication_approval:publish-shortlist": [
                "evidence_current",
                "license_verified",
                "recommendation_ready",
            ],
            "publish:publish-shortlist": ["approval_granted"],
        },
    }
    return view
