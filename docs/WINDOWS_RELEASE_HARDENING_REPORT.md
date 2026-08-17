# Windows Release Hardening Report

Date: 2026-05-04
Branch: windows-release-hardening
Commit: not committed yet
Status: PARTIAL

This report covers the Windows release hardening work applied after the initial Windows support baseline. The result is not a public Windows release. The correct claim is:

> Windows core/operator panel/bundled runtime line now supports signed release-candidate evidence. Public/enterprise Windows release remains blocked until Authenticode signing, timestamp verification, clean VM smoke, installed runtime/capabilities/doctor evidence, runtime manifest evidence, bundle hash evidence, and `windows-public-release-gate.json` all pass.

## 1. Implemented Changes

- Added deterministic operator panel schema drift testing.
- Regenerated checked-in operator panel JSON schemas.
- Added JSON schema validation for `operator capabilities --json`.
- Expanded UI capability validation to cover enterprise command flags.
- Added computer-use capability helpers and UI disabled-state gating.
- Hardened Windows bundled runtime manifest with SHA256 and git evidence.
- Added standalone Windows bundled runtime verify script.
- Changed Tauri resources config to include the runtime directory instead of a shallow glob.
- Hardened Tauri bridge resolution so handshake can use Tauri resource dir before current-exe fallback.
- Added Windows CI evidence artifacts.
- Split unsigned internal smoke from signed release-candidate artifacts in the Windows release workflow.
- Added Windows signing script, bootstrap script, installer smoke script, smoke runbook, and Windows computer-use qualification RFC.
- Added clean smoke and promote workflow gates so public release permission is produced only by `artifacts/windows-public-release-gate/windows-public-release-gate.json`.

## 2. Contract/Schema Closure

`scripts/generate_operator_contract_schemas.py` now runs from the repo root and writes canonical sorted JSON. `tests/test_operator_schema_generation.py` compares each generated schema against the checked-in schema files.

`operator_capabilities.schema.json` includes:

- `reasonCode`
- `summary`

## 3. Bundled Runtime Evidence

`apps/operator-panel/scripts/build_bundled_runtime_windows.ps1` now records:

- `platform`
- `arch`
- `python`
- `imperaos_version`
- `created_at_utc`
- `source_wheel`
- `source_wheel_sha256`
- `python_exe_sha256`
- `uv_lock_sha256`
- `git_sha`

`apps/operator-panel/scripts/verify_bundled_runtime_windows.ps1` checks the manifest, Python entrypoint, hash format, Python executable hash, and `python.exe -m imperaos --version`.

Generated runtime trees remain ignored by git.

## 4. Tauri Bridge Evidence

The bridge keeps shell-free process spawning. `bridge_handshake` receives `tauri::AppHandle` and resolves bundled Python using Tauri's resource directory when available. Existing current-exe based lookup remains only as fallback.

Cargo tests cover:

- platform-specific bundled Python relative path
- resource-dir runtime detection
- CLI path precedence over resource runtime
- resource runtime fallback when CLI path is absent
- platform-specific PATH separator

## 5. CI/Release Workflow Evidence

Windows CI now uses:

- `windows-2022` blocking lane
- `windows-2025` canary lane
- `uv sync --python 3.11 --extra dev --frozen`
- `pnpm install --dir apps/operator-panel --frozen-lockfile`
- schema drift gate
- uploaded `artifacts/windows-ci-evidence/**`

Evidence files include:

- `operator_capabilities.json`
- `doctor_balanced.json`
- `runtime_manifest.txt`
- `runtime_verify.txt`
- `bundle_file_hashes.json`
- `tauri_build_smoke.txt`

## 6. Signing Status

`operator-panel-release-windows.yml` now writes `windows-release-status.json`.

Missing signing secrets produce:

```json
{
  "platform": "windows",
  "artifact_type": "nsis",
  "signed": false,
  "status": "blocked_external_credentials",
  "reason": "missing_windows_signing_secret"
}
```

When signing secrets exist, the workflow decodes the PFX into runner temp storage, signs NSIS artifacts through `sign_windows_artifacts.ps1`, runs `signtool verify /pa /v`, verifies Authenticode timestamp proof with `Get-AuthenticodeSignature`, removes the temp PFX, and marks only `signed_rc_allowed=true`. The workflow no longer writes a public release decision into `windows-release-status.json`; only `artifacts/windows-public-release-gate/windows-public-release-gate.json` owns `public_release_allowed`.

## 7. Clean VM / Installer Smoke Status

`docs/WINDOWS_INSTALLER_SMOKE.md` and `apps/operator-panel/scripts/windows_installer_smoke.ps1` define the repeatable smoke process.

Local clean VM smoke has not been run in this branch. This remains a release blocker. The repeatable route is:

1. Run Windows CI.
2. Run the signed RC workflow.
3. Confirm `signed_rc_allowed=true` and record the installer SHA256.
4. Run `.github/workflows/operator-panel-windows-clean-smoke.yml` with the signed RC run id and installer SHA256.
5. Run `.github/workflows/operator-panel-promote-windows.yml` with signed RC, clean smoke, and expected installer SHA256 inputs.
6. Ship only if `windows-public-release-gate.json` reports `status=pass`, `public_release_allowed=true`, and no blocking reasons.

## 8. Windows Computer-Use Boundary Confirmation

Windows live computer-use automation remains disabled and fail-closed with `WINDOWS_COMPUTER_USE_NOT_QUALIFIED` until a signed Windows qualification report explicitly enables that surface.

No shell passthrough was added.

## 9. Tests Run

Local verification on 2026-05-04:

```powershell
uv run ruff check .
uv run python -m pytest -q
uv run python scripts/generate_operator_contract_schemas.py
git diff --exit-code contracts/operator_panel/schemas
corepack pnpm --dir apps/operator-panel test
corepack pnpm --dir apps/operator-panel lint
corepack pnpm --dir apps/operator-panel build
cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml
cargo fmt --manifest-path apps/operator-panel/src-tauri/Cargo.toml --check
powershell -NoProfile -ExecutionPolicy Bypass -File apps/operator-panel/scripts/verify_bundled_runtime_windows.ps1 -RuntimeDir apps/operator-panel/src-tauri/resources/imperaos-runtime
corepack pnpm --dir apps/operator-panel exec tauri build --debug --no-bundle
git diff --check
```

Summary:

- Ruff: pass.
- Python test suite: pass, with the expected skipped tests shown by pytest.
- Operator panel Vitest suite: 12 files / 43 tests passed.
- Operator panel lint and production build: pass.
- Tauri bridge Cargo tests: 13 tests passed.
- Bundled runtime verify: manifest pass, `imperaos_version=0.4.1`.
- Tauri debug no-bundle smoke: pass, produced `apps/operator-panel/src-tauri/target/debug/imperaos_operator_panel.exe`.
- Diff whitespace check: pass.

## 10. Remaining Blockers

- Authenticode signing certificate secret and password must be configured in the `release-windows` environment.
- Clean Windows VM installer smoke must pass.
- Public GitHub Release publishing remains intentionally absent from this workflow until signing and clean VM evidence are complete.
- Windows live computer-use qualification RFC is draft only.

## 11. Rollback Notes

- UI capability gating can be reverted independently from schema drift closure.
- Bridge resource-dir resolver can fall back to the prior current-exe lookup by reverting the bridge resolver changes.
- Signing workflow can stay blocked while preserving unsigned internal smoke artifact upload.
- Windows computer-use should not be enabled as part of rollback.
