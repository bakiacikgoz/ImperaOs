from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.pilot_ops_drill import run_pilot_ops_drill


def test_pilot_ops_drill_passes_with_safe_runner(tmp_path: Path) -> None:
    def runner(command: list[str], timeout: int) -> tuple[int, str, str]:
        return 0, f"ok:{command[0]}:{timeout}", ""

    report = run_pilot_ops_drill(
        profile="enterprise",
        output_root=tmp_path / "artifacts" / "design-partner-handoff",
        command_runner=runner,
    )

    assert report.status == "pass"
    assert report.metrics.passed_count == report.metrics.step_count
    assert report.metrics.step_count == 12
    assert {step.step_id for step in report.steps} >= {
        "governed-pilot-workflow-verify",
        "evidence-pack-verify",
        "handoff-pack-build-verify",
    }
    assert (
        tmp_path / "artifacts" / "design-partner-handoff" / "PILOT_OPS_DRILL_REPORT.json"
    ).exists()


def test_pilot_ops_drill_reports_conditional_steps(tmp_path: Path) -> None:
    def runner(command: list[str], timeout: int) -> tuple[int, str, str]:
        if "auth" in command:
            return 3, "identity unavailable", ""
        return 0, "ok", ""

    report = run_pilot_ops_drill(
        profile="enterprise",
        output_root=tmp_path / "artifacts" / "design-partner-handoff",
        command_runner=runner,
    )

    assert report.status == "conditional"
    assert any(reason.startswith("DRILL_STEP_CONDITIONAL") for reason in report.warnings)


def test_pilot_ops_drill_blocks_timeout(tmp_path: Path) -> None:
    def runner(command: list[str], timeout: int) -> tuple[int, str, str]:
        raise TimeoutError

    report = run_pilot_ops_drill(
        profile="enterprise",
        output_root=tmp_path / "artifacts" / "design-partner-handoff",
        command_runner=runner,
    )

    assert report.status == "blocked"
    assert any(reason.startswith("DRILL_STEP_TIMEOUT") for reason in report.blockers)
