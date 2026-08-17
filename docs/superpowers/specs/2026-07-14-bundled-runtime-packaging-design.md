# Bundled Runtime Packaging Design

Date: 2026-07-14
Status: Approved
Plan task: Phase 6, Task 6.1

## Objective

Move the Operator Panel bundled runtime from the former physical resource identity to `imperaos-runtime` as one atomic packaging change. Keep Tauri, Rust resolution, build/verify scripts, CI path consumers, installer smoke, ignore rules, and active operator runbooks coherent in the same commit.

## Decisions

- Physical resource directory: `apps/operator-panel/src-tauri/resources/imperaos-runtime/`.
- Tauri resource entry: `resources/imperaos-runtime/`.
- Windows relative Python path: `imperaos-runtime/python/Scripts/python.exe`.
- macOS/Linux relative Python path: `imperaos-runtime/python/bin/python`.
- Wheel discovery remains `imperaos-*.whl`.
- Runtime validation remains `python -m imperaos`.
- Runtime manifest field remains `imperaos_version`.
- Generated README and error/output text use ImperaOS only.
- No compatibility directory, duplicate resource, symlink, or former-path fallback is retained.
- Fix the Task 5.3 Windows/Unicode smoke blocker with `fileURLToPath(import.meta.url)` in `tauri-launched-smoke.ts`.

## Atomic Consumer Set

The directory rename must update every active direct path consumer so the commit remains buildable:

- `.gitignore` generated-runtime patterns;
- `apps/operator-panel/src-tauri/tauri.conf.json`;
- `apps/operator-panel/src-tauri/src/bridge.rs` and its resolver tests;
- Windows/macOS runtime build and verify scripts;
- `apps/operator-panel/scripts/windows_installer_smoke.ps1` path lookup;
- `.github/workflows/windows-ci.yml`;
- `.github/workflows/operator-panel-runtime-matrix.yml`;
- `.github/workflows/operator-panel-release-windows.yml`;
- `.github/workflows/operator-panel-release-macos.yml`;
- `.github/workflows/operator-panel-internal-unsigned-build.yml`;
- active Operator Panel README, macOS local-trial runbook, and release checklist commands.

Historical finalization/evidence reports, the Task 5.3 design/plan explaining the deferral, and immutable evidence are not rewritten.

## Runtime Build Flow

1. Resolve or build an `imperaos-*.whl` wheel.
2. Remove only the verified canonical `imperaos-runtime` output directory.
3. Create a platform-specific virtual environment below `imperaos-runtime/python`.
4. Install the wheel.
5. Copy required config on platforms whose current build flow does so.
6. Validate `python -m imperaos --version`; macOS additionally validates operator capabilities from a neutral working directory.
7. Write `RUNTIME_MANIFEST.txt` with `imperaos_version` and existing platform-specific integrity evidence.
8. Write an ImperaOS-only runtime README.

The generated Python/config/manifest payload remains ignored and must not be committed. The tracked resource directory contains only its canonical README placeholder after verification cleanup.

## Resolver and Packaging Flow

Tauri bundles `resources/imperaos-runtime/`. The Rust bridge searches both direct and Tauri-nested resource layouts using the new relative path while preserving its resolution order and fail-closed behavior. Installer/runtime workflow staging copies the same new directory name without aliasing it back to the former path.

## Smoke Harness Repair

Replace the Windows-unsafe bootstrap:

```typescript
path.dirname(new URL(import.meta.url).pathname)
```

with:

```typescript
path.dirname(fileURLToPath(import.meta.url))
```

This is limited to `tauri-launched-smoke.ts`, the acceptance harness blocked in Task 5.3. Similar scripts are not mass-refactored in this task.

## Task 6.2 Boundary

Task 6.1 may update workflow and installer-smoke lines only where the physical runtime path changes. Task 6.2 retains ownership of:

- workflow/artifact/package display names;
- expected product and binary names not required by this path rename;
- environment/secrets namespace changes;
- cache keys;
- broader release/evidence text;
- final brand gate placement.

## Test Design

Follow RED-GREEN-REFACTOR:

1. Add a file-backed Python identity test that requires the new directory, rejects the old directory, and scans the active consumer set for the former runtime path/module identity.
2. Update Rust resolver expectations before implementation and observe RED.
3. Add a smoke-bootstrap assertion requiring `fileURLToPath` and observe RED.
4. Perform the physical rename and minimal consumer edits.
5. Run focused Python tests, Rust tests, YAML parsing/static workflow checks, PowerShell parsing, shell syntax checks, frontend tests/build, and Tauri contract smoke.
6. Build and verify a real Windows bundled runtime from an ImperaOS wheel.
7. Run the launched Tauri smoke with managed GUI permission after fixing the path bootstrap.
8. Clean generated ignored runtime contents only after resolving and verifying the absolute target stays inside the canonical worktree resource directory; preserve the tracked README.
9. Confirm active former runtime path count is zero and only explicitly historical/design records retain it.

## Error and Safety Behavior

- Build scripts refuse unsupported architectures and unsafe cleanup targets as before.
- Missing wheel, Python, manifest, config, or integrity evidence remains fail-closed.
- Runtime manifest validation rejects former/extra/missing/blank keys.
- Cleanup is limited to the resolved `imperaos-runtime` directory inside `src-tauri/resources`.
- No external state migration or user-data deletion occurs.
- If real macOS execution is unavailable on Windows, shell/static tests and existing behavioral validator tests provide portable evidence; the report must state this limitation.

## Acceptance Criteria

- Active source, scripts, workflows, ignore rules, and runbooks contain no former bundled-runtime path.
- The old resource directory is absent and the new tracked directory exists.
- Tauri and Rust resolve `imperaos-runtime` only.
- Wheel/module/manifest identities are exact ImperaOS values.
- Real Windows runtime build and verify pass without committing generated payload.
- Rust, Python, frontend, workflow, shell, PowerShell, and Tauri contract gates pass.
- Launched smoke passes, or any remaining platform blocker is precisely recorded after the bootstrap fix.
- Broader CI/release identity work remains scoped to Task 6.2.

## Implementation Boundary

The implementation commit subject must be exactly:

`build: package the ImperaOS bundled runtime`
