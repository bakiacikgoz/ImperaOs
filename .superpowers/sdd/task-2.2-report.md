# Task 2.2 Implementation Report

## Outcome

The Python distribution, package build, installed CLI, and active Python runtime
invocations now publish under the ImperaOS identity. The implementation commit is:

`fdd8f24a853375d477434ba131e8c1e57ce10ea2`

Its exact subject is `build: publish runtime under ImperaOS identity`.

## Changed files

- Distribution/build: `pyproject.toml`, `uv.lock`, `hatch_build.py`.
- Runtime identity and CLI: `imperaos/product_identity.py`, `imperaos/cli.py`.
- Active drill command arrays: `imperaos/control_plane/pilot_ops_drill.py`.
- Active script invocations: `scripts/demo_governance_v03.sh`,
  `scripts/evaluate_computer_use_integration_gate.py`,
  `scripts/run_control_plane_demo.py`,
  `scripts/run_qualification_soak_supervised.sh`,
  `scripts/run_rc_evidence_orchestrator_gate.py`, and
  `scripts/run_rc_release_decision_gate.py`.
- Tests: `tests/test_console_entrypoint_unicode_path.py` and
  `tests/test_distribution_wheel.py`.

The implementation commit contains 14 files, 235 insertions, and 96 deletions.

## TDD evidence

### Initial RED

Focused command:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_console_entrypoint_unicode_path.py `
  tests/test_distribution_wheel.py `
  tests/test_brand_identity.py `
  --basetemp C:\tmp\i22-red
```

Observed exit code `1`: 6 expected failures and 10 passes. The failures proved the
old project name, absent `imperaos` console launcher, old root/version help, old wheel
name and console entrypoints, and missing packaged identity resource.

Two additional test-first diagnostic cycles covered build integration:

- Exact editable mode plus the force-included resource initially exposed a physical
  namespace package that shadowed Hatch's editable redirect outside the repository.
  The focused test returned 2 failures and 1 pass before the wheel-only editable
  force-include override.
- Bare `uv build` exposed Hatch's unbounded default sdist scan of ignored Rust
  incremental output. The explicit sdist selection test failed with `KeyError:
  'sdist'` before the minimal sdist configuration was added.

### GREEN

The focused acceptance rerun returned exit code `0`:

```text
................                                                         [100%]
16 passed in 7.30s
```

The tests exercise both build-hook branches through behavior: Unicode-path editable
console/module execution covers the `editable` build, while real wheel construction
and inspection cover the standard build.

## Distribution metadata and lock

- Project name: `imperaos`.
- Version retained: `0.4.1`.
- Description: `ImperaOS governed AI workforce operating platform`.
- Author: `ImperaOS Contributors`.
- Only project script: `imperaos = imperaos.cli:app`.
- Hatch packages: `imperaos`, `benchmarks`, `research`, and `scripts`; `config`
  remains included.
- `branding/identity.json` is force-included as `imperaos/identity.json` from the
  single canonical source file.
- `hatch_build.py` prevents that wheel resource from creating an editable namespace
  package that shadows `imperaos.cli`; exact editable mode remains enabled.
- The explicit sdist selection makes bare `uv build` deterministic without including
  frontend/Tauri build output.

`uv lock` resolved 75 packages. The lock diff only removes the editable root package
record `imperaos==0.4.1` and adds the equivalent `imperaos==0.4.1` record. Dependency
constraints, resolved dependency versions, extras, and hashes are unchanged.

## Wheel inspection

Bare `uv build` completed successfully and produced:

- `dist/imperaos-0.4.1.tar.gz`
- `dist/imperaos-0.4.1-py3-none-any.whl`

Archive inspection confirmed:

- `imperaos/` package present;
- no `imperaos/` package;
- `imperaos/identity.json` present and byte-identical to
  `branding/identity.json`;
- the sole console entrypoint is `imperaos = imperaos.cli:app`;
- wheel metadata reports the approved name, version, summary, and author.

Generated `dist/` artifacts were removed after verification and are not committed.

## Clean external install

The wheel was installed non-editably into a fresh `C:\tmp\i22venv` virtual
environment. All probes ran from `C:\tmp\i22run`, with `PYTHONPATH` cleared:

| Probe | Result |
|---|---|
| `python -m imperaos --version` | `0.4.1`, exit 0 |
| `imperaos --version` | `0.4.1`, exit 0 |
| identity slug probe | `imperaos`, exit 0 |
| import origin | `C:\tmp\i22venv\Lib\site-packages\imperaos\__init__.py` |
| `imperaos.exe` present | false |
| `imperaos.exe` present | false |

