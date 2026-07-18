from __future__ import annotations

import json
from pathlib import Path

from pilot.live_eval.regrade_round_b import regrade_report


RAW_PATH = (
    Path(__file__).resolve().parents[1]
    / "live_eval"
    / "results"
    / "round_b_smoke_latest.json"
)


def test_regrade_preserves_raw_decisions_and_corrects_ambiguous_oracle() -> None:
    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    original_decisions = {
        run["key"]: run.get("decision") for run in raw["runs"]
    }
    report = regrade_report(raw)
    regraded_decisions = {
        run["key"]: run.get("decision") for run in report["runs"]
    }
    assert original_decisions == regraded_decisions
    assert report["api_calls_in_regrade"] == 0
    for summary in report["summaries"]:
        assert summary["core_passes"] == 10
        assert summary["correct_actions"] == 10
        assert summary["exact_impact_identifier_passes"] == 2
        assert summary["exact_impact_identifier_trials"] == 2


def test_structured_summary_is_only_non_dominated_candidate() -> None:
    raw = json.loads(RAW_PATH.read_text(encoding="utf-8"))
    report = regrade_report(raw)
    dominated = report["dominated_candidates"]
    assert "structured_summary_fixed" not in dominated
    assert set(dominated) == {
        "state_vector",
        "minimal_resolvable_amc",
        "deterministic_retrieval",
    }
    assert "structured_summary_fixed" in dominated["state_vector"]
