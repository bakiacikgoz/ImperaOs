from __future__ import annotations

import json
from pathlib import Path

from imperaos.control_plane.target_evidence import (
    REQUIRED_BLOCKED_CLAIMS,
    prepare_target_evidence_session,
)


def test_prepare_target_evidence_session_writes_hash_safe_manifest(tmp_path: Path) -> None:
    session = prepare_target_evidence_session(
        profile="enterprise",
        mode="rehearsal",
        environment_label="local-enterprise-rehearsal",
        output_root=tmp_path,
        operator_id="qa-operator@example.test",
    )

    assert session.version == "control-plane.target-evidence-session/v1"
    assert session.session_id.startswith("target-evidence-")
    assert session.raw_persistence is False
    assert set(REQUIRED_BLOCKED_CLAIMS).issubset(set(session.blocked_claims))
    assert "public-desktop-installer" not in session.allowed_claims
    assert session.operator_id_hash is not None
    assert "qa-operator" not in session.model_dump_json(by_alias=True)

    payload = json.loads((tmp_path / "session.json").read_text(encoding="utf-8"))
    assert payload["rawPersistence"] is False
    assert payload["operatorIdHash"].startswith("sha256:")
    assert "qa-operator" not in json.dumps(payload)


def test_prepare_target_evidence_session_is_idempotent(tmp_path: Path) -> None:
    first = prepare_target_evidence_session(
        profile="enterprise",
        mode="rehearsal",
        environment_label="local-enterprise-rehearsal",
        output_root=tmp_path,
    )
    second = prepare_target_evidence_session(
        profile="enterprise",
        mode="rehearsal",
        environment_label="local-enterprise-rehearsal",
        output_root=tmp_path,
    )

    assert second.session_id == first.session_id
    assert (tmp_path / "session.json").exists()
