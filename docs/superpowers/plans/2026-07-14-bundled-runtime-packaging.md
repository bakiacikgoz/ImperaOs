# ImperaOS Bundled Runtime Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Atomically move the Operator Panel bundled runtime to `imperaos-runtime`, repair the Windows/Unicode Tauri smoke bootstrap, and prove the Windows package can build and verify a real ImperaOS runtime.

**Architecture:** Keep one canonical resource directory and update every active path consumer in the same implementation commit; do not add aliases, compatibility paths, or fallbacks. File-backed Python tests and Rust resolver tests lock the identity, while existing platform validators preserve fail-closed manifest and runtime behavior.

**Tech Stack:** Python/pytest, Rust/Cargo, Tauri 2, TypeScript/Node, PowerShell, Bash, GitHub Actions YAML, pnpm 10.29.2

## Global Constraints

- Canonical resource directory: `apps/operator-panel/src-tauri/resources/imperaos-runtime/`.
- Tauri resource entry: `resources/imperaos-runtime/`.
- Windows Python path: `imperaos-runtime/python/Scripts/python.exe`.
- macOS/Linux Python path: `imperaos-runtime/python/bin/python`.
- Wheel glob, Python module, and manifest key remain exactly `imperaos-*.whl`, `python -m imperaos`, and `imperaos_version`.
- No former-path fallback, compatibility directory, duplicate resource, or symlink may remain.
- Workflow edits are path-only; broader CI/release identity work belongs to Task 6.2.
- Historical reports, immutable evidence, and the Task 5.3 design/plan remain unchanged.
- The only smoke bootstrap repair is `fileURLToPath(import.meta.url)` in `tauri-launched-smoke.ts`.
- Generated runtime payload is ignored and removed after verification; only the canonical README is tracked.
- The implementation commit subject must be exactly `build: package the ImperaOS bundled runtime`.

## File Structure

- `tests/test_bundled_runtime_identity.py`: file-backed regression contract for the directory, active consumers, runtime distribution identity, and smoke bootstrap.
- `apps/operator-panel/src-tauri/resources/imperaos-runtime/README.txt`: sole tracked placeholder in the canonical resource directory.
- `apps/operator-panel/src-tauri/tauri.conf.json`: packages the canonical resource.
- `apps/operator-panel/src-tauri/src/bridge.rs`: resolves the canonical direct and Tauri-nested Python paths.
- `apps/operator-panel/scripts/build_bundled_runtime_windows.ps1`: builds the Windows runtime into the canonical directory and writes ImperaOS-only metadata.
- `apps/operator-panel/scripts/build_bundled_runtime_macos.sh`: macOS equivalent.
- `apps/operator-panel/scripts/verify_bundled_runtime_macos.sh`: verifies the canonical macOS directory.
- `apps/operator-panel/scripts/windows_installer_smoke.ps1`: locates the installed canonical runtime.
- `apps/operator-panel/scripts/tauri-launched-smoke.ts`: derives its script directory safely on Windows and Unicode paths.
- `.gitignore`, five workflow files, `apps/operator-panel/README.md`, `docs/MACOS_M4_LOCAL_TRIAL_RUNBOOK.md`, and `docs/RELEASE_CHECKLIST.md`: active direct consumers updated atomically.
- `.superpowers/sdd/task-6.1-report.md`: durable RED/GREEN, build, smoke, cleanup, inventory, and scope evidence.

---

### Task 1: Atomic Runtime Identity and Packaging Implementation

