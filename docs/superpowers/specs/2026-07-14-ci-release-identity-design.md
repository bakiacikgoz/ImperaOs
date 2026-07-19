# ImperaOS CI and Release Identity Design

Date: 2026-07-14
Status: Approved by delegated user authority
Plan task: Phase 6, Task 6.2

## Objective

Move the remaining active GitHub Actions and desktop release-script identity surfaces to ImperaOS without absorbing the observability, soak, evidence-schema, or broad repository cleanup assigned to later phases. Preserve the existing release safety gates and keep the early brand consistency gate fail-closed.

## Current State

Task 6.1 already moved every bundled-runtime resource path to `imperaos-runtime`. Current inspection found four remaining Task 6.2 identity consumers:

- `.github/workflows/operator-panel-internal-unsigned-build.yml` stages the former Rust binary name on macOS and Windows;
- `.github/workflows/operator-panel-windows-clean-smoke.yml` passes the former product name to the installer smoke;
- `apps/operator-panel/scripts/windows_installer_smoke.ps1` defaults to the former product name;
- `apps/operator-panel/scripts/codesign_notarize_macos.sh` writes the former product identity into the quarantine metadata tag.

No former brand is present in active workflow environment-variable names, GitHub secret names, or cache keys. The runtime paths in the relevant workflows are already canonical after Task 6.1. `.github/workflows/ci.yml` already invokes `make brand-consistency-gate` before lint and tests, and the Makefile target already uses `--mode enforce`.

## Chosen Approach

Use an atomic, narrow CI/release identity change:

- change the debug binary source and staged names to `imperaos_operator_panel` and `imperaos_operator_panel.exe`;
- change the installer-smoke expected product to `ImperaOS Operator Panel` in both the workflow and PowerShell default;
- change the macOS quarantine metadata brand to `ImperaOS`;
- add one file-backed regression suite that checks both absence of former identities and presence of the exact canonical identities;
- verify every workflow, but do not edit already-canonical files merely to create a diff.

This approach is preferred over a broad shell-script sweep because qualification soak paths, service labels, log names, and metric-related identities are explicitly owned by Phase 7. It is preferred over a workflow-only change because release scripts are direct runtime consumers and must remain consistent with their callers.

## Identity Contract

The Task 6.2 contract is:

| Surface | Canonical value |
|---|---|
| Tauri debug binary | `imperaos_operator_panel` |
| Windows debug binary | `imperaos_operator_panel.exe` |
| Installed product | `ImperaOS Operator Panel` |
| macOS quarantine metadata brand | `ImperaOS` |
| CI brand gate command | `make brand-consistency-gate` |
| Brand gate mode | `--mode enforce` |

The contract does not rename generic and already-canonical artifact roots such as `operator-panel-internal-unsigned`, `windows-release-evidence`, or `operator-panel-*`. It also does not rename standard platform signing variables such as `WINDOWS_SIGNING_CERT_*`, `MACOS_SIGNING_*`, or `APPLE_*`; these are not former product identities.

## Components and Data Flow

### Internal unsigned build

Tauri produces the binary named by the Rust package configuration from Task 5.3. The internal unsigned workflow copies that binary into a staged artifact. Both the source path and destination filename must use `imperaos_operator_panel`; the existing internal-only, unsigned, and not-public-release-eligible metadata remains unchanged.

### Windows clean installer smoke

The clean-smoke workflow passes the exact installed product name into `windows_installer_smoke.ps1`. The script compares that value with installed-program inventory and retains its existing fail-closed behavior when the product cannot be found or verified. The workflow and default parameter must agree on `ImperaOS Operator Panel`.

### macOS signing and notarization

The codesign/notarization script preserves all credential, signing, notarization, stapling, and verification behavior. Only the quarantine metadata origin brand changes to `ImperaOS`; no entitlement, identifier, or signature-policy logic changes.

### Early brand gate

`ci.yml` retains the current ordering: dependency synchronization, then the blocking ImperaOS brand gate, then lint and the broader test matrix. The Makefile continues to run the gate in `enforce` mode. No allowlist or temporary weakening is introduced.

## Phase Boundaries

Task 6.2 does not change:

- qualification soak temp directories, monitor copy, or launchd service labels; Phase 7.1 owns them;
- metrics, log labels, `.prom` names, or observability dashboards; Phase 7.1 owns them;
- Python evidence descriptions, evidence schemas, signing payload fields, or historical evidence; Phase 7.2 and later cleanup phases own them;
- user-data paths or runtime configuration namespaces;
- generic artifact names that already contain no former identity.

The repository-wide brand inventory currently fails on findings intentionally assigned to later phases. Task 6.2 therefore proves its active scope locally and preserves the early blocking gate. Full remote-CI green is a Phase 10 closure criterion after the remaining inventory is removed; Task 6.2 must not claim it early.

## Test Design

Follow RED-GREEN-REFACTOR:

1. Add `tests/test_ci_release_identity.py` before production edits.
2. Require the exact canonical product, binary, quarantine brand, early gate command, and `enforce` mode.
3. Reject constructed former product/binary tokens across all workflow YAML plus the two release scripts without embedding a contiguous former token in the test source.
4. Reject former-brand prefixes in workflow env, secret, and cache-key identity surfaces while preserving standard platform credential names.
5. Observe RED on the four current consumers.
6. Apply only the four minimal identity edits.
7. Run the new tests plus existing automation distribution, internal unsigned workflow, Windows release workflow, and macOS release workflow static suites.
8. Parse all workflow YAML, parse the PowerShell script with the PowerShell AST, and run `bash -n` on the macOS script.
9. Run the broader Python suite because the early brand gate and workflow inventory are cross-cutting repository gates.
10. Run brand inventory against the committed implementation and record the new baseline without treating later-phase findings as Task 6.2 regressions.

## Error and Safety Behavior

- Missing or mismatched installed product remains a blocking installer-smoke failure.
- Missing debug binaries still fail staging; no fallback to a former binary is added.
- Signing/notarization credential and verification failures remain blocking.
- The brand gate remains fail-closed in `enforce` mode.
- No secret values are printed, renamed, migrated, or copied.
- No external GitHub secret mutation, push, workflow dispatch, or release publication occurs in this task.

## Acceptance Criteria

- Active GitHub workflows contain no former product or binary identity.
- The two direct release scripts use only the canonical product identity.
- Internal unsigned staging uses `imperaos_operator_panel` on both platforms.
- Installer smoke expects `ImperaOS Operator Panel` consistently.
- macOS quarantine metadata uses `ImperaOS`.
- No former-brand workflow env, secret, or cache key remains.
- The brand gate is an early blocking CI step and still runs `--mode enforce`.
- Workflow YAML, PowerShell, Bash, and focused/static Python tests pass.
- The task report clearly defers full remote-CI green to Phase 10 and does not claim that the repository-wide inventory is already clean.

## Commit Boundary

The implementation commit subject must be exactly:

`ci: move build and release workflows to ImperaOS`
