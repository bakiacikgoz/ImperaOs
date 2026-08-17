# Tauri Application Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Operator Panel desktop application, Rust targets, CLI fallbacks, environment boundary, and desktop work directories to ImperaOS.

**Architecture:** Change Tauri/Cargo identities and centralize platform work-directory suffixes in pure Rust helpers that can be tested on every host. Preserve command-resolution order and defer the physical bundled-runtime resource rename to Task 6.1 so packaging never points at a directory its build scripts do not create.

**Tech Stack:** Tauri 2.10, Rust 2021, Cargo, serde/serde_json, Tokio, TypeScript smoke harness, pnpm 10.29.2.

## Global Constraints

- Tauri product/window title: `ImperaOS Operator Panel`.
- Tauri identifier: `com.imperaos.operatorpanel`.
- Cargo package/implicit binary: `imperaos_operator_panel`.
- Rust library: `imperaos_operator_panel_lib`.
- Cargo description/author: `ImperaOS Operator Panel` / `ImperaOS Contributors`.
- External CLI fallback and Python module fallback: `imperaos`.
- Only `IMPERAOS_*` plus the existing explicit provider-secret allowlist may be forwarded.
- Former desktop app-data paths are ignored; do not migrate, copy, delete, or fall back to them.
- Keep `resources/imperaos-runtime/`, the Tauri resource entry, Rust bundled-runtime relative path, and their tests unchanged until Task 6.1.
- Cargo lock may change only the root package name.
- Do not change dependencies, versions, frontend package metadata, build/verify scripts, installer, CI, history, signed, or immutable files.
- Implementation commit subject: `refactor: move desktop application identity to ImperaOS`.

---

### Task 1: Move desktop metadata and runtime identity

**Files:**

- Modify: `apps/operator-panel/src-tauri/tauri.conf.json`
- Modify: `apps/operator-panel/src-tauri/Cargo.toml`
- Modify: `apps/operator-panel/src-tauri/Cargo.lock`
- Modify: `apps/operator-panel/src-tauri/src/main.rs`
- Modify: `apps/operator-panel/src-tauri/src/bridge.rs`
- Create: `apps/operator-panel/src-tauri/tests/desktop_identity.rs`

**Interfaces:**

- Preserves: `resolve_cli_command(config: &BridgeConfig, resource_dir: Option<&Path>) -> Result<ResolvedCli, BridgeError>` and `default_cli_workdir() -> Option<PathBuf>`.
- Produces: pure path helpers `macos_runtime_workdir(base: &Path) -> PathBuf`, `windows_runtime_workdir(base: &Path) -> PathBuf`, and `unix_runtime_workdir(base: &Path) -> PathBuf`.
- Preserves: existing bundled-runtime resource names and physical paths until Task 6.1.

- [ ] **Step 1: Add a failing file-backed desktop metadata contract**

Create `apps/operator-panel/src-tauri/tests/desktop_identity.rs`:

```rust
use std::{fs, path::PathBuf};

fn manifest_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

#[test]
fn desktop_metadata_uses_imperaos_identity() {
    let root = manifest_root();
    let cargo = fs::read_to_string(root.join("Cargo.toml")).expect("Cargo.toml");
    let tauri: serde_json::Value = serde_json::from_str(
        &fs::read_to_string(root.join("tauri.conf.json")).expect("tauri.conf.json"),
    )
    .expect("valid tauri config");

    assert!(cargo.contains("name = \"imperaos_operator_panel\""));
    assert!(cargo.contains("name = \"imperaos_operator_panel_lib\""));
    assert!(cargo.contains("description = \"ImperaOS Operator Panel\""));
    assert!(cargo.contains("authors = [\"ImperaOS Contributors\"]"));
    assert_eq!(tauri["productName"], "ImperaOS Operator Panel");
    assert_eq!(tauri["identifier"], "com.imperaos.operatorpanel");
    assert_eq!(tauri["app"]["windows"][0]["title"], "ImperaOS Operator Panel");
}
```

- [ ] **Step 2: Update/add Rust behavioral expectations before production changes**

In the existing `#[cfg(test)]` module in `src/bridge.rs`:

- update every Python-backed `ResolvedCli.prefix_args` expectation to `vec!["-m", "imperaos"]`;
- update explicit/fake CLI examples from former product executables to `imperaos`/`imperaos-custom`;
- add an external-fallback test:

