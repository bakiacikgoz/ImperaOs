from __future__ import annotations

from pathlib import Path

import pytest

from imperaos.release.gate_plan import build_release_gate_plan


def test_mainline_rc_windows_plan_has_no_make_and_required_gate_artifacts(tmp_path: Path) -> None:
    plan = build_release_gate_plan(
        target="mainline-rc",
        profile="enterprise",
        mode="rc-focused",
        platform="windows",
        repo_root=tmp_path,
        output_root=Path("artifacts/release-gates/mainline-rc"),
    )

    gate_ids = [gate.gate_id for gate in plan.gates]
    argv_heads = [command.argv[0] for gate in plan.gates for command in gate.commands]

    assert plan.target.platform == "windows"
    assert "make" not in argv_heads
    assert "control-plane-gate" in gate_ids
    assert "design-partner-handoff-gate" in gate_ids
    assert {
        requirement.requirement_id
        for gate in plan.gates
        for requirement in gate.artifact_requirements
    } >= {"control-plane-gate-result", "design-partner-handoff-gate-result"}


def test_plan_rejects_unknown_target(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="INVALID_RELEASE_GATE_TARGET"):
        build_release_gate_plan(
            target="unknown",
            profile="enterprise",
            mode="rc-focused",
            platform="windows",
            repo_root=tmp_path,
            output_root=Path("artifacts/release-gates/mainline-rc"),
        )
