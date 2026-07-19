from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_ROOT = ROOT / "apps" / "operator-panel" / "scripts"

MODULE_PATH_CONSUMERS = (
    "assert-boundary-violations.ts",
    "assert-fallow-policy.ts",
    "assert-pilot-launch-pages.ts",
    "assert-pilot-readiness.ts",
    "audit-ui-controls.ts",
    "collect-route-timings.ts",
    "run-fallow-analysis.ts",
    "write-frontend-qa-summary.ts",
)


def test_operator_panel_scripts_resolve_windows_unicode_paths_from_file_urls() -> None:
    findings: list[str] = []

    for name in MODULE_PATH_CONSUMERS:
        source = (SCRIPT_ROOT / name).read_text(encoding="utf-8")
        if "import { fileURLToPath } from 'node:url';" not in source:
            findings.append(f"{name}: missing fileURLToPath import")
        if "path.dirname(fileURLToPath(import.meta.url))" not in source:
            findings.append(f"{name}: unsafe script directory resolution")
        if "new URL(import.meta.url).pathname" in source:
            findings.append(f"{name}: URL pathname remains encoded")

    assert findings == []


def test_ui_control_audit_normalizes_relative_paths_for_cross_platform_coverage() -> None:
    source = (SCRIPT_ROOT / "audit-ui-controls.ts").read_text(encoding="utf-8")

    assert source.count(".split(path.sep).join('/')") >= 2