```rust
#[test]
fn resolve_cli_command_external_fallback_uses_imperaos() {
    let config = BridgeConfig {
        mode: Some("external".to_string()),
        cli_path: None,
        bundled_python_path: None,
        profile: Some("balanced".to_string()),
        root_dir: None,
        env: HashMap::new(),
        timeout_ms: None,
    };

    let resolved = resolve_cli_command(&config, None).expect("external fallback");
    assert_eq!(resolved.mode, CoreMode::External);
    assert_eq!(resolved.program, "imperaos");
    assert!(resolved.prefix_args.is_empty());
}
```

Add pure path-helper expectations:

```rust
#[test]
fn desktop_runtime_workdirs_use_only_imperaos_identity() {
    let base = Path::new("data-root");

    assert_eq!(
        macos_runtime_workdir(base),
        base.join("com.imperaos.operatorpanel").join("runtime")
    );
    assert_eq!(
        windows_runtime_workdir(base),
        base.join("ImperaOS Operator Panel").join("runtime")
    );
    assert_eq!(
        unix_runtime_workdir(base),
        base.join("imperaos-operator-panel").join("runtime")
    );
}
```

Keep and rerun `cli_env_allowlist_uses_only_canonical_project_prefix`; it already asserts `IMPERAOS_*` acceptance and rejects constructed former prefixes.

- [ ] **Step 3: Run focused tests and verify RED**

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path apps/operator-panel/src-tauri/Cargo.toml desktop_metadata_uses_imperaos_identity -- --nocapture
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path apps/operator-panel/src-tauri/Cargo.toml resolve_cli_command_external_fallback_uses_imperaos -- --nocapture
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path apps/operator-panel/src-tauri/Cargo.toml desktop_runtime_workdirs_use_only_imperaos_identity -- --nocapture
```

Expected:

- metadata test FAILS on current Tauri/Cargo identities;
- external fallback test FAILS on the former executable;
- path-helper test fails to compile because the approved helpers do not exist yet.

Record these as three distinct RED causes before editing production/configuration code.

- [ ] **Step 4: Apply Tauri and Cargo identities**

Set `apps/operator-panel/src-tauri/tauri.conf.json` values:

```json
"productName": "ImperaOS Operator Panel",
"identifier": "com.imperaos.operatorpanel"
```

and window title:

```json
"title": "ImperaOS Operator Panel"
```

Set `Cargo.toml` identities:

```toml
[package]
name = "imperaos_operator_panel"
description = "ImperaOS Operator Panel"
authors = ["ImperaOS Contributors"]

[lib]
name = "imperaos_operator_panel_lib"
```

Update `src/main.rs`:

```rust
fn main() {
    imperaos_operator_panel_lib::run();
}
```

Do not change Tauri `bundle.resources` in this task.

- [ ] **Step 5: Implement CLI/module and app-data identity changes**

In `resolve_cli_command`, replace only active executable/module fallbacks:

```rust
program: cli_path.unwrap_or_else(|| "imperaos".to_string()),
prefix_args: vec!["-m".to_string(), "imperaos".to_string()],
```

and the final auto external fallback:

```rust
program: "imperaos".to_string(),
```

Add the pure path helpers:

```rust
fn macos_runtime_workdir(base: &Path) -> PathBuf {
    base.join("com.imperaos.operatorpanel").join("runtime")
}

fn windows_runtime_workdir(base: &Path) -> PathBuf {
    base.join("ImperaOS Operator Panel").join("runtime")
}

