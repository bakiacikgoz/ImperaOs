# Tauri Application Identity Design

Date: 2026-07-14
Status: Approved
Plan task: Phase 5, Task 5.3

## Objective

Move the Operator Panel desktop application's Tauri, Cargo, process, CLI fallback, environment, and app-data identities to ImperaOS without retaining former-brand compatibility paths. Preserve bundled-runtime packaging as an atomic Phase 6 task.

## Decisions

- Tauri product and window title: `ImperaOS Operator Panel`.
- Tauri bundle identifier: `com.imperaos.operatorpanel`.
- Cargo package and implicit binary target: `imperaos_operator_panel`.
- Rust library target: `imperaos_operator_panel_lib`.
- Cargo description: `ImperaOS Operator Panel`.
- Cargo author identity: `ImperaOS Contributors`.
- External CLI fallback: `imperaos`.
- Bundled Python module fallback: `python -m imperaos`.
- Forward only `IMPERAOS_*` configuration keys plus the existing explicitly allowed provider-secret keys.
- Use only new ImperaOS desktop app-data paths; do not read, migrate, copy, delete, or fall back to former paths.
- Regenerate `apps/operator-panel/src-tauri/Cargo.lock` only for the root package-name change.

## Desktop Data Paths

The CLI working directory resolves as follows:

- macOS: `~/Library/Application Support/com.imperaos.operatorpanel/runtime`
- Windows: `%LOCALAPPDATA%/ImperaOS Operator Panel/runtime`, with `%APPDATA%` as the existing base-directory fallback only
- Linux/Unix: `${XDG_DATA_HOME:-~/.local/share}/imperaos-operator-panel/runtime`

Directory creation remains best-effort and occurs immediately before spawning the CLI. Failure to create the directory preserves the existing process behavior and does not add a former-path fallback.

## Command Resolution

Preserve the existing resolution order:

1. Explicit configured CLI path.
2. Explicit configured bundled Python path.
3. Tauri resource/runtime discovery.
4. External CLI fallback.

Only the identities change: external fallback becomes `imperaos`, while Python-backed execution uses `-m imperaos`. Command timeouts, argument construction, environment clearing, safe platform variables, and provider-secret handling remain unchanged.

## Bundled Runtime Ownership Boundary

The main plan mentions the runtime resource path in both Task 5.3 and Task 6.1. To avoid an intermediate package configuration that points to a directory the build scripts do not yet create, Task 5.3 does not rename `resources/imperaos-runtime`, change the Tauri resource entry, or change the Rust bundled-runtime relative path.

Task 6.1 owns these changes atomically:

- physical `imperaos-runtime` to `imperaos-runtime` directory rename;
- Tauri resource configuration;
- Rust resource resolver and tests;
- wheel glob, module verification, manifest, README, and build/verify scripts.

This boundary is deliberate and must be recorded in the Task 5.3 report.

## Components

- `apps/operator-panel/src-tauri/tauri.conf.json`: product name, window title, and bundle identifier.
- `apps/operator-panel/src-tauri/Cargo.toml`: package, binary, library, description, and author identities.
- `apps/operator-panel/src-tauri/Cargo.lock`: generated root package name.
- `apps/operator-panel/src-tauri/src/main.rs`: call the renamed library target.
- `apps/operator-panel/src-tauri/src/bridge.rs`: CLI/module fallbacks, app-data paths, and identity regression tests.
- Existing Rust/Tauri smoke scripts: verification only unless an exact current identity assertion belongs to Task 5.3 and not Phase 6 packaging.

## Test Design

Follow RED-GREEN-REFACTOR:

1. Add focused Rust tests for external CLI fallback, Python module fallback, allowed environment namespace, and platform-specific app-data path components.
2. Add or run a file-backed metadata contract covering Tauri and Cargo exact identities.
3. Confirm failures are caused by former identities.
4. Apply the minimal configuration and Rust identity changes.
5. Regenerate Cargo lock and confirm only the root package name changes.
6. Run focused Rust tests, full `cargo test`, `cargo check`, Operator Panel TypeScript tests/build where cross-language integration is affected, and Tauri configuration validation.
7. Run launched Tauri smoke if the environment supports GUI/WebView launch; otherwise record the exact environment blocker without a product-code workaround.
8. Scan active Task 5.3 files for former product, bundle, crate, CLI/module, env-prefix, and app-data identities, excluding the explicitly deferred runtime-resource tokens.

## Error and Compatibility Behavior

- Missing external CLI now reports failure for `imperaos`, not the former executable.
- Missing bundled runtime keeps the existing fail-closed error behavior.
- Invalid or blank configured paths keep their existing normalization behavior.
- Former environment-prefix keys are rejected.
- Existing former app-data directories are ignored and left untouched.
- No state migration is performed; canonical `.imperaos` state migration remains owned by Phase 9.

## Acceptance Criteria

- Tauri product/window/bundle identities are exact ImperaOS values.
- Cargo package, implicit binary, library, description, and author identities are ImperaOS.
- External and Python module fallbacks resolve to `imperaos`.
- Only the ImperaOS environment namespace and approved provider secrets are forwarded.
- App-data paths contain only ImperaOS identities and have no former-path fallback.
- Cargo lock changes only its root package identity.
- Rust unit tests and checks pass.
- Launched Tauri smoke passes or has a precisely documented platform/tooling blocker.
- Bundled-runtime physical resource identities remain unchanged and explicitly deferred to Task 6.1.

## Implementation Boundary

The implementation commit subject must be exactly:

`refactor: move desktop application identity to ImperaOS`
