"""Local benchmark comparing verified full replay with checkpoint-plus-tail replay."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from statistics import median
from time import perf_counter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))

from pilot.event_dispatcher import (  # noqa: E402
    CommandEnvelope,
    WorkflowEngine,
    build_replay_checkpoint,
    replay_events,
    replay_from_checkpoint,
)


WORKFLOW_ID = "snapshot-benchmark-001"
EVENT_COUNT = 1_000
CHECKPOINT_SEQUENCE = 900
REPETITIONS = 30


def canonical_bytes(value: object) -> int:
    return len(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    )


def build_stream() -> WorkflowEngine:
    engine = WorkflowEngine(WORKFLOW_ID)
    for cycle in range(EVENT_COUNT // 2):
        revision = engine.state.revision
        engine.process(
            CommandEnvelope(
                command_id=f"refresh-{cycle}",
                workflow_id=WORKFLOW_ID,
                expected_revision=revision,
                command_type="action",
                action="refresh_evidence",
            )
        )
        engine.process(
            CommandEnvelope(
                command_id=f"invalidate-{cycle}",
                workflow_id=WORKFLOW_ID,
                expected_revision=revision + 1,
                command_type="invalidate_evidence",
                authority_class="evidence_monitor",
            )
        )
    return engine


def timed(callable_value) -> float:
    start = perf_counter()
    callable_value()
    return perf_counter() - start


def main() -> None:
    engine = build_stream()
    events = engine.events
    checkpoint = build_replay_checkpoint(
        WORKFLOW_ID, events[:CHECKPOINT_SEQUENCE]
    )
    tail = events[CHECKPOINT_SEQUENCE:]

    full_state = replay_events(WORKFLOW_ID, events)
    checkpoint_state = replay_from_checkpoint(checkpoint, tail)
    if full_state != checkpoint_state or full_state != engine.state:
        raise SystemExit("Replay states differ")

    full_timings = [
        timed(lambda: replay_events(WORKFLOW_ID, events))
        for _ in range(REPETITIONS)
    ]
    checkpoint_timings = [
        timed(lambda: replay_from_checkpoint(checkpoint, tail))
        for _ in range(REPETITIONS)
    ]

    full_bytes = canonical_bytes([asdict(event) for event in events])
    checkpoint_bytes = canonical_bytes(asdict(checkpoint))
    tail_bytes = canonical_bytes([asdict(event) for event in tail])
    full_median = median(full_timings)
    checkpoint_median = median(checkpoint_timings)
    report = {
        "run_type": "local_snapshot_replay_benchmark",
        "event_count": len(events),
        "checkpoint_sequence": checkpoint.sequence_number,
        "tail_event_count": len(tail),
        "repetitions": REPETITIONS,
        "full_replay_median_ms": round(full_median * 1_000, 3),
        "checkpoint_tail_replay_median_ms": round(
            checkpoint_median * 1_000, 3
        ),
        "observed_speed_ratio": round(
            full_median / checkpoint_median, 3
        ),
        "full_event_stream_bytes": full_bytes,
        "checkpoint_bytes": checkpoint_bytes,
        "tail_event_bytes": tail_bytes,
        "checkpoint_plus_tail_working_bytes": checkpoint_bytes + tail_bytes,
        "working_byte_reduction_percent": round(
            (1 - (checkpoint_bytes + tail_bytes) / full_bytes) * 100,
            3,
        ),
        "canonical_full_log_still_required": True,
        "final_revision": engine.state.revision,
        "states_equal": True,
    }
    output = Path(__file__).resolve().parent / "results" / "snapshot_replay_latest.json"
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
