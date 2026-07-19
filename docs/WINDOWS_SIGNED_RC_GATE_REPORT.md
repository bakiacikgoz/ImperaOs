# Windows Signed RC Gate Report

Date: 2026-05-04
Branch: windows-public-release-evidence-closure, continuing from windows-signed-rc-gate
Commit: not committed
Reconciliation Update: included in current working tree
Status: PARTIAL for public release; signed RC gate reconciled

## Summary

This change adds a fail-closed Windows public release gate evaluator. Signing can produce a signed release-candidate artifact, but it no longer sets `public_release_allowed=true` by itself. Public or enterprise Windows release remains blocked until signing, timestamp verification, clean VM installer smoke, installed bundled runtime smoke, operator capabilities, doctor, and Windows computer-use-disabled evidence all pass.

## Branch Reconciliation

Commands run before this reconciliation edit:

```text
$ git status --short --branch --untracked-files=all
## windows-signed-rc-gate

$ git branch --show-current
windows-signed-rc-gate

$ git diff --stat
```

`git diff --stat` produced no output, meaning the branch worktree was clean before this report reconciliation update.

Required files were verified present:

- `scripts/evaluate_windows_release_gate.py`: present
- `tests/test_windows_release_gate.py`: present

Workflow check:

- `.github/workflows/operator-panel-release-windows.yml` signing status writes `signed_rc_allowed`, signing/timestamp/verify evidence, and external blocker status.
- The signing step does not write `public_release_allowed=true`.
- `windows-release-status.json` does not own the public release decision.
- The public release decision is produced only by `artifacts/windows-public-release-gate/windows-public-release-gate.json`.

## Changed Files

- `scripts/evaluate_windows_release_gate.py`
- `tests/test_windows_release_gate.py`
- `.github/workflows/operator-panel-release-windows.yml`
- `apps/operator-panel/scripts/sign_windows_artifacts.ps1`
- `apps/operator-panel/scripts/windows_installer_smoke.ps1`
- `docs/WINDOWS_INSTALLER_SMOKE.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/RELEASE_GATE_v0.5.md`
- `QUALIFICATION_MATRIX.md`
- `README.md`
- `DEPLOYMENT_GUIDE.md`

## Release Gate Inputs

- `artifacts/windows-release-evidence/windows-release-status.json`
- `artifacts/windows-installer-smoke/windows-installer-smoke.json`
- `artifacts/windows-installer-smoke/operator_capabilities.json`
- `artifacts/windows-installer-smoke/doctor_balanced.json`
- required runtime manifest and bundle hash evidence

## Release Gate Output

The evaluator writes:

```text
artifacts/windows-public-release-gate/windows-public-release-gate.json
```

Expected blocked signed-RC-without-clean-VM shape:

```json
{
  "status": "blocked",
  "signed_rc_allowed": true,
  "public_release_allowed": false,
  "blocking_reasons": [
    "installer_smoke_missing",
    "clean_vm_smoke_missing"
  ]
}
```

## Signing Evidence

The Windows release workflow now records:

- `signed`
- `timestamped`
- `signtool_verify_status`
- `signed_rc_allowed`
- `temp_certificate_removed`
- signing evidence JSON per NSIS artifact

Secret values, PFX bytes, and certificate passwords are not written to evidence.

## Workflow Public Release Decision Flow

1. Missing signing secrets produce `windows-release-status.json` with `status=blocked_external_credentials` and `signed_rc_allowed=false`.
2. Successful signing produces `windows-release-status.json` with `signed=true`, `timestamped=true`, `signtool_verify_status=pass`, and `signed_rc_allowed=true`.
3. Signing success still leaves `status=blocked_external_smoke` when clean VM smoke evidence is missing.
4. `scripts/evaluate_windows_release_gate.py` reads signing, installer smoke, operator capabilities, and doctor evidence.
5. Runtime manifest and bundle hash evidence are validated as public gate blockers.
6. Only `artifacts/windows-public-release-gate/windows-public-release-gate.json` can report `public_release_allowed=true`.

## Clean VM Smoke Evidence

`windows_installer_smoke.ps1` now reports:

- `clean_vm_claimed`
- `run_install_used`
- `allow_unsigned_smoke_used`
- `os_version`
- `powershell_version`
- `webview2_status`
- `app_exe_found`
- `install_root_kind`

Public release requires signed smoke with `-RunInstall -CleanVm` and without `-AllowUnsignedSmoke`.

## Public Evidence Closure Addendum

The follow-up branch adds:

- `schemaVersion`, `generated_at_utc`, `decision_source`, and per-input SHA256 provenance to the public gate report.
- Runtime manifest parsing and bundle hash validation as hard public release blockers.
- Smoke-level computer-use hard gates in addition to operator capabilities.
- Real Authenticode timestamp proof in signing evidence.
- Clean smoke and promote workflows with hash continuity and `--fail-on-blocked`.
- Static workflow tests that prevent signing from granting public release permission.

The detailed closure report is `docs/WINDOWS_PUBLIC_RELEASE_EVIDENCE_CLOSURE_REPORT.md`.

## Computer-Use Boundary Confirmation

Windows live computer-use automation remains disabled and fail-closed with `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`. The evaluator hard-fails if Windows computer-use is enabled or if the reason code changes unexpectedly.

No shell passthrough was added.

## Validation Commands

Local verification run on 2026-05-04:

```powershell
uv sync --python 3.11 --extra dev --frozen
uv run ruff check .
uv run python -m pytest -q
uv run python scripts/generate_operator_contract_schemas.py
git diff --exit-code contracts/operator_panel/schemas
corepack pnpm --dir apps/operator-panel install --frozen-lockfile
corepack pnpm --dir apps/operator-panel test
corepack pnpm --dir apps/operator-panel lint
corepack pnpm --dir apps/operator-panel build
cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml
cargo fmt --manifest-path apps/operator-panel/src-tauri/Cargo.toml --check
powershell -NoProfile -ExecutionPolicy Bypass -File apps/operator-panel/scripts/build_bundled_runtime_windows.ps1 -Arch x64 -PythonBin .venv\Scripts\python.exe
powershell -NoProfile -ExecutionPolicy Bypass -File apps/operator-panel/scripts/verify_bundled_runtime_windows.ps1 -RuntimeDir apps/operator-panel/src-tauri/resources/imperaos-runtime
corepack pnpm --dir apps/operator-panel exec tauri build --debug --no-bundle
git diff --check
```

Summary:

- Ruff: pass.
- Python test suite: pass, including `tests/test_windows_release_gate.py` with 29 evaluator tests.
- Schema drift gate: pass.
- Operator panel Vitest suite: 12 files / 43 tests passed.
- Operator panel lint and production build: pass.
- Tauri bridge Cargo tests: 13 tests passed.
- Bundled runtime build and verify: pass, `imperaos_version=0.4.1`.
- Tauri debug no-bundle smoke: pass.
- Workflow YAML parse and PowerShell parser checks: pass.
- Diff whitespace check: pass.

## Remaining Blockers

- Authenticode signing secrets must be configured in the `release-windows` environment.
- Signed NSIS artifact must be timestamped and pass `signtool verify /pa /v`.
- Clean or disposable Windows VM installer smoke must pass.
- `windows-public-release-gate.json` must report `status=pass`, `public_release_allowed=true`, and no blocking reasons before public or enterprise release.

## Rollback Plan

- Revert the evaluator and workflow changes as one release-gate slice if needed.
- Keep the public release gate artifact blocked during rollback.
- Preserve unsigned internal smoke labeling and Windows computer-use fail-closed behavior.