**Files:**
- Create: `tests/test_bundled_runtime_identity.py`
- Delete: `apps/operator-panel/src-tauri/resources/imperaos-runtime/README.txt`
- Create: `apps/operator-panel/src-tauri/resources/imperaos-runtime/README.txt`
- Modify: `.gitignore`
- Modify: `apps/operator-panel/src-tauri/tauri.conf.json`
- Modify: `apps/operator-panel/src-tauri/src/bridge.rs`
- Modify: `apps/operator-panel/scripts/build_bundled_runtime_windows.ps1`
- Modify: `apps/operator-panel/scripts/build_bundled_runtime_macos.sh`
- Modify: `apps/operator-panel/scripts/verify_bundled_runtime_macos.sh`
- Modify: `apps/operator-panel/scripts/windows_installer_smoke.ps1`
- Modify: `apps/operator-panel/scripts/tauri-launched-smoke.ts`
- Modify: `.github/workflows/windows-ci.yml`
- Modify: `.github/workflows/operator-panel-runtime-matrix.yml`
- Modify: `.github/workflows/operator-panel-release-windows.yml`
- Modify: `.github/workflows/operator-panel-release-macos.yml`
- Modify: `.github/workflows/operator-panel-internal-unsigned-build.yml`
- Modify: `apps/operator-panel/README.md`
- Modify: `docs/MACOS_M4_LOCAL_TRIAL_RUNBOOK.md`
- Modify: `docs/RELEASE_CHECKLIST.md`

**Interfaces:**
- Consumes: Tauri's resource directory, `bundled_python_relative_path() -> &'static str`, platform build/verify scripts, and the existing `imperaos_version` manifest validator contract.
- Produces: one resource tree named `imperaos-runtime`, direct and nested Rust resolution for that tree, and a file-backed regression suite named `tests/test_bundled_runtime_identity.py`.

- [ ] **Step 1: Write the failing file-backed identity contract**

Create `tests/test_bundled_runtime_identity.py` with the complete contract below. Construct the former tokens so the regression test does not itself create a brand-inventory finding.

```python
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
    windows = (ROOT / "apps/operator-panel/scripts/build_bundled_runtime_windows.ps1").read_text(encoding="utf-8")
    macos = (ROOT / "apps/operator-panel/scripts/build_bundled_runtime_macos.sh").read_text(encoding="utf-8")
    for source in (windows, macos):
        assert "imperaos-*.whl" in source
        assert "-m imperaos" in source
        assert "imperaos_version" in source
        assert "ImperaOS Operator Panel" in source


def test_tauri_smoke_bootstrap_is_windows_and_unicode_safe() -> None:
    source = (ROOT / "apps/operator-panel/scripts/tauri-launched-smoke.ts").read_text(encoding="utf-8")
    assert "import { fileURLToPath } from 'node:url';" in source
    assert "path.dirname(fileURLToPath(import.meta.url))" in source
    assert "new URL(import.meta.url).pathname" not in source
```

- [ ] **Step 2: Make the Rust expectation RED before changing the resolver**

In `apps/operator-panel/src-tauri/src/bridge.rs`, change only the two expectations in `bundled_python_relative_path_matches_platform`:

```rust
if cfg!(windows) {
    assert_eq!(path, "imperaos-runtime/python/Scripts/python.exe");
} else {
    assert_eq!(path, "imperaos-runtime/python/bin/python");
}
```

- [ ] **Step 3: Run both focused RED gates**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_bundled_runtime_identity.py
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml bundled_python_relative_path_matches_platform
```

Expected: pytest fails because `imperaos-runtime` is absent and active consumers still contain the former path; the Rust test fails because the implementation still returns the former relative path.

- [ ] **Step 4: Create the canonical tracked resource and remove the former tracked placeholder**

Delete `apps/operator-panel/src-tauri/resources/imperaos-runtime/README.txt` and create `apps/operator-panel/src-tauri/resources/imperaos-runtime/README.txt` with exactly:

```text
Generated runtime bundle location for ImperaOS Operator Panel.

Release gate:
1) python/bin/python is executable on macOS bundles
2) python/bin/python -m imperaos --version passes
3) RUNTIME_MANIFEST.txt records platform, arch, Python version, ImperaOS version, wheel hash, git evidence, and build time

Do not ship placeholder-only runtime contents.
```

- [ ] **Step 5: Update the core packaging and resolver implementations**

Apply these exact identity replacements, without adding fallback branches:

