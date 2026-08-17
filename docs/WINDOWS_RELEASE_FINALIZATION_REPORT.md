# Windows Release Finalization Report

Date: 2026-05-04
Branch: main, integrated from windows-public-release-evidence-closure
Commit: 743bb6ff1bbd0117195fe253f7906ad0cce5c8ad
Status: PASS for implementation, local verification, and GitHub CI; BLOCKED for real public release

## Summary

The Windows signed gate implementation is locally finalized and verified. The code now keeps signed release-candidate status separate from public release permission, strengthens clean smoke evidence, and requires the promote gate to be the only source of `public_release_allowed=true`.

The implementation branch was pushed, verified through GitHub Actions, then fast-forwarded into `origin/main` at `743bb6ff1bbd0117195fe253f7906ad0cce5c8ad`.

No public or enterprise Windows artifact was published. Real signed RC, clean smoke, and promote workflow runs were not started because they require protected GitHub environment approval and real signing secrets.

## Source Control

- source branch: `windows-public-release-evidence-closure`
- main branch: `origin/main`
- base commit: `436825bf2240a25916b6cc3c30f87dd741a92cb1`
- implementation commit: `1e51e8f22789614e52e480d067586c874d0625ff`
- report metadata commit: `9b29831588566cbb9b1d933b46d7f4309b43a8df`
- CI fix commit: `743bb6ff1bbd0117195fe253f7906ad0cce5c8ad`
- PR: https://github.com/bakiacikgoz/ImperaOS/pull/2
- tag/ref: no RC tag created

## Source Control Snapshot

```text
git branch --show-current
main

git rev-parse HEAD
743bb6ff1bbd0117195fe253f7906ad0cce5c8ad

git status --short
<clean before this report refresh>

git diff --stat
<empty before this report refresh>

git diff --check
result: pass
```

## Changed Files

```text
.github/workflows/operator-panel-promote-windows.yml
.github/workflows/operator-panel-release-windows.yml
.github/workflows/operator-panel-windows-clean-smoke.yml
DEPLOYMENT_GUIDE.md
QUALIFICATION_MATRIX.md
README.md
apps/operator-panel/scripts/sign_windows_artifacts.ps1
apps/operator-panel/scripts/windows_installer_smoke.ps1
apps/operator-panel/src-tauri/src/bridge.rs
docs/RELEASE_CHECKLIST.md
docs/RELEASE_GATE_v0.5.md
docs/WINDOWS_INSTALLER_SMOKE.md
docs/WINDOWS_PUBLIC_RELEASE_EVIDENCE_CLOSURE_REPORT.md
docs/WINDOWS_RELEASE_FINALIZATION_REPORT.md
docs/WINDOWS_RELEASE_HARDENING_REPORT.md
docs/WINDOWS_SIGNED_RC_GATE_REPORT.md
scripts/evaluate_windows_release_gate.py
tests/test_windows_release_gate.py
tests/test_windows_release_workflows_static.py
```

## Workflow Runs

- CI run id: `25324363368`, result: success
- Operator Panel CI run id: `25324363304`, result: success
- Windows CI run id: `25324363315`, result: success
- Signed RC run id: BLOCKED, requires explicit operator approval and `release-windows` secrets
- Clean smoke run id: BLOCKED, requires signed RC run id and installer SHA256
- Promote gate run id: BLOCKED, requires signed RC and clean smoke evidence

## Signed RC Evidence Model

`operator-panel-release-windows.yml` now writes `windows-release-status.json` with signed-RC-only fields:

- `schemaVersion=windows-release-status/v1`
- `platform=windows`
- `artifact_type=nsis`
- `artifact_kind=nsis`
- `signed`
- `timestamped`
- `signtool_verify_status`
- `signed_rc_allowed`
- `artifact_sha256`
- `installer_sha256`
- `secret_material_written=false`
- `temp_certificate_removed`

The release workflow does not write `public_release_allowed`.

## Clean Windows Smoke Evidence Model

