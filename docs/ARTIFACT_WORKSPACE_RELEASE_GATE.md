# Artifact Workspace Release Gate

Release evidence is valid only for one immutable, clean Git candidate. Commit all intended files, confirm no staged/untracked changes, and run from the repository root:

```powershell
.\.venv\Scripts\python.exe scripts/run_artifact_workspace_release_gate.py --gate workspace-release --profile enterprise --json
```

The runner executes contract, storage, RPC, security, UI, E2E, export, license, and aggregate workspace-release gates. It fails closed on a dirty tree, zero discovered tests, command failure, missing report, candidate SHA drift, unresolved no-ship item, or an untrusted editor adapter. Spreadsheet and canvas pass with either verified commercial entitlement or the reviewed bundled local fallback; absence of both is a no-ship condition.

Required outputs under `artifacts/artifact-workspace-release/` are `contract-report.json`, `storage-integrity-report.json`, `rpc-performance-report.json`, `security-report.json`, `UI_TEST_REPORT.md`, `export-report.json`, `license-report.json`, `release-readiness.json`, `RELEASE_READINESS.md`, and `NO_SHIP_REGISTER.md`. Every report must bind the same candidate SHA. Command output is summarized and hashed; reports must not contain secrets, content, prompts, absolute customer paths, license material, or reusable tickets.

The enterprise default is `artifact_workspace_off`: `artifact_workspace.enabled=false` and every per-kind/export flag false. `artifact_workspace_core` enables all seven governed editors using built-in or bundled fallback adapters. `artifact_workspace_full` uses the same artifact contracts while preferring verified commercial spreadsheet/canvas adapters. Explicit environment flags may only narrow a profile. `assistant_ui_runtime.enabled` and `ai_sdk_tauri_transport.enabled` are separately reversible.

CI runs the release runner on Windows and macOS. A local platform result does not substitute for the other platform job. Promotion requires green lint, Python, frontend tests/build/E2E, full Rust tests, CSP/no-network probes, i18n/bridge parity, performance bounds, backup/recovery rehearsal, and an empty `NO_SHIP_REGISTER.md`. On any regression, disable the global gate, preserve data and evidence, and follow the recovery runbook; do not downgrade schemas or delete revisions.
