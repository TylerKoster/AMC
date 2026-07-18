"""Local event-to-AMC trigger drill; no model or network calls."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def project(events: list[dict], as_of: datetime) -> dict:
    goal = None
    actions: dict[str, dict] = {}
    evidence: dict[str, dict] = {}
    claims: dict[str, dict] = {}
    approvals: set[str] = set()
    revoked: set[str] = set()

    for event in events:
        event_type = event["type"]
        if event_type == "goal_set":
            goal = event["goal"]
        elif event_type == "action_registered":
            actions[event["action_id"]] = dict(event)
        elif event_type == "evidence_recorded":
            evidence[event["evidence_id"]] = dict(event)
        elif event_type == "claim_recorded":
            claims[event["claim_id"]] = dict(event)
        elif event_type == "approval_granted":
            approvals.add(event["action_id"])
        elif event_type == "approval_revoked":
            revoked.add(event["action_id"])

    stale_claims = []
    for claim in claims.values():
        source = evidence[claim["evidence_id"]]
        if parse_time(source["expires_at"]) <= as_of:
            stale_claims.append(claim["claim_id"])

    publish = actions["publish-shortlist"]
    publish_state = "blocked" if publish["action_id"] in revoked else publish["state"]
    return {
        "goal": goal,
        "stale_claims": stale_claims,
        "next_action": "inspect-license" if stale_claims else None,
        "publish_state": publish_state,
        "publish_allowed": publish["action_id"] in approvals and publish["action_id"] not in revoked,
    }


def main() -> None:
    fixture = Path(__file__).parent / "fixtures" / "public_dataset_research_001_events.json"
    source = json.loads(fixture.read_text())
    result = project(source["events"], parse_time(source["as_of"]))
    checks = {
        "goal remains available": result["goal"] is not None,
        "expired evidence invalidates dependent claim": result["stale_claims"] == ["candidate-a-reusable"],
        "stale evidence creates recheck action": result["next_action"] == "inspect-license",
        "revoked approval blocks publish": result["publish_state"] == "blocked",
        "publish is not allowed after revocation": result["publish_allowed"] is False,
    }
    for label, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {label}")
    if not all(checks.values()):
        raise SystemExit(1)
    print("\nResult: PASS")


if __name__ == "__main__":
    main()