`windows_installer_smoke.ps1` and `operator-panel-windows-clean-smoke.yml` now require or emit:

- environment: `clean-smoke-windows`
- `-ExpectedInstallerSha256`
- `-RunInstall`
- `-CleanVm`
- `-LaunchAppSmoke`
- `-RunUninstall`
- no `-AllowUnsignedSmoke`
- installer SHA256 continuity
- `signature_status` and `installer_signature_status`
- `timestamped` and `installer_timestamped`
- `signtool_verify_status`
- `app_launch_status`
- bundled runtime, operator capabilities, and doctor statuses
- Windows computer-use disabled evidence

## Public Release Gate

`operator-panel-promote-windows.yml` runs under `promote-windows`, verifies signed RC and smoke hash continuity, then runs:

```text
uv run python scripts/evaluate_windows_release_gate.py ... --fail-on-blocked
```

The only public release decision artifact is:

```text
artifacts/windows-public-release-gate/windows-public-release-gate.json
```

Public release remains BLOCKED unless that file reports:

```json
{
  "status": "pass",
  "signed_rc_allowed": true,
  "public_release_allowed": true,
  "blocking_reasons": []
}
```

## Computer-Use Boundary

- enabled: `false`
- reasonCode: `WINDOWS_COMPUTER_USE_NOT_QUALIFIED`
- expected: Windows live computer-use remains disabled until a separate signed Windows qualification report explicitly enables it.

## New Finalization Checks

- Release workflow status JSON includes signed-RC schema fields and sanitized secret hygiene fields.
- Clean smoke workflow is protected by `clean-smoke-windows`.
- Promote workflow is protected by `promote-windows`.
- Smoke evidence includes app launch and signtool verify gate inputs.
- Evaluator blocks `installer_smoke_signtool_verify_not_pass`.
- Evaluator blocks `app_launch_not_pass`.
- Static workflow tests verify public release cannot be granted from the signing workflow.

## Validation Results

```text
uv sync --python 3.11 --extra dev --frozen
result: pass

uv run ruff check .
result: pass

uv run python -m pytest -q tests/test_windows_release_gate.py tests/test_windows_release_workflows_static.py
result: pass, 36 tests

uv run python -m pytest -q
result: pass, expected skipped tests shown by pytest

uv run python scripts/generate_operator_contract_schemas.py
git diff --exit-code contracts/operator_panel/schemas
result: pass

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
result: pass

PowerShell parser checks
result: pass

Workflow YAML parse checks
result: pass

Source-control secret hygiene scan
result: pass

Local synthetic evaluator pass/blocked smoke
result: pass; blocked smoke exits 2 with --fail-on-blocked
```

## Remaining Blockers

- Real Authenticode signing secrets must be configured in the protected `release-windows` environment.
- A release operator must explicitly approve running the signed RC workflow with real signing material.
- The signed RC workflow must produce a signed and timestamped NSIS installer plus release evidence.
- The clean smoke workflow must run against the signed installer and pass.
- The promote workflow must run with signed RC and clean smoke run ids and produce a passing public gate.
- Public/enterprise release publish still requires separate human approval after gate PASS.

## Human Approval Required Before Publish

Signed RC workflow approval phrase:

```text
ONAYLIYORUM: Windows signed RC workflow gerçek signing certificate ile çalıştırılsın; public release publish yapılmasın.
```

Public publish approval phrase:

```text
ONAYLIYORUM: Gate artifact status=pass olduğu doğrulanan Windows installer public/enterprise release kanalına yayınlansın.
```

## Rollback Plan

1. Do not publish public Windows artifacts.
2. Keep `windows-public-release-gate.json` missing or non-pass as release-blocking.
3. Disable clean smoke or promote workflows if a workflow bug appears.
4. Preserve `public_release_allowed=false` by default.
5. Preserve Windows computer-use disabled behavior.
6. Rotate signing secrets only through the human release operator if a secret exposure is suspected.