```text
apps/operator-panel/src-tauri/tauri.conf.json
  resources/imperaos-runtime/ -> resources/imperaos-runtime/

apps/operator-panel/src-tauri/src/bridge.rs
  imperaos-runtime/python/Scripts/python.exe -> imperaos-runtime/python/Scripts/python.exe
  imperaos-runtime/python/bin/python -> imperaos-runtime/python/bin/python

apps/operator-panel/scripts/build_bundled_runtime_windows.ps1
  src-tauri\resources\imperaos-runtime -> src-tauri\resources\imperaos-runtime
  Generated Windows runtime bundle for ImperaOS Operator Panel. -> Generated Windows runtime bundle for ImperaOS Operator Panel.

apps/operator-panel/scripts/build_bundled_runtime_macos.sh
  src-tauri/resources/imperaos-runtime -> src-tauri/resources/imperaos-runtime
  Generated runtime bundle location for ImperaOS Operator Panel. -> Generated runtime bundle location for ImperaOS Operator Panel.

apps/operator-panel/scripts/verify_bundled_runtime_macos.sh
  src-tauri/resources/imperaos-runtime -> src-tauri/resources/imperaos-runtime

apps/operator-panel/scripts/windows_installer_smoke.ps1
  resources\imperaos-runtime -> resources\imperaos-runtime
```

Keep the existing safety boundary in the Windows builder: resolve `src-tauri/resources`, require the target to remain below that parent, and remove only the canonical runtime directory.

- [ ] **Step 6: Repair only the accepted Tauri smoke bootstrap**

In `apps/operator-panel/scripts/tauri-launched-smoke.ts`, add the Node URL import and replace the unsafe initializer:

```typescript
import { fileURLToPath } from 'node:url';

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
```

Do not edit other scripts that use `new URL(import.meta.url).pathname`.

- [ ] **Step 7: Update all atomic direct consumers**

Replace every runtime path segment in the listed files while preserving the surrounding workflow, command, artifact, and display names:

```text
.gitignore
  resources/imperaos-runtime/ -> resources/imperaos-runtime/

.github/workflows/windows-ci.yml
.github/workflows/operator-panel-runtime-matrix.yml
.github/workflows/operator-panel-release-windows.yml
.github/workflows/operator-panel-release-macos.yml
.github/workflows/operator-panel-internal-unsigned-build.yml
  imperaos-runtime -> imperaos-runtime (path segments only)

apps/operator-panel/README.md
docs/MACOS_M4_LOCAL_TRIAL_RUNBOOK.md
docs/RELEASE_CHECKLIST.md
  imperaos-runtime -> imperaos-runtime
  -m imperaos -> -m imperaos
```

Do not change workflow artifact labels, product/binary expectations, environment names, secret names, cache keys, or unrelated release prose; those remain Task 6.2.

