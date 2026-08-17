# Task 5.3 — Tauri/Cargo Application Identity Report

Date: 2026-07-14
Base: `650c4b260f997dba716b25ed3c1dff89c50d32ba`
Implementation: `79a17be67e0aec8e5564721888e4cc88754e86b4`
Implementation subject: `refactor: move desktop application identity to ImperaOS`

## Scope

The implementation commit changes exactly the six approved files:

- `apps/operator-panel/src-tauri/tauri.conf.json`
- `apps/operator-panel/src-tauri/Cargo.toml`
- `apps/operator-panel/src-tauri/Cargo.lock`
- `apps/operator-panel/src-tauri/src/main.rs`
- `apps/operator-panel/src-tauri/src/bridge.rs`
- `apps/operator-panel/src-tauri/tests/desktop_identity.rs`

No dependency, dependency version, frontend package metadata, build/verify script,
installer, workflow, signed artifact, or immutable historical file changed.

## RED evidence

Tests were changed or added before production/configuration edits.

1. `cargo test ... desktop_metadata_uses_imperaos_identity -- --nocapture`
   failed on the current Cargo package identity:
   `assertion failed: cargo.contains("name = \"imperaos_operator_panel\"")`.
2. `cargo test ... resolve_cli_command_external_fallback_uses_imperaos -- --nocapture`
   failed with `left: "imperaos"`, `right: "imperaos"`.
3. `cargo test ... desktop_runtime_workdirs_use_only_imperaos_identity -- --nocapture`
   failed to compile with `E0425` for the absent
   `macos_runtime_workdir`, `windows_runtime_workdir`, and
   `unix_runtime_workdir` helpers.

These are three distinct missing-identity causes rather than setup or syntax
failures.

## Implemented identity

- Tauri product/window title: `ImperaOS Operator Panel`.
- Tauri bundle identifier: `com.imperaos.operatorpanel`.
- Cargo package and implicit binary: `imperaos_operator_panel`.
- Rust library: `imperaos_operator_panel_lib`.
- Cargo description/author: `ImperaOS Operator Panel` /
  `ImperaOS Contributors`.
- External CLI fallback: `imperaos`.
- Python-backed fallback: `-m imperaos`.
- App-data runtime suffixes:
  - macOS: `com.imperaos.operatorpanel/runtime` below Application Support;
  - Windows: `ImperaOS Operator Panel/runtime` below `LOCALAPPDATA`, retaining
    only the existing `APPDATA` base-directory fallback;
  - Unix: `imperaos-operator-panel/runtime` below `XDG_DATA_HOME` or
    `~/.local/share`.
