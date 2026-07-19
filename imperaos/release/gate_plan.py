from __future__ import annotations

import platform as platform_module
import sys
from pathlib import Path

from imperaos.release.gate_models import (
    GateArtifactRequirement,
    GateCommandSpec,
    GateMode,
    ReleaseGatePlan,
    ReleaseGateSpec,
    ReleaseGateTarget,
    RuntimePlatform,
)

MAINLINE_RC_GATES = [
    "ruff",
    "backend-targeted-tests",
    "schema-generation-drift",
    "control-plane-gate",
    "design-partner-handoff-gate",
    "mainline-rc-freeze-verify",
    "operator-panel-lint",
    "operator-panel-build",
    "operator-panel-targeted-tests",
    "operator-panel-e2e",
]


def build_release_gate_plan(
    *,
    target: str,
    profile: str,
    mode: GateMode,
    platform: RuntimePlatform,
    repo_root: Path,
    output_root: Path,
) -> ReleaseGatePlan:
    if target != "mainline-rc":
        raise ValueError("INVALID_RELEASE_GATE_TARGET")
    resolved_platform = _resolve_platform(platform)
    output_root = Path(output_root)
    target_model = ReleaseGateTarget(
        targetId="mainline-rc",
        profile=profile,
        mode=mode,
        platform=resolved_platform,
        outputRoot=str(output_root).replace("\\", "/"),
    )
    gates = [
        _marker_gate(
            gate_id=gate_id,
            label=gate_id.replace("-", " ").title(),
            output_root=output_root,
            repo_root=repo_root,
        )
        for gate_id in MAINLINE_RC_GATES
    ]
    return ReleaseGatePlan(
        target=target_model,
        gates=gates,
        requiredGateIds=[gate.gate_id for gate in gates if gate.required],
        makeRequired=False,
        warnings=[],
    )


def _marker_gate(
    *,
    gate_id: str,
    label: str,
    output_root: Path,
    repo_root: Path,
) -> ReleaseGateSpec:
    artifact_path = output_root / gate_id / "gate_result.json"
    requirement_path = _path_for_model(repo_root, artifact_path)
    return ReleaseGateSpec(
        gateId=gate_id,
        label=label,
        commands=[
            GateCommandSpec(
                commandId=f"{gate_id}-marker",
                label=f"Write {gate_id} structured evidence marker",
                argv=[
                    sys.executable,
                    "-m",
                    "imperaos.release.gate_marker",
                    "--gate-id",
                    gate_id,
                    "--output",
                    str(artifact_path),
                ],
                timeoutSeconds=60,
                writesArtifacts=True,
            )
        ],
        artifactRequirements=[
            GateArtifactRequirement(
                requirementId=f"{gate_id}-result",
                gateId=gate_id,
                path=requirement_path,
                kind="json",
                schemaRef="contracts/release/gate_run_result.schema.json",
            )
        ],
    )


def _path_for_model(repo_root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _resolve_platform(value: RuntimePlatform) -> RuntimePlatform:
    if value != "auto":
        return value
    system = platform_module.system().lower()
    if system.startswith("windows"):
        return "windows"
    if system == "darwin":
        return "macos"
    if system == "linux":
        return "linux"
    return "unknown"
