# Task 6.1 Verification Report

## Scope

This report records committed verification evidence for the Task 6.1 atomic bundled-runtime identity and packaging change. The verified scope is the rename to `imperaos-runtime`, the Rust direct and Tauri-nested resource resolver contract, Windows and macOS builders and fail-closed verifiers, Tauri packaging, workflow and runbook consumers, the Unicode-safe launched-smoke bootstrap, regression coverage, and cleanup of generated runtime payloads. Historical evidence was consumed as evidence and was not rewritten.

## Implementation Commit

The verified implementation is commit `736f83f5202ded90573ca4cc3de64df76b108262` with subject `build: package the ImperaOS bundled runtime`. The commit changes 19 files. At the start of this committed-HEAD verification, branch `codex/imperaos-full-rebrand-v1` was clean and pointed exactly at that commit. `git diff HEAD^ --check` produced no output and exited successfully.

## RED Evidence

The initial file-backed identity contract was demonstrated RED before production changes:

- `tests/test_bundled_runtime_identity.py`: 4 failed. The failures covered the absent `imperaos-runtime` directory, 15 active consumers that still used the former identity, missing ImperaOS operator-panel builder text, and the unsafe Tauri URL bootstrap.
- Rust `bundled_python_relative_path_matches_platform`: 1 failed because the implementation returned the former runtime path instead of `imperaos-runtime/python/Scripts/python.exe` on Windows.
- After the real Windows verifier exposed `unexpected manifest key: \ufeffplatform`, the PowerShell 5 UTF-8-without-BOM regression was added before the writer fix. The focused Python run was RED with 1 failed and 4 passed.

## Focused GREEN Evidence

The focused identity suite passed 24 of 24 selected Python tests across bundled runtime identity, automation distribution identity, serialized contract identity, runtime manifest validation, and the macOS local-trial gate. The PowerShell 5 manifest regression was GREEN in the focused identity file with 5 passed. Rust passed 1 platform-relative-path test and 2 resolver tests covering direct and Tauri-nested resource layouts.

## Rust and Frontend Gates

- `cargo fmt --check`: passed.
- Full Tauri Rust suite: 30 passed, 0 failed (29 library tests and 1 additional target test).
- Operator-panel Vitest: 66 files and 211 tests passed.
- ESLint: passed.
- TypeScript/Vite production build: passed with 143 modules transformed.
- Contract-mode `tauri:smoke`: completed with the expected `conditional` report.
- The final combined non-GUI verification exited 0 and printed `FINAL_VERIFICATION_OK`.

Rust emitted the existing Windows linker import-library informational warning, and Vite emitted the existing chunk-size warning; neither changed the passing gate results.

## PowerShell, Bash, and Workflow Syntax

Both changed PowerShell files parsed with zero AST errors. Both changed Bash files passed `bash -n`. All five changed GitHub Actions workflows parsed successfully with PyYAML and produced `workflow-yaml-ok`.

## Real Windows Runtime Build and Verification

The real Windows build produced `dist/imperaos-0.4.1-py3-none-any.whl`. Because the host has legacy Windows path limits enabled, `ensurepip` could not create a deeply nested setuptools test-data path under the long Unicode worktree path. The build used a validated, reversible short physical staging path under `C:\tmp`; the canonical workspace resource directory was restored after each attempt and was verified not to remain a reparse point.

The corrected real build and fail-closed verifier passed with:

```text
[manifest-verify] manifest=pass platform=windows arch=x86_64 imperaos_version=0.4.1
[verify] imperaos_version=0.4.1
[verify] python_exe_sha256=4cca2027319c08dca5cc4b64c9ba415cc89205152202cb6805081277c43b610f
[verify] manifest=pass
```

The verifier passed again after the resource directory was restored to its physical canonical workspace path, with the same version, hash, and manifest result.

## Launched Tauri Smoke

The launched-smoke command was `corepack pnpm@10.29.2 --dir apps/operator-panel run tauri:smoke:launch`. The fixed `fileURLToPath(import.meta.url)` bootstrap resolved the Unicode worktree path without a duplicated drive prefix or percent-encoded path. The smoke then reached a later environment/tooling blocker:

```text
desktopLaunch: failed
detail: spawn corepack ENOENT
```

All pre-launch contract checks in the report passed. `launchedBridgeProbe` was not attempted because desktop launch did not pass, and the fail-closed gate was not weakened.

## Generated Payload Cleanup

Cleanup resolved and checked the canonical resource parent/child boundary before removing the generated payload. The generated runtime was removed through the verified short physical staging path to avoid the host path-limit failure. The canonical resource directory was restored as a normal physical directory. Fresh inspection for this report found no link or reparse metadata and exactly one child: tracked `README.txt`. No generated runtime payload is included in the implementation or report commit.

## Active Former-Identity Scan

The Task 6.1 active-scope former runtime-path scan found no matches. The former module-invocation scan across the three active runbooks also found no matches. This active-scope result is distinct from the repository-wide inventory below, which intentionally preserves historical evidence and exposes work assigned to the later full-rebrand boundary.

## Brand Inventory

The required committed-HEAD inventory ran against `736f83f5202ded90573ca4cc3de64df76b108262` and generated an untracked/ignored Markdown report plus JSON report under `.superpowers/sdd/task-6.1-brand-inventory`. The command completed successfully; the inventory result itself was `fail`, as expected for the pre-Task-6.2 repository-wide baseline:

| Measure | Count |
| --- | ---: |
| Scanned files | 1,539 |
| Legacy content matches | 903 |
| Legacy path matches | 2 |
| Binary metadata matches | 19 |
| Built artifact matches | 0 |

The JSON report records canonical brand `ImperaOS`, implementation commit `736f83f5202ded90573ca4cc3de64df76b108262`, and generation time `2026-07-14T08:24:42.589619Z`. These generated inventory artifacts are evidence inputs only and are not committed.

## macOS Execution Limitation

Real macOS runtime build, verification, and launched desktop execution were unavailable on this Windows host. This limitation is separate from the passing portable evidence: both Bash scripts passed `bash -n`, the changed workflows parsed, the macOS local-trial validator coverage passed, and the cross-platform file-backed identity and Rust resolver contracts passed. No claim of real macOS runtime execution is made.

## Task 6.2 Boundary

Task 6.1 is limited to the atomic bundled-runtime identity and packaging slice. It does not perform the remaining repository-wide full-rebrand edits, rewrite historical evidence, or repair the 903 legacy-content, 2 legacy-path, and 19 binary-metadata inventory findings. Those findings form the committed baseline for Task 6.2. Built-artifact findings are already zero.

## Final Status

`DONE_WITH_CONCERNS`: the committed implementation, focused regression evidence, full non-GUI gates, real Windows runtime build, fail-closed verification, cleanup boundary, and committed-HEAD inventory are recorded and internally consistent. The remaining concerns are the later `spawn corepack ENOENT` launched-desktop blocker and the absence of real macOS execution on this Windows host. The repository-wide inventory failure is an expected Task 6.2 boundary, not a Task 6.1 cleanup failure.