- [ ] **Step 8: Run focused GREEN gates**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_bundled_runtime_identity.py tests/test_automation_distribution_identity.py tests/test_serialized_contract_identity.py tests/test_runtime_manifest_validator.py tests/test_macos_local_trial_gate.py
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml bundled_python_relative_path
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml resolve_bundled_python_from_resource_dir
```

Expected: all selected Python tests pass; all selected Rust resolver tests pass for direct and Tauri-nested layouts.

- [ ] **Step 9: Parse every changed platform automation file**

Run PowerShell AST parsing for both `.ps1` files:

```powershell
$paths = @(
  'apps/operator-panel/scripts/build_bundled_runtime_windows.ps1',
  'apps/operator-panel/scripts/windows_installer_smoke.ps1'
)
foreach ($path in $paths) {
  $tokens = $null
  $errors = $null
  $null = [System.Management.Automation.Language.Parser]::ParseFile(
    (Resolve-Path $path), [ref]$tokens, [ref]$errors
  )
  if ($errors.Count -ne 0) { throw "$path parse failed: $errors" }
}
```

Run Bash syntax checks:

```powershell
& 'C:\Program Files\Git\bin\bash.exe' -n apps/operator-panel/scripts/build_bundled_runtime_macos.sh
& 'C:\Program Files\Git\bin\bash.exe' -n apps/operator-panel/scripts/verify_bundled_runtime_macos.sh
```

Run YAML parsing for the five changed workflows:

```powershell
.\.venv\Scripts\python.exe -c "from pathlib import Path; import yaml; paths=[Path(p) for p in ['.github/workflows/windows-ci.yml','.github/workflows/operator-panel-runtime-matrix.yml','.github/workflows/operator-panel-release-windows.yml','.github/workflows/operator-panel-release-macos.yml','.github/workflows/operator-panel-internal-unsigned-build.yml']]; [yaml.safe_load(p.read_text(encoding='utf-8')) for p in paths]; print('workflow-yaml-ok')"
```

Expected: no PowerShell parse errors, both shell scripts return zero, and Python prints `workflow-yaml-ok`.

- [ ] **Step 10: Run Rust, frontend, and non-GUI Tauri gates**

Run:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" fmt --check --manifest-path apps/operator-panel/src-tauri/Cargo.toml
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml
corepack pnpm@10.29.2 --dir apps/operator-panel test
corepack pnpm@10.29.2 --dir apps/operator-panel lint
corepack pnpm@10.29.2 --dir apps/operator-panel build
corepack pnpm@10.29.2 --dir apps/operator-panel run tauri:smoke
```

Expected: Rust formatting and tests pass, frontend tests/lint/build pass, and the contract-mode Tauri smoke report passes.

- [ ] **Step 11: Build and verify a real Windows bundled runtime**

Run with the project environment on `PATH`:

```powershell
$env:PATH="$env:APPDATA\Python\Python314\Scripts;C:\Users\duzey\AppData\Local\CodexTools\MinGit\cmd;"+$env:PATH
& .\apps\operator-panel\scripts\build_bundled_runtime_windows.ps1 -Arch x64 -PythonBin '.\.venv\Scripts\python.exe'
& .\apps\operator-panel\scripts\verify_bundled_runtime_windows.ps1 -RuntimeDir 'apps/operator-panel/src-tauri/resources/imperaos-runtime'
```

Expected: an `imperaos-*.whl` is built or selected, the nested Python reports an ImperaOS version, manifest validation succeeds, and the verifier reports the bundled runtime ready without former module/path identity.

- [ ] **Step 12: Run the launched Tauri smoke with desktop permission**

