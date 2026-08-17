from __future__ import annotations

from pathlib import Path

from imperaos.control_plane.operator_attestation import (
    build_operator_attestation,
    verify_operator_attestation,
)
from imperaos.control_plane.target_evidence import (
    REQUIRED_BLOCKED_CLAIMS,
    prepare_target_evidence_session,
)


def test_operator_attestation_hashes_display_name_and_accepts_boundaries(tmp_path: Path) -> None:
    session = prepare_target_evidence_session(
        profile="enterprise",
        mode="rehearsal",
        environment_label="local-enterprise-rehearsal",
        output_root=tmp_path,
    )

    attestation = build_operator_attestation(
        session=session,
        operator_display_name="Baki Operator",
        output_root=tmp_path,
    )

    assert attestation.version == "control-plane.operator-attestation/v1"
    assert attestation.operator_display_name_hash.startswith("sha256:")
    assert "Baki Operator" not in attestation.model_dump_json(by_alias=True)
    assert set(REQUIRED_BLOCKED_CLAIMS).issubset(set(attestation.accepted_boundaries))
    assert (tmp_path / "operator_attestation.json").exists()

    result = verify_operator_attestation(
        attestation,
        required_boundaries=REQUIRED_BLOCKED_CLAIMS,
    )
    assert result.status == "pass"
    assert result.blocking_reasons == []


def test_operator_attestation_blocks_missing_boundary(tmp_path: Path) -> None:
    session = prepare_target_evidence_session(
        profile="enterprise",
        mode="rehearsal",
        environment_label="local-enterprise-rehearsal",
        output_root=tmp_path,
    )
    attestation = build_operator_attestation(
        session=session,
        operator_display_name="Operator",
        output_root=tmp_path,
        accepted_boundaries=["public-desktop-installer"],
    )

    result = verify_operator_attestation(
        attestation,
        required_boundaries=REQUIRED_BLOCKED_CLAIMS,
    )

    assert result.status == "blocked"
    assert "MISSING_ACCEPTED_BOUNDARY:live-macos-computer-use" in result.blocking_reasons
