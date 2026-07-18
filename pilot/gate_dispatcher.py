"""Deterministic execution gates that sit downstream of an AMC.

The model may propose an action, but this dispatcher decides whether the action
is executable. Approval is bound to a state revision so an old approval cannot
silently authorize work after evidence changes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


ACTIONS = frozenset(
    {
        "refresh_evidence",
        "verify_license",
        "form_recommendation",
        "request_publication_approval",
        "publish",
    }
)
APPROVAL_STATUSES = frozenset({"revoked", "pending", "granted"})


class InvalidGateState(ValueError):
    """Raised when a caller supplies an impossible or malformed gate state."""


@dataclass(frozen=True)
class GateState:
    evidence_current: bool = False
    license_verified: bool = False
    recommendation_ready: bool = False
    revision: int = 0
    approval_status: str = "revoked"
    approval_request_revision: int | None = None
    approval_grant_revision: int | None = None
    published: bool = False


def _is_nonnegative_int(value: object) -> bool:
    return type(value) is int and value >= 0


def validate_state(state: GateState) -> None:
    """Reject malformed or internally contradictory dispatcher state."""
    if not isinstance(state, GateState):
        raise TypeError("state must be a GateState")

    boolean_fields = (
        "evidence_current",
        "license_verified",
        "recommendation_ready",
        "published",
    )
    for field in boolean_fields:
        if type(getattr(state, field)) is not bool:
            raise InvalidGateState(f"{field} must be a boolean")
    if not _is_nonnegative_int(state.revision):
        raise InvalidGateState("revision must be a non-negative integer")
    if state.approval_status not in APPROVAL_STATUSES:
        raise InvalidGateState("approval_status is not recognized")

    for field in ("approval_request_revision", "approval_grant_revision"):
        value = getattr(state, field)
        if value is not None and not _is_nonnegative_int(value):
            raise InvalidGateState(f"{field} must be null or a non-negative integer")

    if state.license_verified and not state.evidence_current:
        raise InvalidGateState("verified license requires current evidence")
    if state.recommendation_ready and not state.license_verified:
        raise InvalidGateState("ready recommendation requires a verified license")

    if state.approval_status == "revoked":
        if (
            state.approval_request_revision is not None
            or state.approval_grant_revision is not None
        ):
            raise InvalidGateState("revoked approval cannot retain approval revisions")
    elif state.approval_status == "pending":
        if (
            state.approval_request_revision != state.revision
            or state.approval_grant_revision is not None
        ):
            raise InvalidGateState("pending approval must bind only its current request")
    elif (
        state.approval_request_revision != state.revision
        or state.approval_grant_revision != state.revision
    ):
        raise InvalidGateState("granted approval must bind to the current revision")

    if state.approval_status in {"pending", "granted"} and not state.recommendation_ready:
        raise InvalidGateState("approval requires a ready recommendation")
    if state.published and state.approval_status != "granted":
        raise InvalidGateState("publication requires current granted approval")


def _allowed_actions_validated(state: GateState) -> set[str]:
    if state.published:
        return set()
    if not state.evidence_current:
        return {"refresh_evidence"}
    if not state.license_verified:
        return {"verify_license"}
    if not state.recommendation_ready:
        return {"form_recommendation"}
    if (
        state.approval_status == "granted"
        and state.approval_grant_revision == state.revision
    ):
        return {"publish"}
    if not (
        state.approval_status == "pending"
        and state.approval_request_revision == state.revision
    ):
        return {"request_publication_approval"}
    return set()


def allowed_actions(state: GateState) -> set[str]:
    validate_state(state)
    return _allowed_actions_validated(state)


def attempt_action(state: GateState, action: str) -> tuple[GateState, dict[str, Any]]:
    validate_state(state)
    if not isinstance(action, str):
        raise TypeError("action must be a string")
    if not action:
        raise ValueError("action must not be empty")

    allowed = _allowed_actions_validated(state)
    if action not in allowed:
        return state, {
            "type": "action_rejected",
            "action": action,
            "revision": state.revision,
            "allowed": sorted(allowed),
            "reason": (
                "unsupported_action"
                if action not in ACTIONS
                else "prerequisite_or_approval_gate"
            ),
        }

    if action == "refresh_evidence":
        new_state = replace(state, evidence_current=True, revision=state.revision + 1)
    elif action == "verify_license":
        new_state = replace(state, license_verified=True, revision=state.revision + 1)
    elif action == "form_recommendation":
        new_state = replace(state, recommendation_ready=True, revision=state.revision + 1)
    elif action == "request_publication_approval":
        new_state = replace(
            state,
            approval_status="pending",
            approval_request_revision=state.revision,
            approval_grant_revision=None,
        )
    elif action == "publish":
        new_state = replace(state, published=True)
    else:  # unreachable because allowed_actions uses a closed vocabulary
        raise ValueError(f"Unsupported action: {action}")

    validate_state(new_state)
    return new_state, {
        "type": "action_accepted",
        "action": action,
        "revision": new_state.revision,
    }


def grant_approval(
    state: GateState, *, basis_revision: int
) -> tuple[GateState, dict[str, Any]]:
    validate_state(state)
    if not _is_nonnegative_int(basis_revision):
        raise ValueError("basis_revision must be a non-negative integer")
    if not (
        state.approval_status == "pending"
        and state.approval_request_revision == basis_revision
        and state.revision == basis_revision
    ):
        return state, {
            "type": "approval_rejected",
            "basis_revision": basis_revision,
            "current_revision": state.revision,
            "reason": "approval_not_bound_to_current_requested_revision",
        }
    new_state = replace(
        state,
        approval_status="granted",
        approval_grant_revision=basis_revision,
    )
    validate_state(new_state)
    return new_state, {
        "type": "approval_granted",
        "basis_revision": basis_revision,
    }


def invalidate_evidence(state: GateState) -> tuple[GateState, dict[str, Any]]:
    validate_state(state)
    new_state = replace(
        state,
        evidence_current=False,
        license_verified=False,
        recommendation_ready=False,
        revision=state.revision + 1,
        approval_status="revoked",
        approval_request_revision=None,
        approval_grant_revision=None,
        published=False,
    )
    validate_state(new_state)
    return new_state, {
        "type": "evidence_invalidated",
        "revision": new_state.revision,
        "approval_effect": "revoked",
    }
