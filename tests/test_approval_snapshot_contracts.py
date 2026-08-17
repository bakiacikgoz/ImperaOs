from __future__ import annotations

import pytest

from imperaos.governance.approval_snapshots import (
    ControlPlaneActionSnapshot,
    compute_approval_request_hash,
    parse_approval_snapshot,
)


def _control_plane_payload() -> dict[str, object]:
    return {
        "schema_version": "approval.snapshot/v2",
        "kind": "control_plane_action",
        "run_id": "run-1",
        "agent_id": "agent-1",
        "action_id": "action-1",
        "proposal_ref": "proposals/run-1/action-1.json",
        "proposal_hash": "a" * 64,
        "policy_hash": "b" * 64,
        "input_hash": "c" * 64,
        "runtime_version": "0.4.1",
    }


def test_parse_strict_control_plane_snapshot_and_hash_deterministically() -> None:
    parsed = parse_approval_snapshot(_control_plane_payload())
    assert isinstance(parsed, ControlPlaneActionSnapshot)
    assert compute_approval_request_hash(parsed) == compute_approval_request_hash(
        dict(reversed(list(_control_plane_payload().items())))
    )


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "approval.snapshot/v1"},
        {"kind": "unknown"},
        {"unexpected": True},
    ],
)
def test_parse_rejects_unsupported_or_extra_snapshot_fields(change: dict[str, object]) -> None:
    payload = {**_control_plane_payload(), **change}
    with pytest.raises(ValueError, match="APPROVAL_SNAPSHOT_SCHEMA_UNSUPPORTED|validation"):
        parse_approval_snapshot(payload)
