from __future__ import annotations

from pathlib import Path

from imperaos.cli import _team_init_template
from imperaos.contracts.version import OPERATOR_PANEL_CONTRACT_VERSION
from scripts.run_managed_kms_adapter_drill import SCHEMA_VERSION as KMS_DRILL_SCHEMA_VERSION
from scripts.run_operator_validation_drill import (
    ATTESTATION_SCHEMA_VERSION,
)
from scripts.run_operator_validation_drill import (
    SCHEMA_VERSION as OPERATOR_DRILL_SCHEMA_VERSION,
)


def test_active_serialized_contract_identities_are_imperaos_v2_only() -> None:
    assert ATTESTATION_SCHEMA_VERSION == "imperaos-non-developer-operator-attestation/v2"
    assert OPERATOR_DRILL_SCHEMA_VERSION == "imperaos-operator-validation-drill/v2"
    assert KMS_DRILL_SCHEMA_VERSION == "imperaos-managed-kms-adapter-drill/v2"

    former_prefix = "bin" + "liquid-"
    assert all(
        not value.startswith(former_prefix)
        for value in (
            ATTESTATION_SCHEMA_VERSION,
            OPERATOR_DRILL_SCHEMA_VERSION,
            KMS_DRILL_SCHEMA_VERSION,
        )
    )


def test_default_team_and_operator_contract_identifiers_are_canonical() -> None:
    assert OPERATOR_PANEL_CONTRACT_VERSION == "3.0"
    assert 'team_id: "imperaos-team"' in _team_init_template("balanced")
    assert 'team_id: "imperaos-regulated-team"' in _team_init_template("restricted")


def test_runtime_manifest_scripts_use_only_imperaos_version_field() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    paths = (
        repo_root / "apps/operator-panel/scripts/build_bundled_runtime_macos.sh",
        repo_root / "apps/operator-panel/scripts/verify_bundled_runtime_macos.sh",
        repo_root / "apps/operator-panel/scripts/build_bundled_runtime_windows.ps1",
        repo_root / "apps/operator-panel/scripts/verify_bundled_runtime_windows.ps1",
        repo_root / "scripts/evaluate_windows_release_gate.py",
        repo_root / "scripts/run_macos_local_trial_gate.py",
    )
    former_field = "bin" + "liquid_version"
    for path in paths:
        source = path.read_text(encoding="utf-8")
        assert "imperaos_version" in source, path
        assert former_field not in source, path


def test_platform_verifiers_delegate_after_reading_actual_runtime_version() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    windows_source = (
        repo_root / "apps/operator-panel/scripts/verify_bundled_runtime_windows.ps1"
    ).read_text(encoding="utf-8")
    macos_source = (
        repo_root / "apps/operator-panel/scripts/verify_bundled_runtime_macos.sh"
    ).read_text(encoding="utf-8")

    assert windows_source.index("$ActualVersion =") < windows_source.index(
        "& $RuntimePython $ManifestValidator"
    )
    assert macos_source.index('RUNTIME_VERSION="$(') < macos_source.index(
        '"${RUNTIME_PYTHON}" "${MANIFEST_VALIDATOR}"'
    )