## Verification

| Check | Result |
|---|---|
| `uv lock --check` | exit 0; lock current |
| `uv sync --python 3.11 --extra dev` | exit 0; 75 packages resolved |
| Focused metadata/CLI/wheel/identity tests | 16 passed |
| Full Python suite with `--basetemp C:\t\f` | 852 passed, 9 skipped, exit 0 |
| Ruff on every changed Python file | all checks passed |
| Bare `uv build` | sdist and wheel built successfully |
| Active removed-CLI invocation guard in `imperaos/`, `scripts/`, `tests/` | 0 matches |
| `git diff --check` | exit 0 |

A longer final base-temp spelling reproduced six pre-existing Windows deep-path
failures. A single failing case passed under `C:\t\r`, and the complete suite passed
under the required genuinely short base temp `C:\t\f`; no product-code change was
made for that environmental path-length condition.

## Brand inventory delta

Inventory mode exited `0`; audit status remains `fail` because later rebrand tasks
own the deferred contracts and surfaces.

| Metric | Task 2.1 | Task 2.2 | Delta |
|---|---:|---:|---:|
| Findings | 1,666 | 1,616 | -50 |
| Legacy content matches | 1,644 | 1,594 | -50 |
| Legacy path matches | 3 | 3 | 0 |
| Binary metadata matches | 19 | 19 | 0 |
| Built artifact matches | 0 | 0 | 0 |
| Scanned files | 1,505 | 1,505 | 0 |

## Deliberately deferred legacy tokens

The task intentionally preserves all deferred contracts, including `.imperaos`
state roots, `IMPERAOS_*` environment lookups, `imperaos_` metric names,
`imperaos_core`/`imperaos_team` runtime kinds, `imperaos-*` team identifiers,
legacy schema/manifest values, provider metadata keys, and signed or historical
evidence. Frontend/Tauri packages and resource directories, docs, and other
later-task surfaces were not rebranded here; active workflow automation is covered
by the post-review correction below.

## Post-review automation correction

Independent review identified one Important omission: active Makefile and GitHub
Actions automation still invoked the removed console/module name or watched the old
Python package directory. The correction is committed as:

`ac81712da4dce8914a788de48e11c99d44183ba6`

with subject `fix: update automation for ImperaOS CLI`.

The correction updates 76 active references across `Makefile` and eight workflow
files, covering direct `uv run` console calls, `python -m` calls, bundled-runtime
module probes, the compile target, and Python package-directory filters/arguments.
It deliberately leaves `.imperaos` state paths, `IMPERAOS_*` environment keys,
and `imperaos-runtime` Tauri resource directories unchanged.

### Review-fix TDD and verification

The new `tests/test_automation_distribution_identity.py` regression test scans
`Makefile` and all workflow YAML files for only four active categories. Its RED run
returned one failing test with 76 enumerated violations. After the automation update:

| Check | Result |
|---|---|
| Static automation regression | 1 passed |
| Existing workflow/static tests | 15 passed |
| Focused Task 2.2 tests | 17 passed |
| Full Python suite, `--basetemp C:\t\g` | 853 passed, 9 skipped |
| Ruff on the changed Python test | all checks passed |
| `uv lock --check` | exit 0; unchanged/current |
| Bare `uv build` | sdist and wheel built successfully |
| `git diff --check` | exit 0 |

Generated `dist/` artifacts were removed again after the review verification.

### Final inventory after review fix

The final inventory was rerun after the regression test and review fix were tracked.
Inventory mode exits 0; the audit remains intentionally `fail` for deferred work.

| Metric | Original Task 2.2 report | Post-review | Delta |
|---|---:|---:|---:|
| Findings | 1,616 | 1,554 | -62 |
| Legacy content matches | 1,594 | 1,532 | -62 |
| Legacy path matches | 3 | 3 | 0 |
| Binary metadata matches | 19 | 19 | 0 |
| Built artifact matches | 0 | 0 | 0 |
| Scanned files | 1,505 | 1,509 | +4 |

The net inventory delta includes the newly tracked build hook, distribution test,
Task 2.2 report, and automation regression test; the regression's literal detection
patterns are themselves inventory-visible. The active automation guard nevertheless
reports zero executable/module/package-directory violations.

## Second-review bundled-runtime correction

A second independent review found four workflow-called bundled-runtime scripts that
still selected the removed wheel distribution and executed the removed Python module.
The correction is committed as:

`d25378de064e26c7213c60dc64503c8b9aeb716b`

with subject `fix: update bundled runtime for ImperaOS wheel`.

