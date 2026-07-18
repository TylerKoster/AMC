"""Independent reference model for the AMC gate dispatcher contract."""

from __future__ import annotations

from dataclasses import dataclass, replace


ACTIONS = (
    "refresh_evidence",
    "verify_license",
    "form_recommendation",
    "request_publication_approval",
    "publish",
)


@dataclass(frozen=True)
class OracleState:
    evidence_current: bool = False
    license_verified: bool = False
    recommendation_ready: bool = False
    revision: int = 0
    approval_status: str = "revoked"
    approval_request_revision: int | None = None
    approval_grant_revision: int | None = None
    published: bool = False


def allowed(state: OracleState) -> set[str]:
    """Apply the ordered phase table from the written transition contract."""
    phase_table = (
        (not state.evidence_current, "refresh_evidence"),
        (not state.license_verified, "verify_license"),
        (not state.recommendation_ready, "form_recommendation"),
        (
            state.approval_status == "granted"
            and state.approval_grant_revision == state.revision,
            "publish",
        ),
        (
            not (
                state.approval_status == "pending"
                and state.approval_request_revision == state.revision
            ),
            "request_publication_approval",
        ),
    )
    if state.published:
        return set()
    for predicate, action in phase_table:
        if predicate:
            return {action}
    return set()


def attempt(state: OracleState, action: str) -> tuple[OracleState, str]:
    if action not in allowed(state):
        return state, "action_rejected"
    transitions = {
        "refresh_evidence": lambda value: replace(
            value, evidence_current=True, revision=value.revision + 1
        ),
        "verify_license": lambda value: replace(
            value, license_verified=True, revision=value.revision + 1
        ),
        "form_recommendation": lambda value: replace(
            value, recommendation_ready=True, revision=value.revision + 1
        ),
        "request_publication_approval": lambda value: replace(
            value,
            approval_status="pending",
            approval_request_revision=value.revision,
            approval_grant_revision=None,
        ),
        "publish": lambda value: replace(value, published=True),
    }
    return transitions[action](state), "action_accepted"


def grant(state: OracleState, basis_revision: int) -> tuple[OracleState, str]:
    matching_request = (
        state.approval_status == "pending"
        and state.approval_request_revision == basis_revision
        and state.revision == basis_revision
    )
    if not matching_request:
        return state, "approval_rejected"
    return (
        replace(
            state,
            approval_status="granted",
            approval_grant_revision=basis_revision,
        ),
        "approval_granted",
    )


def invalidate(state: OracleState) -> tuple[OracleState, str]:
    return (
        replace(
            state,
            evidence_current=False,
            license_verified=False,
            recommendation_ready=False,
            revision=state.revision + 1,
            approval_status="revoked",
            approval_request_revision=None,
            approval_grant_revision=None,
            published=False,
        ),
        "evidence_invalidated",
    )
