from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.models import TargetEvidenceBundle
from imperaos.control_plane.target_evidence import (
    REQUIRED_BLOCKED_CLAIMS,
    collect_target_evidence_rehearsal,
    prepare_target_evidence_session,
    verify_target_evidence_bundle,
)


def test_collect_rehearsal_writes_hash_only_bundle(tmp_path: Path) -> None:
    session = prepare_target_evidence_session(
        profile="enterprise",
        mode="rehearsal",
        environment_label="local-enterprise-rehearsal",
        output_root=tmp_path / "target",
    )

    bundle = collect_target_evidence_rehearsal(
        session=session,
        output_root=tmp_path / "target",
        state_root=tmp_path / "state",
        evidence_root=tmp_path / "artifacts",
    )

    assert bundle.status in {"pass", "conditional"}
    assert bundle.secret_material_written is False
    assert bundle.raw_prompt_persisted is False
    assert bundle.raw_response_persisted is False
    assert bundle.raw_screenshot_persisted is False
    assert bundle.claim_boundary.public_desktop_installer == "blocked"
    assert bundle.claim_boundary.live_macos_computer_use == "blocked"
    assert set(REQUIRED_BLOCKED_CLAIMS).issubset(set(bundle.claim_boundary.blocked_claims))
    assert all(item.sha256.startswith("sha256:") for item in bundle.items)
    assert (tmp_path / "target" / "target_evidence_bundle.json").exists()

    verification = verify_target_evidence_bundle(
        tmp_path / "target" / "target_evidence_bundle.json"
    )
    assert verification.status == "pass"
    assert verification.blocking_reasons == []


def test_verify_bundle_blocks_raw_or_opened_claim_boundary() -> None:
    bundle = TargetEvidenceBundle(
        sessionId="target-evidence-test",
        status="pass",
        rawPromptPersisted=True,
        claimBoundary={
            "publicDesktopInstaller": "allowed",
            "liveMacosComputerUse": "blocked",
            "liveWindowsComputerUse": "blocked",
            "liveLinuxComputerUse": "blocked",
            "blockedClaims": [
                "live-macos-computer-use",
                "live-windows-computer-use",
                "live-linux-computer-use",
            ],
        },
    )

    result = verify_target_evidence_bundle(bundle)

    assert result.status == "blocked"
    assert "RAW_PROMPT_PERSISTED" in result.blocking_reasons
    assert "PUBLIC_DESKTOP_INSTALLER_BOUNDARY_OPEN" in result.blocking_reasons
