"""Source-level mutation checks for critical dispatcher faults."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

import pilot.gate_dispatcher as production_dispatcher


SOURCE = Path(production_dispatcher.__file__).read_text()

MUTANTS = (
    (
        "invert_evidence_gate",
        'if not state.evidence_current:\n        return {"refresh_evidence"}',
        'if state.evidence_current:\n        return {"refresh_evidence"}',
    ),
    (
        "invert_license_gate",
        'if not state.license_verified:\n        return {"verify_license"}',
        'if state.license_verified:\n        return {"verify_license"}',
    ),
    (
        "invert_recommendation_gate",
        'if not state.recommendation_ready:\n        return {"form_recommendation"}',
        'if state.recommendation_ready:\n        return {"form_recommendation"}',
    ),
    (
        "allow_action_after_publication",
        'if state.published:\n        return set()',
        'if state.published:\n        return {"publish"}',
    ),
    (
        "allow_duplicate_approval_request",
        '    return set()\n\n\ndef allowed_actions',
        '    return {"request_publication_approval"}\n\n\ndef allowed_actions',
    ),
    (
        "refresh_does_not_advance_revision",
        'evidence_current=True, revision=state.revision + 1',
        'evidence_current=True, revision=state.revision',
    ),
    (
        "license_does_not_advance_revision",
        'license_verified=True, revision=state.revision + 1',
        'license_verified=True, revision=state.revision',
    ),
    (
        "recommendation_does_not_advance_revision",
        'recommendation_ready=True, revision=state.revision + 1',
        'recommendation_ready=True, revision=state.revision',
    ),
    (
        "approval_request_binds_previous_revision",
        'approval_request_revision=state.revision,\n            approval_grant_revision=None,',
        'approval_request_revision=state.revision - 1,\n            approval_grant_revision=None,',
    ),
    (
        "grant_requires_wrong_status",
        '    if not (\n        state.approval_status == "pending"\n        and state.approval_request_revision == basis_revision\n        and state.revision == basis_revision\n    ):',
        '    if not (\n        state.approval_status == "granted"\n        and state.approval_request_revision == basis_revision\n        and state.revision == basis_revision\n    ):',
    ),
)


def load_module(source: str, path: Path, name: str) -> ModuleType:
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(name, None)
    return module


def assert_transition_contract(module: ModuleType) -> None:
    state = module.GateState()
    assert module.allowed_actions(state) == {"refresh_evidence"}

    unchanged, event = module.attempt_action(state, "publish")
    assert unchanged == state
    assert event["type"] == "action_rejected"
    unchanged, event = module.attempt_action(state, "unknown_action")
    assert unchanged == state
    assert event["reason"] == "unsupported_action"

    expected_revisions = (
        ("refresh_evidence", 1),
        ("verify_license", 2),
        ("form_recommendation", 3),
        ("request_publication_approval", 3),
    )
    for action, expected_revision in expected_revisions:
        assert module.allowed_actions(state) == {action}
        state, event = module.attempt_action(state, action)
        assert event["type"] == "action_accepted"
        assert state.revision == expected_revision

    assert module.allowed_actions(state) == set()
    unchanged, event = module.attempt_action(
        state, "request_publication_approval"
    )
    assert unchanged == state
    assert event["type"] == "action_rejected"

    unchanged, event = module.grant_approval(state, basis_revision=2)
    assert unchanged == state
    assert event["type"] == "approval_rejected"
    state, event = module.grant_approval(state, basis_revision=3)
    assert event["type"] == "approval_granted"
    assert module.allowed_actions(state) == {"publish"}
    state, event = module.attempt_action(state, "publish")
    assert event["type"] == "action_accepted"
    assert module.allowed_actions(state) == set()

    state, event = module.invalidate_evidence(state)
    assert event["type"] == "evidence_invalidated"
    assert state == module.GateState(revision=4)
    assert module.allowed_actions(state) == {"refresh_evidence"}


def test_production_source_satisfies_mutation_oracle(tmp_path: Path) -> None:
    module = load_module(SOURCE, tmp_path / "dispatcher_original.py", "dispatcher_original")
    assert_transition_contract(module)


@pytest.mark.parametrize("name,old,new", MUTANTS, ids=[item[0] for item in MUTANTS])
def test_critical_source_mutant_is_killed(
    name: str, old: str, new: str, tmp_path: Path
) -> None:
    assert SOURCE.count(old) == 1, f"mutation target drifted for {name}"
    mutated_source = SOURCE.replace(old, new, 1)
    module = load_module(
        mutated_source,
        tmp_path / f"dispatcher_{name}.py",
        f"dispatcher_{name}",
    )
    with pytest.raises(Exception):
        assert_transition_contract(module)
