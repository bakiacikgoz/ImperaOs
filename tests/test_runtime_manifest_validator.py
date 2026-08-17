from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "apps/operator-panel/scripts/validate_runtime_manifest.py"


def _windows_manifest(**overrides: str) -> dict[str, str]:
    values = {
        "platform": "windows",
        "arch": "x86_64",
        "python": "python/Scripts/python.exe",
        "imperaos_version": "0.4.1",
        "created_at_utc": "2026-07-13T12:00:00Z",
        "source_wheel": "imperaos-0.4.1-py3-none-any.whl",
        "source_wheel_sha256": "a" * 64,
        "python_exe_sha256": "b" * 64,
        "uv_lock_sha256": "c" * 64,
        "git_sha": "d" * 40,
    }
    values.update(overrides)
    return values


def _macos_manifest(**overrides: str) -> dict[str, str]:
    values = {
        "platform": "macos",
        "arch": "arm64",
        "python": "Python 3.11.9",
        "imperaos_version": "0.4.1",
        "wheel_sha256": "a" * 64,
        "git_head": "d" * 40,
        "built_at_utc": "2026-07-13T12:00:00Z",
    }
    values.update(overrides)
    return values


def _write_manifest(
    path: Path,
    values: dict[str, str],
    *,
    extra_lines: list[str] | None = None,
) -> None:
    lines = [
        *(f"{key}={value}" for key, value in values.items()),
        *(extra_lines or []),
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_validator(
    manifest: Path,
    *,
    platform: str,
    arch: str,
    runtime_version: str = "0.4.1",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "--manifest",
            str(manifest),
            "--platform",
            platform,
            "--arch",
            arch,
            "--runtime-version",
            runtime_version,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    ("platform", "arch", "values"),
    [
        ("windows", "x86_64", _windows_manifest()),
        ("macos", "arm64", _macos_manifest()),
    ],
)
def test_validator_accepts_exact_platform_manifest(
    tmp_path: Path,
    platform: str,
    arch: str,
    values: dict[str, str],
) -> None:
    manifest = tmp_path / "RUNTIME_MANIFEST.txt"
    _write_manifest(manifest, values)

    result = _run_validator(manifest, platform=platform, arch=arch)

    assert result.returncode == 0, result.stderr
    assert "manifest=pass" in result.stdout


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("duplicate", "duplicate manifest key"),
        ("former", "unexpected manifest key"),
        ("missing", "missing manifest key"),
        ("blank", "blank manifest value"),
    ],
)
def test_validator_rejects_non_exact_key_contract(
    tmp_path: Path,
    mutation: str,
    expected_error: str,
) -> None:
    manifest = tmp_path / "RUNTIME_MANIFEST.txt"
    values = _windows_manifest()
    extra_lines: list[str] = []
    if mutation == "duplicate":
        extra_lines.append("imperaos_version=0.4.1")
    elif mutation == "former":
        former_key = "bin" + "liquid_version"
        values[former_key] = "0.4.1"
    elif mutation == "missing":
        values.pop("imperaos_version")
    elif mutation == "blank":
        values["imperaos_version"] = ""
    _write_manifest(manifest, values, extra_lines=extra_lines)

    result = _run_validator(manifest, platform="windows", arch="x86_64")

    assert result.returncode != 0
    assert expected_error in result.stderr


@pytest.mark.parametrize(
    ("platform", "arch", "runtime_version", "overrides", "expected_error"),
    [
        ("windows", "x86_64", "0.4.2", {}, "version mismatch"),
        ("windows", "x86_64", "0.4.1", {"platform": "macos"}, "platform mismatch"),
        ("windows", "x86_64", "0.4.1", {"arch": "arm64"}, "arch mismatch"),
    ],
)
def test_validator_rejects_runtime_identity_mismatch(
    tmp_path: Path,
    platform: str,
    arch: str,
    runtime_version: str,
    overrides: dict[str, str],
    expected_error: str,
) -> None:
    manifest = tmp_path / "RUNTIME_MANIFEST.txt"
    _write_manifest(manifest, _windows_manifest(**overrides))

    result = _run_validator(
        manifest,
        platform=platform,
        arch=arch,
        runtime_version=runtime_version,
    )

    assert result.returncode != 0
    assert expected_error in result.stderr


def test_platform_verifiers_invoke_portable_validator_with_actual_version() -> None:
    windows_source = (
        ROOT / "apps/operator-panel/scripts/verify_bundled_runtime_windows.ps1"
    ).read_text(encoding="utf-8")
    macos_source = (
        ROOT / "apps/operator-panel/scripts/verify_bundled_runtime_macos.sh"
    ).read_text(encoding="utf-8")

    assert "validate_runtime_manifest.py" in windows_source
    assert '"--runtime-version"' in windows_source
    assert "$ActualVersion" in windows_source
    assert "validate_runtime_manifest.py" in macos_source
    assert '"--runtime-version" "${RUNTIME_VERSION}"' in macos_source
