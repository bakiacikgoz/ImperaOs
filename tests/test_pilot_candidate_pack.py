from __future__ import annotations

import json
from pathlib import Path

from imperaos.control_plane.operator_attestation import build_operator_attestation
from imperaos.control_plane.pilot_candidate_pack import (
    generate_design_partner_pilot_candidate_pack,
)
from imperaos.control_plane.target_evidence import (
    collect_target_evidence_rehearsal,
    prepare_target_evidence_session,
)


def test_pilot_candidate_pack_is_conditional_without_overclaim(tmp_path: Path) -> None:
    rc_root = tmp_path / "rc"
    rc_root.mkdir()
    (rc_root / "design-partner-rc-status.json").write_text(
        json.dumps(
            {
                "schemaVersion": "control-plane.design-partner-rc/v1",
                "status": "conditional",
                "blockers": [],
                "warnings": ["enterprise-hat-a"],
            }
        ),
        encoding="utf-8",
    )
    (rc_root / "claim-guard-matrix.json").write_text('{"claims":[]}\n', encoding="utf-8")
    proof = rc_root / "provider-runtime" / "workflow-proof" / "read_only_ops_triage.json"
    proof.parent.mkdir(parents=True)
    proof.write_text('{"status":"pass","executedMutations":0}\n', encoding="utf-8")

    target_root = tmp_path / "target"
    session = prepare_target_evidence_session(
        profile="enterprise",
        mode="rehearsal",
        environment_label="local-enterprise-rehearsal",
        output_root=target_root,
    )
    collect_target_evidence_rehearsal(
        session=session,
        output_root=target_root,
        state_root=tmp_path / "state",
        evidence_root=tmp_path / "artifacts",
    )
    build_operator_attestation(
        session=session,
        operator_display_name="Operator",
        output_root=target_root,
    )

    manifest = generate_design_partner_pilot_candidate_pack(
        profile="enterprise",
        rc_root=rc_root,
        target_evidence_root=target_root,
        output_root=tmp_path / "pilot",
    )

    assert manifest.version == "control-plane.pilot-candidate/v1"
    assert manifest.status in {"pass", "conditional"}
    assert "UNSUPPORTED_LIVE_COMPUTER_USE_CLAIM" not in manifest.blocking_reasons
    assert manifest.target_evidence_path.endswith("target_evidence_bundle.json")
    assert (tmp_path / "pilot" / "manifest.json").exists()
    assert (tmp_path / "pilot" / "PILOT_CANDIDATE_SUMMARY.md").exists()


def test_pilot_candidate_pack_blocks_target_evidence_blocker(tmp_path: Path) -> None:
    rc_root = tmp_path / "rc"
    rc_root.mkdir()
    (rc_root / "design-partner-rc-status.json").write_text(
        '{"schemaVersion":"control-plane.design-partner-rc/v1","status":"conditional","blockers":[],"warnings":[]}\n',
        encoding="utf-8",
    )
    target_root = tmp_path / "target"
    target_root.mkdir()
    (target_root / "target_evidence_bundle.json").write_text(
        json.dumps(
            {
                "version": "control-plane.target-evidence-bundle/v1",
                "sessionId": "target-evidence-test",
                "status": "blocked",
                "blockingReasons": ["RAW_RESPONSE_PERSISTED"],
                "claimBoundary": {
                    "publicDesktopInstaller": "blocked",
                    "liveMacosComputerUse": "blocked",
                    "liveWindowsComputerUse": "blocked",
                    "liveLinuxComputerUse": "blocked",
                    "blockedClaims": [
                        "public-desktop-installer",
                        "live-macos-computer-use",
                        "live-windows-computer-use",
                        "live-linux-computer-use",
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    manifest = generate_design_partner_pilot_candidate_pack(
        profile="enterprise",
        rc_root=rc_root,
        target_evidence_root=target_root,
        output_root=tmp_path / "pilot",
    )

    assert manifest.status == "blocked"
    assert "RAW_RESPONSE_PERSISTED" in manifest.blocking_reasons