fn unix_runtime_workdir(base: &Path) -> PathBuf {
    base.join("imperaos-operator-panel").join("runtime")
}
```

Refactor `default_cli_workdir` to call them:

```rust
fn default_cli_workdir() -> Option<PathBuf> {
    if cfg!(target_os = "macos") {
        let home = std::env::var_os("HOME")?;
        let base = PathBuf::from(home)
            .join("Library")
            .join("Application Support");
        return Some(macos_runtime_workdir(&base));
    }
    if cfg!(windows) {
        if let Some(base) = std::env::var_os("LOCALAPPDATA").or_else(|| std::env::var_os("APPDATA")) {
            return Some(windows_runtime_workdir(&PathBuf::from(base)));
        }
    }
    let base = std::env::var_os("XDG_DATA_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".local/share")))?;
    Some(unix_runtime_workdir(&base))
}
```

Do not add former-path probes, migration, copying, deletion, or fallback.

- [ ] **Step 6: Regenerate and audit Cargo lock**

Run from the repository root:

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" check --manifest-path apps/operator-panel/src-tauri/Cargo.toml
git diff -- apps/operator-panel/src-tauri/Cargo.lock
```

Expected: the only `Cargo.lock` content change is root package name `imperaos_operator_panel` to `imperaos_operator_panel`; dependency versions/checksums are identical.

- [ ] **Step 7: Run focused GREEN tests**

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path apps/operator-panel/src-tauri/Cargo.toml desktop_metadata_uses_imperaos_identity -- --nocapture
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path apps/operator-panel/src-tauri/Cargo.toml resolve_cli_command_external_fallback_uses_imperaos -- --nocapture
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path apps/operator-panel/src-tauri/Cargo.toml desktop_runtime_workdirs_use_only_imperaos_identity -- --nocapture
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --manifest-path apps/operator-panel/src-tauri/Cargo.toml cli_env_allowlist_uses_only_canonical_project_prefix -- --nocapture
```

Expected: each selected test PASS.

- [ ] **Step 8: Run full Rust and target verification**

```powershell
& "$env:USERPROFILE\.cargo\bin\cargo.exe" fmt --manifest-path apps/operator-panel/src-tauri/Cargo.toml -- --check
& "$env:USERPROFILE\.cargo\bin\cargo.exe" test --locked --manifest-path apps/operator-panel/src-tauri/Cargo.toml
& "$env:USERPROFILE\.cargo\bin\cargo.exe" check --locked --all-targets --manifest-path apps/operator-panel/src-tauri/Cargo.toml
& "$env:USERPROFILE\.cargo\bin\cargo.exe" build --locked --bin imperaos_operator_panel --manifest-path apps/operator-panel/src-tauri/Cargo.toml
```

Expected: formatting, all Rust tests, all-target check, and renamed binary build exit 0.

- [ ] **Step 9: Run cross-language and Tauri contract gates**

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel test
corepack pnpm@10.29.2 --dir apps/operator-panel build
corepack pnpm@10.29.2 --dir apps/operator-panel tauri:smoke
```

Expected: frontend tests/build pass and contract smoke reports no failed checks.

- [ ] **Step 10: Run launched Tauri smoke**

```powershell
$env:OPERATOR_PANEL_TAURI_LAUNCH_TIMEOUT_MS='20000'
corepack pnpm@10.29.2 --dir apps/operator-panel tauri:smoke:launch
```

Expected: the Tauri dev process launches and stays alive for the probe window. This is a GUI/WebView operation; request the required managed execution permission. If platform tooling, WebView, display session, or sandbox policy blocks launch before application execution, record the exact blocker and do not alter product code.

- [ ] **Step 11: Audit active identity and deferred boundary**

Run targeted scans over the five active Task 5.3 files and new test:

```powershell
rg -n -i 'ImperaOS|com\.imperaos|imperaos_operator_panel|\boperator_panel_lib\b|program: "imperaos"|"-m".*"imperaos"|join\("imperaos-operator-panel"\)|join\("ImperaOS Operator Panel"\)' apps/operator-panel/src-tauri/tauri.conf.json apps/operator-panel/src-tauri/Cargo.toml apps/operator-panel/src-tauri/Cargo.lock apps/operator-panel/src-tauri/src/main.rs apps/operator-panel/src-tauri/src/bridge.rs apps/operator-panel/src-tauri/tests/desktop_identity.rs
rg -n 'resources/imperaos-runtime|imperaos-runtime/python' apps/operator-panel/src-tauri/tauri.conf.json apps/operator-panel/src-tauri/src/bridge.rs
git diff --check
```

Expected:

- active desktop product/bundle/crate/CLI/module/app-data scan has no matches;
- the second scan still finds only the deliberately deferred bundled-runtime resource references and their existing tests;
- no former environment prefix is accepted;
- no dependency/version/script/installer/CI/history changes;
- `git diff --check` exits 0.

- [ ] **Step 12: Commit, inventory, and report**

Stage only the six Task 5.3 files and commit:

```powershell
git -c user.name=Codex -c user.email=codex@openai.com commit -m "refactor: move desktop application identity to ImperaOS"
```

Run brand inventory against the committed implementation HEAD with MinGit on `PATH`. Write `.superpowers/sdd/task-5.3-report.md` containing RED/GREEN evidence, Rust/frontend counts, Cargo lock audit, binary name proof, contract/launched smoke outcome, active/deferred scans, committed inventory counts, exact diff boundary, implementation SHA, and explicit Task 6.1 resource deferral. Commit the report separately.
