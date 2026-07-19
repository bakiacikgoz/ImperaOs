# ImperaOS Rebrand Release Readiness Plan

## Task 1: Lock the final source baseline

- Record the branch and HEAD.
- Confirm a clean worktree and zero direct-root agent artifacts.
- Run enforce-mode brand inventory at committed HEAD.

## Task 2: Execute the complete Python matrix

- Run whole-repository Ruff.
- Run the complete pytest suite with a short, isolated Windows temporary root.
- Diagnose any failure against the last verified baseline and rerun the exact
  failing node after correction or classification.

## Task 3: Execute panel and desktop matrices

- Run all Vitest tests, ESLint, i18n coverage, bridge parity, and the Vite
  production build.
- Run the Rust/Tauri test suite.
- Attempt the Windows Tauri production build and record any toolchain or signing
  boundary precisely.

## Task 4: Build and inspect release artifacts

- Build Python wheel and source distribution into an isolated ignored output.
- Inspect archive paths, package metadata, console entry point, and embedded
  identity resource.
- Install the wheel into an isolated environment and verify imports and CLI
  identity without publishing anything.
- Scan Python, web, and desktop outputs in artifact mode.

## Task 5: Close the plan

- Regenerate the committed-HEAD brand inventory.
- Remove all short temporary roots and generated scratch outputs not retained as
  evidence.
- Record exact results and external-action boundaries in the Phase 10 report.
- Obtain independent final review and commit the report.
