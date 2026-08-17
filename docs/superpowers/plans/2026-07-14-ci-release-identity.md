# ImperaOS CI and Release Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining active former product and binary identities from GitHub Actions and desktop release scripts while preserving release safety and the early fail-closed brand gate.

**Architecture:** Treat the workflows and their two direct platform scripts as one identity boundary. Add a file-backed regression contract first, then make only four consumer edits; already-canonical workflows, secrets, environment variables, cache keys, artifact roots, and later-phase soak/evidence surfaces remain unchanged.

**Tech Stack:** GitHub Actions YAML, Python/pytest, PowerShell, Bash, Tauri/Rust, Make

## Global Constraints

- Canonical debug binary names are exactly `imperaos_operator_panel` and `imperaos_operator_panel.exe`.
- Canonical installed product is exactly `ImperaOS Operator Panel`.
- Canonical macOS quarantine metadata brand is exactly `ImperaOS`.
- The CI brand gate command remains `make brand-consistency-gate` and the Makefile target remains `--mode enforce`.
- No former-path or former-binary fallback may be added.
- Existing standard platform secrets and environment names (`WINDOWS_SIGNING_*`, `MACOS_SIGNING_*`, `APPLE_*`) remain unchanged.
- Generic artifact roots already free of former identity remain unchanged.
- Qualification soak/temp/service-label and observability identity work remains Phase 7.1.
- Python evidence descriptions, schemas, and historical evidence remain outside Task 6.2.
- Full remote-CI green is deferred to Phase 10; Task 6.2 must not weaken the gate or claim repository-wide inventory success.
- No push, workflow dispatch, secret mutation, signing, notarization, or release publication occurs.
- The implementation commit subject must be exactly `ci: move build and release workflows to ImperaOS`.

## File Structure

- `tests/test_ci_release_identity.py`: exact positive and negative identity contract for all workflows, the two release scripts, and the early brand gate.
- `.github/workflows/operator-panel-internal-unsigned-build.yml`: stages the canonical Rust binary on macOS and Windows.
- `.github/workflows/operator-panel-windows-clean-smoke.yml`: passes the canonical product to installer smoke.
- `apps/operator-panel/scripts/windows_installer_smoke.ps1`: defaults to the canonical installed product.
- `apps/operator-panel/scripts/codesign_notarize_macos.sh`: records the canonical quarantine metadata brand.
- `.superpowers/sdd/task-6.2-report.md`: durable RED/GREEN, syntax, inventory, scope, and remote-CI deferral evidence.

---

### Task 1: CI and Release Identity Contract

**Files:**
- Create: `tests/test_ci_release_identity.py`
- Modify: `.github/workflows/operator-panel-internal-unsigned-build.yml`
- Modify: `.github/workflows/operator-panel-windows-clean-smoke.yml`
- Modify: `apps/operator-panel/scripts/windows_installer_smoke.ps1`
- Modify: `apps/operator-panel/scripts/codesign_notarize_macos.sh`

**Interfaces:**
- Consumes: the Rust binary identity from Task 5.3, the runtime resource identity from Task 6.1, the installer-smoke `ExpectedProductName` parameter, and the existing CI brand-gate target.
- Produces: workflow staging and platform-script identity that agree on ImperaOS, plus `tests/test_ci_release_identity.py` as the regression contract.

- [ ] **Step 1: Write the failing file-backed regression contract**

Create `tests/test_ci_release_identity.py` with this complete content:

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / ".github/workflows"
INTERNAL_UNSIGNED = WORKFLOW_ROOT / "operator-panel-internal-unsigned-build.yml"
CLEAN_SMOKE = WORKFLOW_ROOT / "operator-panel-windows-clean-smoke.yml"
WINDOWS_SMOKE = ROOT / "apps/operator-panel/scripts/windows_installer_smoke.ps1"
MACOS_CODESIGN = ROOT / "apps/operator-panel/scripts/codesign_notarize_macos.sh"

FORMER_BRANDS = (("imperaos" + "os").casefold(), ("bin" + "liquid").casefold())


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_active_workflows_use_no_former_product_identity() -> None:
    violations: list[str] = []
    for path in sorted(WORKFLOW_ROOT.glob("*.y*ml")):
        source = _read(path).casefold()
        if any(token in source for token in FORMER_BRANDS):
            violations.append(path.name)
    assert violations == []


