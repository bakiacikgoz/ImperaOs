from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / ".github/workflows"
INTERNAL_UNSIGNED = WORKFLOW_ROOT / "operator-panel-internal-unsigned-build.yml"
CLEAN_SMOKE = WORKFLOW_ROOT / "operator-panel-windows-clean-smoke.yml"
WINDOWS_SMOKE = ROOT / "apps/operator-panel/scripts/windows_installer_smoke.ps1"
MACOS_CODESIGN = ROOT / "apps/operator-panel/scripts/codesign_notarize_macos.sh"

FORMER_BRANDS = (("ae" + "gis" + "os").casefold(), ("bin" + "liquid").casefold())


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_workflow(path: Path) -> dict[object, object]:
    workflow = yaml.safe_load(_read(path))
    assert isinstance(workflow, dict)
    if True in workflow and "on" not in workflow:
        workflow["on"] = workflow.pop(True)
    return workflow


def test_active_workflows_use_no_former_product_identity() -> None:
    violations: list[str] = []
    for path in sorted(WORKFLOW_ROOT.glob("*.y*ml")):
        source = _read(path).casefold()
        if any(token in source for token in FORMER_BRANDS):
            violations.append(path.name)
    assert violations == []


def test_internal_unsigned_stages_the_canonical_binary_on_both_platforms() -> None:
    workflow = _read(INTERNAL_UNSIGNED)
    macos_source = (
        "            apps/operator-panel/src-tauri/target/debug/"
        "imperaos_operator_panel \\\n"
    )
    macos_destination = '"${STAGE_ROOT}/imperaos_operator_panel"'
    windows_source = (
        '"apps/operator-panel/src-tauri/target/debug/imperaos_operator_panel.exe"'
    )
    windows_destination = '"$stageRoot/imperaos_operator_panel.exe"'
    assert workflow.count(macos_source) == 1
    assert workflow.count(macos_destination) == 1
    assert workflow.count(windows_source) == 1
    assert workflow.count(windows_destination) == 1


def test_installer_smoke_uses_the_canonical_product_everywhere() -> None:
    canonical = "ImperaOS Operator Panel"
    assert f'-ExpectedProductName "{canonical}"' in _read(CLEAN_SMOKE)
    assert f'[string]$ExpectedProductName = "{canonical}"' in _read(WINDOWS_SMOKE)


def test_macos_quarantine_metadata_uses_the_canonical_brand() -> None:
    source = _read(MACOS_CODESIGN)
    assert 'QUARANTINE_TAG="0081;$(date +%s);ImperaOS;"' in source


def test_direct_release_scripts_use_no_former_product_identity() -> None:
    violations: list[str] = []
    for path in (WINDOWS_SMOKE, MACOS_CODESIGN):
        source = _read(path).casefold()
        if any(token in source for token in FORMER_BRANDS):
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_brand_gate_is_early_and_fail_closed() -> None:
    workflow = _read_workflow(WORKFLOW_ROOT / "ci.yml")
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict)
    test_job = jobs.get("test")
    assert isinstance(test_job, dict)
    steps = test_job.get("steps")
    assert isinstance(steps, list)

    names = [step.get("name") for step in steps if isinstance(step, dict)]
    assert names.count("Sync dependencies") == 1
    assert names.count("ImperaOS brand consistency gate") == 1
    assert names.count("Lint") == 1
    sync = names.index("Sync dependencies")
    gate = names.index("ImperaOS brand consistency gate")
    lint = names.index("Lint")
    assert sync < gate < lint

    gate_step = steps[gate]
    assert isinstance(gate_step, dict)
    assert gate_step.get("run") == "make brand-consistency-gate"
    assert gate_step.get("continue-on-error", False) is False
    assert "if" not in gate_step

    makefile = _read(ROOT / "Makefile")
    target = makefile.split("brand-consistency-gate:", maxsplit=1)[1].split(
        "\n\n", maxsplit=1
    )[0]
    assert "scripts/run_brand_consistency_gate.py" in target
    assert "--mode enforce" in target