Run:

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel run tauri:smoke:launch
```

Expected: the script no longer constructs a duplicated `C:\C:\...` or percent-encoded Unicode path. Record a pass, or record the exact later platform/tooling blocker without weakening the gate.

- [ ] **Step 13: Clean only generated runtime payload and restore the canonical README**

Resolve both the resource parent and target, verify the target is exactly the canonical child, remove every generated child except `README.txt`, then replace the generated README with the canonical text from Step 4 using `apply_patch`.

```powershell
$parent = (Resolve-Path 'apps/operator-panel/src-tauri/resources').Path
$target = (Resolve-Path 'apps/operator-panel/src-tauri/resources/imperaos-runtime').Path
$expected = [System.IO.Path]::GetFullPath((Join-Path $parent 'imperaos-runtime'))
if (-not [string]::Equals($target, $expected, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing cleanup outside canonical runtime: $target"
}
Get-ChildItem -LiteralPath $target -Force |
  Where-Object Name -ne 'README.txt' |
  Remove-Item -Recurse -Force
```

Expected: `imperaos-runtime/README.txt` is the only remaining runtime resource file and Git reports no generated runtime payload.

- [ ] **Step 14: Prove exact scope and commit the implementation**

Run targeted active scans; construct former tokens in PowerShell so the command does not copy them into reports:

```powershell
$formerRuntime = 'bin' + 'liquid-runtime'
$formerModule = '-m ' + 'bin' + 'liquid'
$active = @(
  '.gitignore',
  'apps/operator-panel/src-tauri/tauri.conf.json',
  'apps/operator-panel/src-tauri/src/bridge.rs',
  'apps/operator-panel/scripts',
  '.github/workflows',
  'apps/operator-panel/README.md',
  'docs/MACOS_M4_LOCAL_TRIAL_RUNBOOK.md',
  'docs/RELEASE_CHECKLIST.md'
)
rg -n --fixed-strings $formerRuntime -- $active
if ($LASTEXITCODE -eq 0) { throw 'former runtime path remains in active scope' }
rg -n --fixed-strings $formerModule -- apps/operator-panel/README.md docs/MACOS_M4_LOCAL_TRIAL_RUNBOOK.md docs/RELEASE_CHECKLIST.md
if ($LASTEXITCODE -eq 0) { throw 'former module invocation remains in active runbooks' }
```

Run `git diff --check`, inspect `git status --short`, stage only the files named in this task, and commit:

```powershell
git commit -m "build: package the ImperaOS bundled runtime"
```

Expected: one atomic implementation commit with the exact subject and no generated runtime contents.

---

### Task 2: Committed Verification Evidence and Independent Review

**Files:**
- Create: `.superpowers/sdd/task-6.1-report.md`

**Interfaces:**
- Consumes: the committed Task 1 implementation SHA and all Task 1 command outputs.
- Produces: a durable Task 6.1 verification report suitable for independent spec and quality review.

- [ ] **Step 1: Run committed-HEAD brand inventory and final repository checks**

Run:

```powershell
$env:PATH="$env:APPDATA\Python\Python314\Scripts;C:\Users\duzey\AppData\Local\CodexTools\MinGit\cmd;"+$env:PATH
.\.venv\Scripts\python.exe scripts/run_brand_consistency_gate.py --mode inventory --repo-root . --output-root .superpowers/sdd/task-6.1-brand-inventory --json
git diff HEAD^ --check
git status --short --branch
```

Expected: inventory completes against the committed implementation HEAD, the implementation diff has no whitespace errors, and only the report/inventory evidence expected by this step is untracked or modified.

- [ ] **Step 2: Write the Task 6.1 report**

Create `.superpowers/sdd/task-6.1-report.md` with these exact sections and concrete values from the actual command outputs:

```markdown
# Task 6.1 Verification Report

## Scope
## Implementation Commit
## RED Evidence
## Focused GREEN Evidence
## Rust and Frontend Gates
## PowerShell, Bash, and Workflow Syntax
## Real Windows Runtime Build and Verification
## Launched Tauri Smoke
## Generated Payload Cleanup
## Active Former-Identity Scan
## Brand Inventory
## macOS Execution Limitation
## Task 6.2 Boundary
## Final Status
```

The report must state that real macOS runtime execution was unavailable on Windows, if that remains true; distinguish this from the passing portable shell/static/validator evidence. Record the launched-smoke result or exact post-bootstrap blocker. Do not paste secret-bearing environment values or rewrite historical evidence.

- [ ] **Step 3: Verify and commit only the report**

Run `git diff --check`, confirm the report cites the committed implementation SHA and actual counts, then commit:

```powershell
git add -- .superpowers/sdd/task-6.1-report.md
git commit -m "docs: record task 6.1 verification"
```

Expected: the worktree is clean after the report commit; generated inventory/runtime payload is not committed.

- [ ] **Step 4: Request two-stage independent review**

Give a fresh reviewer the approved design, this plan, implementation commit, and report commit. Require separate answers for:

```text
1. Spec compliance: does the implementation cover every Task 6.1 requirement without entering Task 6.2 or rewriting historical evidence?
2. Code quality: are cleanup boundaries, resolver behavior, build/verify failure modes, tests, and reports technically sound?
```

If review finds a real defect, apply `superpowers:receiving-code-review`, reproduce it, fix it with the smallest scoped change, rerun the affected gates plus inventory, update the report, and request re-review. Final acceptance requires both reviews to say Ready.
