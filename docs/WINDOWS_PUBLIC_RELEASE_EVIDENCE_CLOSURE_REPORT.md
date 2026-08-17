# Windows Public Release Evidence Closure Report

Date: 2026-05-04
Branch: windows-public-release-evidence-closure
Commit: not committed
Base commit: 436825bf2240a25916b6cc3c30f87dd741a92cb1
Status: PASS for implementation and local verification; public Windows release remains BLOCKED until real signed RC and clean smoke workflow evidence are produced.

## Summary

This change closes the Windows public release evidence chain. Signing now only grants a signed release-candidate decision through `windows-release-status.json`. Public or enterprise Windows release permission is produced only by `artifacts/windows-public-release-gate/windows-public-release-gate.json`.

The evaluator is fail-closed and requires signed/timestamped/verified RC evidence, clean VM installer smoke, installed bundled runtime smoke, operator capabilities, doctor evidence, runtime manifest, bundle hashes, installer hash continuity, and Windows computer-use-disabled evidence.

## Branch Snapshot

```text
branch: windows-public-release-evidence-closure
head: 436825bf2240a25916b6cc3c30f87dd741a92cb1
commit: not committed
```

`git diff --stat` before this report showed 13 changed tracked files plus 3 new files. The new report itself is also part of this change.

## Changed Files

- `.github/workflows/operator-panel-release-windows.yml`
- `.github/workflows/operator-panel-windows-clean-smoke.yml`
- `.github/workflows/operator-panel-promote-windows.yml`
- `apps/operator-panel/scripts/sign_windows_artifacts.ps1`
- `apps/operator-panel/scripts/windows_installer_smoke.ps1`
- `scripts/evaluate_windows_release_gate.py`
- `tests/test_windows_release_gate.py`
- `tests/test_windows_release_workflows_static.py`
- `docs/WINDOWS_INSTALLER_SMOKE.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/RELEASE_GATE_v0.5.md`
- `docs/WINDOWS_RELEASE_HARDENING_REPORT.md`
- `docs/WINDOWS_SIGNED_RC_GATE_REPORT.md`
- `docs/WINDOWS_PUBLIC_RELEASE_EVIDENCE_CLOSURE_REPORT.md`
- `docs/WINDOWS_RELEASE_FINALIZATION_REPORT.md`
- `README.md`
- `DEPLOYMENT_GUIDE.md`
- `QUALIFICATION_MATRIX.md`

## Gate Decision Model

- Signed RC decision: `windows-release-status.json` can report `signed_rc_allowed=true` only after Authenticode signing, timestamp proof, and `signtool verify /pa /v` pass.
- Public release decision: only `windows-public-release-gate.json` can report `public_release_allowed=true`.
- Single source of truth: `artifacts/windows-public-release-gate/windows-public-release-gate.json`.
- If `windows-release-status.json` contains `public_release_allowed=true`, the evaluator ignores it and emits `release_status_public_release_claim_ignored_warning`.

## New/Changed Blocking Reasons

| Reason | Type | Trigger | Public release effect |
|---|---|---|---|
| `runtime_manifest_missing` | blocker | `runtime_manifest.txt` absent | blocked |
| `runtime_manifest_invalid` | blocker | manifest malformed or missing required keys | blocked |
| `runtime_manifest_platform_mismatch` | blocker | manifest platform is not `windows` | blocked |
| `runtime_manifest_arch_mismatch` | blocker | manifest arch is not `x86_64` | blocked |
| `runtime_manifest_python_path_mismatch` | blocker | manifest Python path is not `python/Scripts/python.exe` | blocked |
| `runtime_manifest_python_hash_missing` | blocker | Python executable SHA256 missing/invalid | blocked |
| `bundle_hashes_missing` | blocker | `nsis_file_hashes.json` absent | blocked |
| `bundle_hashes_invalid_json` | blocker | bundle hash evidence malformed | blocked |
| `bundle_hashes_installer_hash_missing` | blocker | release evidence has no installer hash | blocked |
| `bundle_hashes_installer_hash_mismatch` | hard fail | release installer hash not in bundle hash evidence | fail |
| `release_platform_mismatch` | hard fail | release evidence platform is not Windows | fail |
| `installer_smoke_platform_mismatch` | blocker | smoke evidence platform is not Windows | blocked |
| `installer_smoke_timestamp_missing` | blocker | smoke installer is not timestamped | blocked |
| `installer_smoke_signature_not_valid` | blocker | smoke installer signature status is not `Valid` | blocked |
| `installer_smoke_signtool_verify_not_pass` | blocker | smoke installer `signtool verify /pa /v` did not pass | blocked |
| `app_launch_not_pass` | blocker | clean smoke app launch evidence is missing or failed | blocked |
| `smoke_computer_use_enabled` | hard fail | smoke evidence enables Windows computer-use | fail |
| `smoke_computer_use_reason_code_mismatch` | hard fail | smoke reason code is not `WINDOWS_COMPUTER_USE_NOT_QUALIFIED` | fail |
| `webview2_not_detected_for_smoke` | warning | WebView2 not detected by registry/path checks | warning only |
| `release_status_public_release_claim_ignored_warning` | warning | release status claims public permission | ignored warning |

Existing signing, clean smoke, runtime, doctor, capability, and hash mismatch reasons remain active.

## Evidence Artifacts

