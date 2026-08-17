# Windows Installer Smoke Runbook

Status: release gate runbook

Windows installer smoke is required before any public or enterprise Windows release claim. Unsigned NSIS artifacts may be used only for internal CI smoke and must be clearly labeled as unsigned.

Windows x64 core CLI, operator panel, bundled runtime, and signed release-candidate evidence are supported. Public or enterprise Windows release remains blocked until `artifacts/windows-public-release-gate/windows-public-release-gate.json` reports `status=pass`, `public_release_allowed=true`, and `blocking_reasons=[]`.

## Preconditions

- Windows runner or clean Windows VM.
- Microsoft Edge WebView2 Runtime installed.
- NSIS installer artifact produced by the Windows signed RC workflow.
- Matching installer SHA256 from release evidence.
- Authenticode signature, timestamp proof, and `signtool verify /pa /v` pass for public release candidates.
- `runtime_manifest.txt` and `nsis_file_hashes.json` from the signed RC artifact.
- `-AllowUnsignedSmoke` only for internal smoke; never for public release evidence.

## Internal Unsigned Smoke

```powershell
pwsh apps/operator-panel/scripts/windows_installer_smoke.ps1 `
  -InstallerPath <path-to-nsis-exe> `
  -ExpectedProductName "ImperaOS Operator Panel" `
  -OutputDir artifacts/windows-installer-smoke `
  -AllowUnsignedSmoke
```

Unsigned smoke is internal validation only. It must never be used as public release evidence.

## Signed Public RC Smoke

Run this only with a signed installer on a clean or disposable Windows VM:

```powershell
pwsh apps/operator-panel/scripts/windows_installer_smoke.ps1 `
  -InstallerPath <signed-nsis-exe> `
  -ExpectedInstallerSha256 <signed-rc-installer-sha256> `
  -ExpectedProductName "ImperaOS Operator Panel" `
  -OutputDir artifacts/windows-installer-smoke `
  -RunInstall `
  -CleanVm `
  -LaunchAppSmoke `
  -RunUninstall
```

Do not use `-AllowUnsignedSmoke` for signed public RC smoke. Use `-RunInstall` only on a clean or disposable VM because it installs the NSIS package. `-RunUninstall` is recommended for repeatable workflow evidence when the environment allows it.

## Evidence

The smoke script writes:

- `windows-installer-smoke.json`
- `operator_capabilities.json` when an installed runtime is found
- `doctor_balanced.json` when an installed runtime is found
- `imperaos-version.txt` when an installed runtime is found

The expected report shape includes:

```json
{
  "schemaVersion": "windows-installer-smoke/v1",
  "generated_at_utc": "...",
  "platform": "windows",
  "runner_machine": "github-hosted|local-redacted",
  "github_hosted_runner": true,
  "installer_sha256": "...",
  "expected_installer_sha256": "...",
  "hash_continuity_status": "pass",
  "signed": true,
  "timestamped": true,
  "installer_timestamped": true,
  "signature_status": "Valid",
  "installer_signature_status": "Valid",
  "signtool_verify_status": "pass",
  "clean_vm_claimed": true,
  "run_install_used": true,
  "allow_unsigned_smoke_used": false,
  "launch_app_smoke_used": true,
  "os_version": "...",
  "powershell_version": "...",
  "webview2_status": "present|unknown",
  "app_exe_found": true,
  "app_launch_status": "pass|blocked|fail|not_requested",
  "install_root_kind": "LocalAppData|ProgramFiles|ProgramFilesX86|unknown",
  "install_status": "pass|manual|blocked|fail",
  "bundled_runtime_status": "pass|manual|blocked|fail",
  "operator_capabilities_status": "pass|manual|blocked|fail",
  "doctor_status": "pass|manual|blocked|fail",
  "computer_use_live_enabled": false,
  "computer_use_reason_code": "WINDOWS_COMPUTER_USE_NOT_QUALIFIED",
  "uninstall_status": "pass|not_found|not_run|fail"
}
```

## Public Release Gate

After `windows-release-status.json` and installer smoke evidence exist, evaluate the machine-readable public release gate:

```powershell
uv run python scripts/evaluate_windows_release_gate.py `
  --release-status artifacts/windows-release-evidence/windows-release-status.json `
  --installer-smoke artifacts/windows-installer-smoke/windows-installer-smoke.json `
  --operator-capabilities artifacts/windows-installer-smoke/operator_capabilities.json `
  --doctor artifacts/windows-installer-smoke/doctor_balanced.json `
  --runtime-manifest artifacts/windows-release-evidence/runtime_manifest.txt `
  --bundle-hashes artifacts/windows-release-evidence/nsis_file_hashes.json `
  --output artifacts/windows-public-release-gate/windows-public-release-gate.json `
  --fail-on-blocked
```

Expected internal unsigned smoke result:

```json
{
  "public_release_allowed": false,
  "blocking_reasons": [
    "unsigned_internal_smoke_not_public_release_eligible"
  ]
}
```

## Release Rule

Public or enterprise Windows release remains blocked until:

- NSIS artifact is Authenticode signed and timestamped.
- `signtool verify /pa /v` passes.
- Clean VM installer smoke passes with `-RunInstall`, `-CleanVm`, and app launch smoke.
- Smoke installer SHA256 matches signed RC release evidence.
- Runtime manifest and bundle hash evidence are present and consistent.
- `operator capabilities --json` reports Windows live computer-use disabled with `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`.
- `windows-public-release-gate.json` reports `status=pass`, `public_release_allowed=true`, and no `blocking_reasons`.

## No-Ship Rules

Do not ship public or enterprise Windows artifacts if:

- `windows-public-release-gate.json` is missing.
- `status != pass`.
- `public_release_allowed != true`.
- `blocking_reasons` is non-empty.
- Windows computer-use is enabled in operator capabilities or smoke evidence.
- Installer smoke used `-AllowUnsignedSmoke`.
- `clean_vm_claimed != true`.
- Installer SHA256 mismatches signed RC evidence.
