"""Deterministic safety checks for the first AMC pilot fixture.

This is deliberately not an LLM evaluator. It establishes that the packet has
the fields needed for a later clean-context model comparison.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CAPSULE_PATH = ROOT / "fixtures" / "public_dataset_research_001_capsule.json"
SUMMARY_PATH = ROOT / "fixtures" / "public_dataset_research_001_summary.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check(condition: bool, label: str, failures: list[str]) -> None:
    if condition:
        print(f"PASS: {label}")
    else:
        print(f"FAIL: {label}")
        failures.append(label)


def main() -> int:
    capsule = load_json(CAPSULE_PATH)
    summary = load_json(SUMMARY_PATH)
    failures: list[str] = []

    required_top_level = {
        "format", "capsule_id", "goal", "intention", "actions", "claims",
        "evidence", "semantic_tests", "human_projection",
    }
    check(required_top_level.issubset(capsule), "all required capsule sections exist", failures)

    intention = capsule.get("intention", {})
    check(
        {"status", "next_action", "approval_required", "expected_output"}.issubset(intention),
        "intention names status, next action, approval state, and expected output",
        failures,
    )

    evidence_ids = {item.get("id") for item in capsule.get("evidence", [])}
    claims = capsule.get("claims", [])
    check(all(item.get("status") in {"observed", "inferred"} for item in claims),
          "every claim says whether it was observed or inferred", failures)
    check(all(item.get("evidence_id") in evidence_ids for item in claims),
          "every claim points to recorded evidence", failures)

    actions = capsule.get("actions", [])
    check(all(item.get("idempotency_key") for item in actions),
          "every action has a duplicate-action guard", failures)
    approval_actions = [item for item in actions if item.get("state") == "approval_required"]
    check(all(item.get("authorization") == "not_granted" for item in approval_actions),
          "approval-required actions are not marked authorized", failures)

    tests = capsule.get("semantic_tests", {})
    check(all(tests.get(key) for key in ("required_answers", "required_actions", "forbidden_actions")),
          "the preservation contract names required and forbidden behavior", failures)

    check(len(capsule["human_projection"].split()) <= 80,
          "human handoff is short enough for rapid inspection", failures)
    check(len(summary["summary"].split()) < len(capsule["human_projection"].split()),
          "baseline summary is intentionally less explicit than the capsule", failures)

    print(f"\nResult: {'PASS' if not failures else 'FAIL'}")
    if failures:
        print("Failed checks:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("This confirms packet completeness only. It does not measure model resumption quality.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
