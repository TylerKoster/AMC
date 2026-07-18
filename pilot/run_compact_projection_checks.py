"""Deterministic checks for the software-generated compact AMC."""

from __future__ import annotations

import json
from pathlib import Path

from compact_amc import project_compact, project_compact_gated


def encoded_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def main() -> None:
    root = Path(__file__).resolve().parent
    capsule = json.loads((root / "fixtures" / "public_dataset_research_001_capsule.json").read_text())
    case = json.loads((root / "live_eval" / "evals" / "id_only_dependency_case_v2.json").read_text())
    compact = project_compact(capsule, case["events"])
    gated = project_compact_gated(capsule, case["events"])
    checks = {
        "compact view is smaller than full capsule": encoded_size(compact) < encoded_size(capsule),
        "invalidated evidence remains explicit": compact["changed"]["evidence"] == {"evidence-001": "invalidated"},
        "evidence-to-claim links remain exact": compact["links"]["evidence_to_claims"]
        == {"evidence-001": ["claim-001", "claim-002"]},
        "revoked approval remains explicit": compact["approvals"] == {"publish-shortlist": "revoked"},
        "full history remains resolvable": compact["history_ref"] == capsule["capsule_id"],
        "gated view remains smaller than full capsule": encoded_size(gated) < encoded_size(capsule),
        "gated view permits only evidence refresh now": gated["workflow"]["now"]
        == ["refresh_evidence:evidence-001"],
        "approval request has explicit prerequisites": gated["workflow"]["gates"]
        ["request_publication_approval:publish-shortlist"]
        == ["evidence_current", "license_verified", "recommendation_ready"],
        "publication still requires approval": gated["workflow"]["gates"]
        ["publish:publish-shortlist"]
        == ["approval_granted"],
    }
    for label, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'}: {label}")
    if not all(checks.values()):
        raise SystemExit(1)
    print(
        f"\nResult: PASS (full={encoded_size(capsule)}B "
        f"compact={encoded_size(compact)}B gated={encoded_size(gated)}B)"
    )


if __name__ == "__main__":
    main()