The build scripts now select `imperaos-*.whl`, report ImperaOS wheel names, and
validate the bundled runtime with `-m imperaos`. The macOS and Windows verification
scripts use the same module probe. Their generated release-gate hints also show the
working ImperaOS module command.

The correction deliberately preserves the resource directory `imperaos-runtime`,
the manifest field `imperaos_version`, and the `IMPERAOS_*` environment-variable
contract, along with every other identifier deferred to later rebrand tasks.

### Second-review TDD and verification

The existing automation regression was extended first to scan the four runtime
scripts and detect old wheel globs/wording plus old module commands. Its RED run
failed with 17 enumerated violations: two wheel globs, three wheel-branding messages,
and twelve module probes or hints. None of the deliberately preserved identifiers
matched. After the minimal script edits, the guard passed.

| Check | Result |
|---|---|
| Static automation regression | 1 passed |
| Workflow/static aggregate | 14 passed |
| Focused Task 2.2 aggregate | 17 passed |
| Windows runtime-script PowerShell parse | pass, zero AST parse errors |
| Full Python suite, `--basetemp C:\t\i` | 853 passed, 9 skipped, exit 0 in 81.8 seconds |
| Ruff on the changed Python test | all checks passed |
| `uv lock --check` | exit 0; 75 packages resolved, lock unchanged/current |
| Bare `uv build` | `imperaos-0.4.1` sdist and wheel built successfully |
| `git diff --check` | exit 0 |

The generated `dist/` directory was removed after verification.

### Final inventory after second review

Inventory mode exits 0 and the audit remains intentionally `fail` for deferred work.
The final tracked-state metrics are:

| Metric | First review | Second review | Delta |
|---|---:|---:|---:|
| Findings | 1,554 | 1,541 | -13 |
| Legacy content matches | 1,532 | 1,519 | -13 |
| Legacy path matches | 3 | 3 | 0 |
| Binary metadata matches | 19 | 19 | 0 |
| Built artifact matches | 0 | 0 | 0 |
| Scanned files | 1,509 | 1,509 | 0 |

## Final transitive Windows installer-smoke correction

Controller review traced the Windows clean-smoke workflow into its installer-smoke
script and found three remaining runtime probes plus a distribution-facing version
artifact name. The correction is committed as:

`211bb6962ca7aac75001b1adc8e3ec2940576795`

with subject `fix: update installer smoke for ImperaOS runtime`.

`windows_installer_smoke.ps1` now executes all version, capability, and doctor probes
with `-m imperaos` and writes `imperaos-version.txt`. The bundled resource lookup at
`resources\imperaos-runtime` remains unchanged as required.

### Final correction TDD and verification

The automation regression was first extended to include the installer-smoke script
and its version-artifact name. RED reported four classified violations across three
lines: three legacy module probes and the legacy filename on the version-probe line.
The preserved resource path did not match. After the minimal script edit, GREEN
returned one passing guard test.

| Check | Result |
|---|---|
| Static automation regression | 1 passed |
| Windows installer-smoke PowerShell parse | pass, zero AST parse errors |
| Windows release workflow static tests | 6 passed |
| Focused Task 2.2 aggregate | 17 passed |
| Full Python suite, `--basetemp C:\t\j` | 853 passed, 9 skipped, exit 0 in 92.9 seconds |
| Ruff on the changed Python test | all checks passed |
| `uv lock --check` | exit 0; 75 packages resolved, lock unchanged/current |
| Bare `uv build` | `imperaos-0.4.1` sdist and wheel built successfully |
| `git diff --check` | exit 0 |

A comprehensive guard enumerated 138 tracked files under `Makefile`, `.github/**`,
`apps/operator-panel/scripts/**`, and `scripts/**`. It found zero occurrences of the
four removed active forms: `-m imperaos`, `uv run imperaos`, `imperaos-*.whl`, or
`compileall imperaos`. Generated `dist/` artifacts were removed afterward.

### Final tracked-state inventory

Inventory mode exits 0; its audit status remains intentionally `fail` for deferred
rebrand work. Before this report section was added, the implementation-only state
contained 1,539 findings and 1,517 content matches. The literal regression patterns
documented above are themselves inventory-visible, producing the final counts below.

| Metric | Prior report | Final | Delta |
|---|---:|---:|---:|
| Findings | 1,541 | 1,542 | +1 |
| Legacy content matches | 1,519 | 1,520 | +1 |
| Legacy path matches | 3 | 3 | 0 |
| Binary metadata matches | 19 | 19 | 0 |
| Built artifact matches | 0 | 0 | 0 |
| Scanned files | 1,509 | 1,509 | 0 |
