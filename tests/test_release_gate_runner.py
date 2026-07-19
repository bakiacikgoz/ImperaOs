from __future__ import annotations

import sys
from pathlib import Path

from imperaos.release.gate_models import GateArtifactRequirement, GateCommandSpec, ReleaseGateSpec
from imperaos.release.gate_runner import run_release_gate


def test_runner_collects_hash_only_artifact(tmp_path: Path) -> None:
    artifact_path = "artifacts/release-gates/mainline-rc/unit/gate_result.json"
    gate = ReleaseGateSpec(
        gateId="unit",
        commands=[
            GateCommandSpec(
                commandId="write-artifact",
                label="Write artifact",
                argv=[
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        f"p=Path(r'{artifact_path}'); "
                        "p.parent.mkdir(parents=True, exist_ok=True); "
                        "p.write_text('{\"status\":\"pass\"}\\n', encoding='utf-8')"
                    ),
                ],
                timeoutSeconds=30,
            )
        ],
        artifactRequirements=[
            GateArtifactRequirement(
                requirementId="unit-result",
                gateId="unit",
                path=artifact_path,
                kind="json",
            )
        ],
    )

    result = run_release_gate(gate=gate, repo_root=tmp_path, output_root=tmp_path / "artifacts")

    assert result.status == "pass"
    assert result.artifact_refs[0].content_persisted is False
    assert result.artifact_refs[0].sha256
    assert result.secret_scan_status == "pass"
    assert result.raw_marker_scan_status == "pass"


def test_runner_blocks_unsafe_command_without_execution(tmp_path: Path) -> None:
    gate = ReleaseGateSpec(
        gateId="unsafe",
        commands=[
            GateCommandSpec(
                commandId="unsafe-push",
                label="Unsafe push",
                argv=["git", "push"],
                timeoutSeconds=30,
            )
        ],
    )

    result = run_release_gate(gate=gate, repo_root=tmp_path, output_root=tmp_path / "artifacts")

    assert result.status == "blocked"
    assert "UNSAFE_GATE_COMMAND" in result.blocking_reasons
