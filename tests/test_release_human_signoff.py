from __future__ import annotations

import json
from pathlib import Path

from imperaos.release_decision.signoff import (
    build_signoff_template,
    verify_human_signoffs,
)


def test_signoff_missing_role_blocks_approval(tmp_path: Path) -> None:
    report = verify_human_signoffs(
        dossier_hash="a" * 64,
        signoff_root=tmp_path,
        required_roles=["release_owner", "security_operator"],
    )

    assert report.status == "missing"
    assert "security_operator" in report.missing_roles


def test_signoff_stale_dossier_hash_blocks(tmp_path: Path) -> None:
    signoff = build_signoff_template(dossier_hash="a" * 64, role="release_owner")
    payload = signoff.model_dump(mode="json", by_alias=True)
    payload["operatorDisplayNameHash"] = "b" * 64
    payload["dossierSha256"] = "c" * 64
    payload["signedAtUtc"] = "2026-06-15T10:00:00Z"
    (tmp_path / "release_owner.json").write_text(json.dumps(payload), encoding="utf-8")

    report = verify_human_signoffs(
        dossier_hash="a" * 64,
        signoff_root=tmp_path,
        required_roles=["release_owner"],
    )

    assert report.status == "blocked"
    assert "STALE_DOSSIER_HASH" in report.blocking_reasons


def test_signoff_template_is_not_treated_as_real_approval(tmp_path: Path) -> None:
    template = build_signoff_template(dossier_hash="a" * 64, role="release_owner")
    (tmp_path / "release_owner.template.json").write_text(
        json.dumps(template.model_dump(mode="json", by_alias=True)),
        encoding="utf-8",
    )

    report = verify_human_signoffs(
        dossier_hash="a" * 64,
        signoff_root=tmp_path,
        required_roles=["release_owner"],
    )

    assert report.status == "missing"
    assert report.verified_roles == []
