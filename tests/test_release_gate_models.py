from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from imperaos.release.gate_models import (
    GateArtifactRef,
    GateArtifactRequirement,
    GateCommandSpec,
    GateEvidenceLedger,
    GateRunResult,
    ReleaseGateTarget,
)


def test_release_gate_models_are_hash_only_and_alias_safe() -> None:
    target = ReleaseGateTarget(
        targetId="mainline-rc",
        profile="enterprise",
        mode="rc-focused",
        platform="windows",
        outputRoot="artifacts/release-gates/mainline-rc",
    )
    requirement = GateArtifactRequirement(
        requirementId="control-plane-gate-result",
        gateId="control-plane-gate",
        path="artifacts/release-gates/mainline-rc/control-plane-gate/gate_result.json",
        kind="json",
    )
    artifact = GateArtifactRef(
        path=requirement.path,
        sha256="0" * 64,
        sizeBytes=12,
        kind="json",
        scanStatus="pass",
    )
    result = GateRunResult(
        gateId="control-plane-gate",
        status="pass",
        startedAtUtc=datetime.now(UTC),
        finishedAtUtc=datetime.now(UTC),
        durationMs=1,
        artifactRefs=[artifact],
    )
    ledger = GateEvidenceLedger(
        repoHeadSha="1" * 40,
        branch="codex/test",
        target=target,
        gateResults=[result],
        requiredGateIds=["control-plane-gate"],
        status="ready",
        artifactRoot="artifacts/release-gates/mainline-rc",
    )

    payload = ledger.model_dump(mode="json", by_alias=True)

    assert payload["schemaVersion"] == "release.gate-evidence-ledger/v1"
    assert payload["target"]["targetId"] == "mainline-rc"
    assert payload["gateResults"][0]["artifactRefs"][0]["contentPersisted"] is False
    assert payload["gateResults"][0]["artifactRefs"][0]["sha256"] == "0" * 64


def test_gate_command_spec_rejects_shell_string_and_destructive_flags() -> None:
    with pytest.raises(ValidationError):
        GateCommandSpec(
            commandId="bad",
            label="bad",
            argv="uv run pytest",  # type: ignore[arg-type]
            destructive=False,
        )

    with pytest.raises(ValidationError):
        GateCommandSpec(
            commandId="push",
            label="push",
            argv=["git", "push"],
            destructive=True,
        )
