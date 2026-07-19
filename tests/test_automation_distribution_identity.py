from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_PATHS = (
    ROOT / "Makefile",
    ROOT / "apps/operator-panel/scripts/build_bundled_runtime_macos.sh",
    ROOT / "apps/operator-panel/scripts/build_bundled_runtime_windows.ps1",
    ROOT / "apps/operator-panel/scripts/verify_bundled_runtime_macos.sh",
    ROOT / "apps/operator-panel/scripts/verify_bundled_runtime_windows.ps1",
    ROOT / "apps/operator-panel/scripts/windows_installer_smoke.ps1",
    *sorted((ROOT / ".github" / "workflows").glob("*.yml")),
    *sorted((ROOT / ".github" / "workflows").glob("*.yaml")),
)
FORMER_DISTRIBUTION = "bin" + "liquid"
REMOVED_AUTOMATION_REFERENCES = {
    "console CLI": re.compile(
        rf"\buv\s+run\s+{re.escape(FORMER_DISTRIBUTION)}(?=\s|$)"
    ),
    "Python module": re.compile(
        rf"\s-m\s+{re.escape(FORMER_DISTRIBUTION)}(?=\s|$)"
    ),
    "compile target": re.compile(
        rf"\bcompileall\s+{re.escape(FORMER_DISTRIBUTION)}(?=\s|$)"
    ),
    "package directory": re.compile(
        rf"(?<![.\w-]){re.escape(FORMER_DISTRIBUTION)}/"
    ),
    "wheel distribution": re.compile(
        rf"\b{re.escape(FORMER_DISTRIBUTION)}-[^\s\"']*\.whl\b",
        re.IGNORECASE,
    ),
    "wheel branding": re.compile(
        rf"\b{re.escape(FORMER_DISTRIBUTION)}\s+wheel\b", re.IGNORECASE
    ),
    "distribution artifact": re.compile(
        rf"\b{re.escape(FORMER_DISTRIBUTION)}-version\.txt\b", re.IGNORECASE
    ),
}


def test_active_automation_uses_imperaos_distribution_identity() -> None:
    violations: list[str] = []

    for path in AUTOMATION_PATHS:
        source = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(source.splitlines(), start=1):
            for reference_kind, pattern in REMOVED_AUTOMATION_REFERENCES.items():
                if pattern.search(line):
                    relative_path = path.relative_to(ROOT).as_posix()
                    violations.append(
                        f"{relative_path}:{line_number}: {reference_kind}: {line.strip()}"
                    )

    assert violations == [], "removed distribution automation references:\n" + "\n".join(
        violations
    )
