"""Deterministic checks for downstream gate enforcement."""

from __future__ import annotations

from gate_dispatcher import GateState, allowed_actions, attempt_action, grant_approval, invalidate_evidence


def main() -> None:
    state = GateState()
    checks: dict[str, bool] = {}

    unchanged, event = attempt_action(state, "request_publication_approval")
    checks["premature approval request is rejected"] = (
        unchanged == state and event["type"] == "action_rejected"
    )

    for action in ("refresh_evidence", "verify_license", "form_recommendation"):
        checks[f"{action} becomes executable in order"] = allowed_actions(state) == {action}
        state, event = attempt_action(state, action)
        checks[f"{action} is accepted"] = event["type"] == "action_accepted"

    state, event = attempt_action(state, "request_publication_approval")
    checks["approval request is allowed only after prerequisites"] = event["type"] == "action_accepted"
    checks["publication waits for approval event"] = allowed_actions(state) == set()

    unchanged, event = grant_approval(state, basis_revision=state.revision - 1)
    checks["approval for wrong revision is rejected"] = (
        unchanged == state and event["type"] == "approval_rejected"
    )

    state, event = grant_approval(state, basis_revision=state.revision)
    checks["approval bound to current revision is accepted"] = event["type"] == "approval_granted"
    checks["publication becomes executable after bound approval"] = allowed_actions(state) == {"publish"}

    state, event = invalidate_evidence(state)
    checks["new invalidation revokes prior approval"] = (
        state.approval_status == "revoked" and event["approval_effect"] == "revoked"
    )
    checks["new invalidation returns workflow to evidence refresh"] = allowed_actions(state) == {"refresh_evidence"}

    for label, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {label}")
    if not all(checks.values()):
        raise SystemExit(1)
    print("\nResult: PASS")


if __name__ == "__main__":
    main()
