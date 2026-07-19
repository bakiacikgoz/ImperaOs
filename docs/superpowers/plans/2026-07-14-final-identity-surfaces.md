# ImperaOS Final Identity Surfaces Implementation Plan

**Goal:** eliminate all remaining blocking identity findings and replace manually reviewed legacy artwork with a deterministic ImperaOS desktop icon set.

## Task 1: Establish regression tests

- Add a final-identity test that checks canonical runtime, fixture, command, URL, archive, and ignore-file surfaces.
- Preserve negative compatibility assertions by constructing former identifiers from separated fragments.
- Add a desktop-artwork test covering the SVG source, required Tauri outputs, PNG dimensions, container signatures, and obsolete screenshot removal.
- Run the new tests first and retain the expected failures as the red baseline.

## Task 2: Canonicalize active text surfaces

- Update remaining Python runtime prompts and remediation strings.
- Update operator-panel commands, fixtures, mock paths, and archive names.
- Update Rust environment compatibility construction.
- Update Python tests and fixtures while retaining their original behavioral intent.
- Remove the retired state-directory ignore entry while retaining `.imperaos/`.

## Task 3: Replace binary artwork

- Add `apps/operator-panel/src-tauri/icons/imperaos-source.svg` using the established nested-hex geometry.
- Generate the standard Tauri Windows, macOS, and PNG icon outputs from the SVG.
- Delete the three unreferenced planning screenshots containing retired visual identity.
- Visually inspect the regenerated primary PNG.

## Task 4: Verify Phase 9

- Run focused Python tests, operator-panel unit tests, Rust bridge tests, Ruff, and diff checks.
- Run the brand inventory and confirm zero blocking content/path/artifact findings.
- Record the inspected binary set, inventory totals, commands, and any platform limitations in a Phase 9 report.
- Obtain a final code review and commit the report.

## Task 5: Hand off to Phase 10

- Confirm the worktree is clean.
- Confirm no direct-root temporary test directories exist.
- Proceed to the full repository test, build, package, and release-readiness matrix.