- `artifacts/windows-release-evidence/windows-release-status.json`
- `artifacts/windows-release-evidence/runtime_manifest.txt`
- `artifacts/windows-release-evidence/nsis_file_hashes.json`
- `artifacts/windows-installer-smoke/windows-installer-smoke.json`
- `artifacts/windows-installer-smoke/operator_capabilities.json`
- `artifacts/windows-installer-smoke/doctor_balanced.json`
- `artifacts/windows-public-release-gate/windows-public-release-gate.json`

## Evaluator Output Examples

Signed RC exists, clean VM smoke missing:

```json
{
  "schemaVersion": "windows-public-release-gate/v1",
  "status": "blocked",
  "signed_rc_allowed": true,
  "public_release_allowed": false,
  "blocking_reasons": [
    "installer_smoke_missing",
    "clean_vm_smoke_missing"
  ]
}
```

All required synthetic evidence present:

```json
{
  "schemaVersion": "windows-public-release-gate/v1",
  "status": "pass",
  "signed_rc_allowed": true,
  "public_release_allowed": true,
  "blocking_reasons": []
}
```

Blocked CLI behavior:

```text
--fail-on-blocked exit code: 2
```

## Workflow Public Release Decision Flow

1. `operator-panel-release-windows.yml` builds and signs the NSIS artifact when signing secrets exist.
2. Signing evidence records real Authenticode state, timestamp proof, `signtool` status, certificate metadata presence, artifact SHA256, and `secret_material_written=false`.
3. The release workflow writes `windows-release-status.json` with `signed_rc_allowed`; it does not write `public_release_allowed`.
4. `operator-panel-windows-clean-smoke.yml` downloads the signed RC artifact by run id, verifies installer SHA256, and runs smoke with `-RunInstall -CleanVm -LaunchAppSmoke -RunUninstall` under the `clean-smoke-windows` environment.
5. `operator-panel-promote-windows.yml` downloads signed RC and clean smoke evidence, verifies hash continuity, and runs the evaluator with `--fail-on-blocked` under the `promote-windows` environment.
6. Gate evidence is uploaded as `windows-public-release-gate`.
7. There is no automatic public publish step in this change.

## Security Confirmation

- Windows live computer-use remains disabled and fail-closed with `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`.
- No Windows desktop/browser automation adapter was added.
- No shell passthrough was added.
- PFX bytes, certificate password, base64 secrets, and raw signing output are not written to evidence.
- Temporary PFX removal remains verified in release workflow status.
- `-AllowUnsignedSmoke` is blocked from the clean smoke workflow and remains public-release-ineligible in the evaluator.

## Validation Commands and Results

```text
uv sync --python 3.11 --extra dev --frozen
result: pass

uv run ruff check .
result: pass

uv run python -m pytest -q tests/test_windows_release_gate.py
result: pass, 29 tests

uv run python -m pytest -q
result: pass, expected skipped tests shown by pytest

uv run python scripts/generate_operator_contract_schemas.py
git diff --exit-code contracts/operator_panel/schemas
result: pass, no schema diff

corepack pnpm --dir apps/operator-panel install --frozen-lockfile
result: pass; pnpm reported ignored esbuild build scripts per local approval policy

corepack pnpm --dir apps/operator-panel test
result: pass, 12 files / 43 tests

corepack pnpm --dir apps/operator-panel lint
result: pass

corepack pnpm --dir apps/operator-panel build
result: pass

cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml
result: pass, 13 tests

cargo fmt --manifest-path apps/operator-panel/src-tauri/Cargo.toml --check
result: pass

powershell -NoProfile -ExecutionPolicy Bypass -File apps/operator-panel/scripts/build_bundled_runtime_windows.ps1 -Arch x64 -PythonBin .venv\Scripts\python.exe
result: pass

powershell -NoProfile -ExecutionPolicy Bypass -File apps/operator-panel/scripts/verify_bundled_runtime_windows.ps1 -RuntimeDir apps/operator-panel/src-tauri/resources/imperaos-runtime
result: pass, manifest=pass, imperaos_version=0.4.1

corepack pnpm --dir apps/operator-panel exec tauri build --debug --no-bundle
result: pass, produced apps/operator-panel/src-tauri/target/debug/imperaos_operator_panel.exe

PowerShell parser checks for signing and smoke scripts
result: pass

Workflow YAML parse checks
result: pass

Local synthetic evaluator pass and blocked smoke
result: pass; missing smoke reasons are exactly installer_smoke_missing and clean_vm_smoke_missing

git diff --check
result: pass
```

## Workflow Runs

- Windows CI: not run in GitHub during this local implementation pass.
- Signed RC: not run in GitHub during this local implementation pass.
- Clean smoke: not run in GitHub during this local implementation pass.
- Promote gate: not run in GitHub during this local implementation pass.

## Remaining Blockers

- Configure real Authenticode signing secrets in the `release-windows` environment.
- Run the Windows signed RC workflow and retain the signed RC artifact SHA256.
- Run the clean Windows smoke workflow on the signed installer.
- Run the promote workflow with `--fail-on-blocked`.
- Ship public/enterprise Windows artifacts only after `windows-public-release-gate.json` reports `status=pass`, `public_release_allowed=true`, and `blocking_reasons=[]`.

## Rollback Plan

1. Disable or revert the clean smoke and promote workflows.
2. Keep `windows-release-status.json` scoped to signed RC status only.
3. Keep public release blocked by default.
4. Preserve Windows computer-use fail-closed behavior.
5. Revert evaluator hardening as one slice only if the release gate artifact remains blocked during rollback.