- The environment allowlist continues to accept only `IMPERAOS_*` plus
  `OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, and
  `COMPANY_LLM_API_KEY`.
- No former app-data probe, migration, copy, deletion, or fallback was added.

## Cargo lock and target proof

`cargo check --manifest-path apps/operator-panel/src-tauri/Cargo.toml` regenerated
the lock after the manifest rename. The lock diff contains only the root package
block moving alphabetically while its name changes from the former root package
name to `imperaos_operator_panel`; its version and complete dependency list are
unchanged. No registry version or checksum changed.

Fresh `cargo metadata --locked --no-deps` evidence:

- package: `imperaos_operator_panel`;
- targets: `imperaos_operator_panel_lib`, `imperaos_operator_panel`,
  `desktop_identity`, and `build-script-build`.

`cargo build --locked --bin imperaos_operator_panel ...` exited 0. The resulting
Windows debug binary existed at
`apps/operator-panel/src-tauri/target/debug/imperaos_operator_panel.exe`
(14,075,392 bytes in this run).

## GREEN and full verification

Focused GREEN runs all exited 0:

- `desktop_metadata_uses_imperaos_identity`: 1 passed;
- `resolve_cli_command_external_fallback_uses_imperaos`: 1 passed;
- `desktop_runtime_workdirs_use_only_imperaos_identity`: 1 passed;
- `cli_env_allowlist_uses_only_canonical_project_prefix`: 1 passed.

Full gates:

- `cargo fmt ... -- --check`: pass. The official `rustfmt` component had not
  been installed locally; it was installed through `rustup component add
  rustfmt`, after which both formatting and the check exited 0.
- `cargo test --locked ...`: 29 Rust unit tests plus 1 integration test passed,
  0 failed.
- `cargo check --locked --all-targets ...`: pass.
- `cargo build --locked --bin imperaos_operator_panel ...`: pass.
- `corepack pnpm@10.29.2 --dir apps/operator-panel test`: 66 files and 211
  tests passed, 0 failed.
- `corepack pnpm@10.29.2 --dir apps/operator-panel build`: pass; Vite emitted
  only the existing large-chunk advisory.
- `git diff --check`: pass before the implementation commit.

## Tauri smoke outcome

The standard contract command and the managed-permission launched command were
both attempted:

- `corepack pnpm@10.29.2 --dir apps/operator-panel tauri:smoke`
- `OPERATOR_PANEL_TAURI_LAUNCH_TIMEOUT_MS=20000` with
  `corepack pnpm@10.29.2 --dir apps/operator-panel tauri:smoke:launch`

Both stopped before application execution in the pre-existing smoke harness at
`scripts/tauri-launched-smoke.ts:13`. On Windows,
`new URL(import.meta.url).pathname` retained the leading drive slash and URL
encoding, after which `path.resolve` produced a path beginning
`C:\\C:\\Users\\...\\HER%C5%9EEY...`. The exact failure was `ENOENT` while
opening that derived `package.json`. An ASCII `subst` probe reproduced the same
class of error as `C:\\R:\\apps\\operator-panel\\package.json`, confirming the
failure is the Windows URL-path bootstrap and not the product identity changes.

For contract evidence only, the unchanged harness source was streamed through
the existing `tsx` runtime with that single bootstrap expression replaced in
memory by the correctly resolved script directory. This wrote the normal smoke
report and exited 0: Tauri config, Tauri scripts, bridge handlers, runtime truth
fixture, control-plane snapshot fixture, no-preview-fallback, and Rust bridge
checks all passed. Its overall result was `conditional` only because GUI launch
was not requested in that verification-only run.

The real GUI/WebView process was therefore not launched. No product-code or
tracked smoke-script workaround was added; the exact harness blocker is recorded
for later repair outside Task 5.3.

## Active/deferred scans

The targeted active scan across the six Task 5.3 files returned no former
desktop product, bundle, crate, executable fallback, Python module fallback, or
app-data identity matches.

The deliberate Task 6.1 scan still found exactly five references:

- one Tauri resource entry for `resources/imperaos-runtime/`;
- two platform branches of the Rust bundled Python relative path;
- two matching existing Rust test expectations.

Those five references, the physical runtime directory, wheel glob, manifest,
README, and build/verify scripts remain atomically owned by Task 6.1. They were
not changed here.

## Committed-head inventory

Inventory was run against implementation commit
`79a17be67e0aec8e5564721888e4cc88754e86b4` with MinGit on `PATH`:

```powershell
.\.venv\Scripts\python.exe scripts/run_brand_consistency_gate.py --mode inventory --repo-root . --output-root artifacts/brand-consistency/task-5.3 --json
```

Result:

- scanned tracked files: 1,535;
- legacy content findings: 927;
- legacy path findings: 3;
- binary metadata findings: 19;
- built artifact findings: 0;
- total findings: 949;
- status: expected `fail`, because later rename phases still own runtime
  packaging, installers, CI, documentation, automation, and historical
  boundaries.

The last published Task 5.2 implementation inventory was 968 total findings;
the current committed-head total is 19 lower while the tracked scan scope is
four files larger. This comparison is informational rather than a strict
task-only delta because the intervening Task 5.2 report and Task 5.3 design/plan
documents changed the tracked scan scope.

## Result

Task 5.3's desktop metadata, Rust targets, command fallbacks, environment
boundary, and app-data paths are implemented and verified. The only unmet
runtime observation is the launched GUI smoke, precisely blocked before product
execution by the existing Windows URL-path bug in the smoke harness. Bundled
runtime resource identities remain intentionally deferred to Task 6.1.