def test_internal_unsigned_stages_the_canonical_binary_on_both_platforms() -> None:
    workflow = _read(INTERNAL_UNSIGNED)
    assert workflow.count("imperaos_operator_panel") == 4
    assert "target/debug/imperaos_operator_panel" in workflow
    assert "target/debug/imperaos_operator_panel.exe" in workflow
    assert '"${STAGE_ROOT}/imperaos_operator_panel"' in workflow
    assert '"$stageRoot/imperaos_operator_panel.exe"' in workflow


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
    workflow = _read(WORKFLOW_ROOT / "ci.yml")
    sync = workflow.index("Sync dependencies")
    gate = workflow.index("ImperaOS brand consistency gate")
    lint = workflow.index("Lint")
    assert sync < gate < lint
    assert "run: make brand-consistency-gate" in workflow

    makefile = _read(ROOT / "Makefile")
    target = makefile.split("brand-consistency-gate:", maxsplit=1)[1].split(
        "\n\n", maxsplit=1
    )[0]
    assert "scripts/run_brand_consistency_gate.py" in target
    assert "--mode enforce" in target
```

- [ ] **Step 2: Run RED and record the expected failures**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_ci_release_identity.py
```

Expected: the workflow-wide negative test, canonical binary test, installer product test, quarantine metadata test, and direct-script negative test fail on the four current consumers; the existing early brand-gate test passes.

- [ ] **Step 3: Apply the four minimal identity edits**

Make only these replacements:

```text
.github/workflows/operator-panel-internal-unsigned-build.yml
  target/debug/imperaos_operator_panel -> target/debug/imperaos_operator_panel
  ${STAGE_ROOT}/imperaos_operator_panel -> ${STAGE_ROOT}/imperaos_operator_panel
  target/debug/imperaos_operator_panel.exe -> target/debug/imperaos_operator_panel.exe
  $stageRoot/imperaos_operator_panel.exe -> $stageRoot/imperaos_operator_panel.exe

.github/workflows/operator-panel-windows-clean-smoke.yml
  -ExpectedProductName "ImperaOS Operator Panel" -> -ExpectedProductName "ImperaOS Operator Panel"

apps/operator-panel/scripts/windows_installer_smoke.ps1
  [string]$ExpectedProductName = "ImperaOS Operator Panel" -> [string]$ExpectedProductName = "ImperaOS Operator Panel"

apps/operator-panel/scripts/codesign_notarize_macos.sh
  QUARANTINE_TAG="0081;$(date +%s);ImperaOS;" -> QUARANTINE_TAG="0081;$(date +%s);ImperaOS;"
```

Do not change runtime paths, artifact roots, workflow triggers, signing variables, cache keys, or release eligibility metadata.

- [ ] **Step 4: Run focused GREEN tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_ci_release_identity.py `
  tests/test_automation_distribution_identity.py `
  tests/test_operator_panel_internal_unsigned_workflow.py `
  tests/test_windows_release_workflows_static.py `
  tests/test_macos_release_workflows_static.py `
  tests/test_ci_node_action_inventory.py
.\.venv\Scripts\python.exe -m ruff check tests/test_ci_release_identity.py
```

Expected: all selected tests and Ruff pass.

- [ ] **Step 5: Parse platform automation and every workflow**

Run PowerShell AST parsing:

```powershell
$tokens = $null
$errors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile(
  (Resolve-Path 'apps/operator-panel/scripts/windows_installer_smoke.ps1'),
  [ref]$tokens,
  [ref]$errors
)
if ($errors.Count -ne 0) { throw "PowerShell parse failed: $errors" }
```

Run Bash syntax validation:

```powershell
& 'C:\Program Files\Git\usr\bin\bash.exe' -n apps/operator-panel/scripts/codesign_notarize_macos.sh
```

Run YAML parsing:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; import yaml; paths=sorted(Path('.github/workflows').glob('*.y*ml')); [yaml.safe_load(p.read_text(encoding='utf-8')) for p in paths]; print(f'workflow-yaml-ok:{len(paths)}')"
```

Expected: no PowerShell errors, Bash exits zero, and every workflow parses.

- [ ] **Step 6: Prove the canonical Rust binary exists**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" build -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml --bin imperaos_operator_panel
```

