from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = ROOT / "apps/operator-panel/src-tauri/resources"
FORMER_RUNTIME = "bin" + "liquid-runtime"
FORMER_MODULE = "-m " + "bin" + "liquid"

ACTIVE_CONSUMERS = (
    ROOT / ".gitignore",
    ROOT / "apps/operator-panel/src-tauri/tauri.conf.json",
    ROOT / "apps/operator-panel/src-tauri/src/bridge.rs",
    ROOT / "apps/operator-panel/scripts/build_bundled_runtime_windows.ps1",
    ROOT / "apps/operator-panel/scripts/build_bundled_runtime_macos.sh",
    ROOT / "apps/operator-panel/scripts/verify_bundled_runtime_macos.sh",
    ROOT / "apps/operator-panel/scripts/windows_installer_smoke.ps1",
    ROOT / ".github/workflows/windows-ci.yml",
    ROOT / ".github/workflows/operator-panel-runtime-matrix.yml",
    ROOT / ".github/workflows/operator-panel-release-windows.yml",
    ROOT / ".github/workflows/operator-panel-release-macos.yml",
    ROOT / ".github/workflows/operator-panel-internal-unsigned-build.yml",
    ROOT / "apps/operator-panel/README.md",
    ROOT / "docs/MACOS_M4_LOCAL_TRIAL_RUNBOOK.md",
    ROOT / "docs/RELEASE_CHECKLIST.md",
)


def test_only_canonical_runtime_resource_directory_exists() -> None:
    canonical = RESOURCE_ROOT / "imperaos-runtime"
    assert canonical.is_dir()
    assert (canonical / "README.txt").is_file()
    assert not (RESOURCE_ROOT / FORMER_RUNTIME).exists()


def test_active_consumers_use_only_canonical_runtime_identity() -> None:
    violations: list[str] = []
    for path in ACTIVE_CONSUMERS:
        source = path.read_text(encoding="utf-8")
        if FORMER_RUNTIME in source or FORMER_MODULE in source:
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_runtime_build_identity_is_exact() -> None:
    windows = (
        ROOT / "apps/operator-panel/scripts/build_bundled_runtime_windows.ps1"
    ).read_text(encoding="utf-8")
    macos = (ROOT / "apps/operator-panel/scripts/build_bundled_runtime_macos.sh").read_text(
        encoding="utf-8"
    )
    for source in (windows, macos):
        assert "imperaos-*.whl" in source
        assert "-m imperaos" in source
        assert "imperaos_version" in source
        assert "ImperaOS Operator Panel" in source


def test_windows_runtime_manifest_is_written_as_utf8_without_bom() -> None:
    source = (
        ROOT / "apps/operator-panel/scripts/build_bundled_runtime_windows.ps1"
    ).read_text(encoding="utf-8")
    assert "New-Object System.Text.UTF8Encoding($false)" in source
    assert "[System.IO.File]::WriteAllLines" in source


def test_tauri_smoke_bootstrap_is_windows_and_unicode_safe() -> None:
    source = (ROOT / "apps/operator-panel/scripts/tauri-launched-smoke.ts").read_text(
        encoding="utf-8"
    )
    assert "import { fileURLToPath } from 'node:url';" in source
    assert "path.dirname(fileURLToPath(import.meta.url))" in source
    assert "new URL(import.meta.url).pathname" not in source
