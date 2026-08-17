# Web Workspace Metadata Design

Date: 2026-07-13
Status: Approved
Plan task: Phase 5, Task 5.2

## Objective

Align the JavaScript workspace, Operator Panel package, and browser document metadata with the canonical ImperaOS identity. Preserve dependencies, versions, scripts, runtime behavior, and Tauri-owned metadata.

## Decisions

- Root package name: `imperaos-workspace`.
- Operator Panel package name: `imperaos-operator-panel`.
- Browser document title: `ImperaOS Operator Panel`.
- The current Vite favicon does not contain the former product brand and remains unchanged in this task.
- Package versions, scripts, dependencies, and package-manager declarations remain unchanged.
- Tauri, Cargo, bundled-runtime, installer, release, and CI identities remain owned by later tasks.

## Components and Data Flow

`package.json` provides the private workspace identity. `apps/operator-panel/package.json` provides the private web application identity. `apps/operator-panel/index.html` provides the initial browser title before React mounts. The Playwright helper verifies that the served document exposes the same exact title.

No runtime code reads these package names. Changing them must not alter dependency resolution or lockfile package versions.

## Lockfile Behavior

Run the repository's pinned pnpm version with `install --lockfile-only`. The pnpm v9 lockfile records workspace importers by path and does not currently record either private package name, so no lockfile diff is expected. If pnpm produces unrelated dependency churn, reject that churn and investigate rather than accepting it.

## Test Design

Follow RED-GREEN-REFACTOR:

1. Add a focused metadata contract test that reads the root package, app package, and HTML document.
2. Confirm it fails against the current names/title.
3. Apply only the three metadata value changes and the matching Playwright expectation.
4. Confirm the focused test passes.
5. Run full Operator Panel tests, lint, build, and the relevant browser check where the installed environment supports it.
6. Regenerate the lockfile deterministically and confirm no dependency or lockfile drift.
7. Scan the three active metadata files for former workspace/app/title identities.

## Error and Compatibility Behavior

- Invalid or missing metadata causes the focused contract test to fail with the mismatched field.
- No alias for former package names is retained.
- No migration is required because both packages are private and the workspace importer paths remain unchanged.
- The existing missing local Playwright Chromium binary may block browser launch; record that environment condition without adding a product-code workaround.

## Acceptance Criteria

- Root package name is exactly `imperaos-workspace`.
- App package name is exactly `imperaos-operator-panel`.
- HTML and E2E document title are exactly `ImperaOS Operator Panel`.
- The favicon remains unchanged.
- Full unit, lint, and build verification passes.
- `pnpm-lock.yaml` has no unintended drift.
- No Tauri, Cargo, runtime, installer, CI, dependency, version, script, or historical file changes are included.

## Implementation Boundary

The implementation commit subject must be exactly:

`build: align web workspace metadata with ImperaOS`