Expected: Cargo builds `imperaos_operator_panel` successfully; no former binary fallback is needed.

- [ ] **Step 7: Run the cross-cutting Python regression suite**

Run with the project tools on `PATH` and a short temp root:

```powershell
$env:PATH="$env:APPDATA\Python\Python314\Scripts;C:\Users\duzey\AppData\Local\CodexTools\MinGit\cmd;"+$env:PATH
$env:TEMP='C:\t'
$env:TMP='C:\t'
.\.venv\Scripts\python.exe -m pytest -q --basetemp C:\t\task-6-2-full
```

Expected: the full Python suite passes with only the repository's documented skips.

- [ ] **Step 8: Verify exact scope and commit the implementation**

Construct former tokens in PowerShell and scan only active Task 6.2 surfaces:

```powershell
$formerProduct = 'ImperaOS' + 'OS'
$formerDistribution = 'Bin' + 'Liquid'
$active = @('.github/workflows', 'apps/operator-panel/scripts/windows_installer_smoke.ps1', 'apps/operator-panel/scripts/codesign_notarize_macos.sh')
rg -n -i "$formerProduct|$formerDistribution" -- $active
if ($LASTEXITCODE -eq 0) { throw 'former CI/release identity remains in active Task 6.2 scope' }
```

Run `git diff --check`, inspect `git status --short`, stage exactly the five Task 1 files, and commit:

```powershell
git commit -m "ci: move build and release workflows to ImperaOS"
```

Expected: the implementation commit contains the regression test and four minimal consumer edits only.

---

### Task 2: Task 6.2 Verification Evidence

**Files:**
- Create: `.superpowers/sdd/task-6.2-report.md`

**Interfaces:**
- Consumes: the committed Task 1 SHA, RED/GREEN outputs, syntax/build evidence, and committed-HEAD inventory JSON.
- Produces: a durable Task 6.2 report for independent spec and quality review.

- [ ] **Step 1: Run committed-HEAD inventory**

Run:

```powershell
$env:PATH="$env:APPDATA\Python\Python314\Scripts;C:\Users\duzey\AppData\Local\CodexTools\MinGit\cmd;"+$env:PATH
.\.venv\Scripts\python.exe scripts/run_brand_consistency_gate.py --mode inventory --repo-root . --output-root .superpowers/sdd/task-6.2-brand-inventory --json
```

Expected: the command produces JSON tied to the implementation SHA. Repository status may remain `fail` because later phases still own the remaining findings; Task 6.2 active workflow/script scope must be clean.

- [ ] **Step 2: Create the durable report**

Create `.superpowers/sdd/task-6.2-report.md` with these exact sections and actual values:

```markdown
# Task 6.2 Verification Report

## Scope
## Implementation Commit
## RED Evidence
## Focused GREEN Evidence
## Workflow, PowerShell, and Bash Syntax
## Canonical Binary Build
## Full Python Regression
## Active CI and Release Identity Scan
## Early Blocking Brand Gate
## Brand Inventory
## Remote CI Deferral
## Phase 7 Boundary
## Final Status
```

Record actual test counts, parsed workflow count, inventory SHA/counts, and exact implementation diff. State that no push, workflow dispatch, secret mutation, signing, notarization, or release publication occurred. State that full remote-CI green is deferred to Phase 10 because the early enforcing gate correctly continues to see later-phase findings.

- [ ] **Step 3: Verify and commit the report**

Run `git diff --check`, validate report SHA/counts against the JSON, ensure generated inventory is ignored, then commit only the report:

```powershell
git add -f -- .superpowers/sdd/task-6.2-report.md
git commit -m "docs: record task 6.2 verification"
```

Expected: the worktree is clean after the report commit.

- [ ] **Step 4: Complete two-stage review**

Give fresh reviewers the approved design, this plan, Task 1 implementation commit, Task 2 report commit, raw execution handoffs, and diff packages. Require:

```text
1. Spec compliance: exact canonical identities, minimal four-consumer scope, early fail-closed gate, and Phase 7/10 boundaries.
2. Code quality: regression strength, YAML/PowerShell/Bash safety, binary-path correctness, report consistency, and no release/secret side effects.
```

Fix every Critical or Important finding with a focused regression and re-review. Record Minor findings in the SDD progress ledger. Final Task 6.2 acceptance requires both task reviews and the combined final review to be Ready for Phase 7.
