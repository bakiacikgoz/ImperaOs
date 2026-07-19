# Task 6.2 Verification Report

## Scope

Task 6.2 changed only the CI and direct release-script identity boundary. It added a file-backed regression contract and made the four prescribed consumer edits: internal unsigned macOS/Windows binary staging, clean Windows installer product identity, the Windows installer script default, and macOS quarantine metadata. Runtime paths, workflow triggers, signing variables, cache keys, generic artifact roots, release eligibility metadata, and later-phase soak/evidence surfaces were not changed.

No push, workflow dispatch, secret mutation, signing, notarization, or release publication occurred.

## Commit History

- Base commit: `341c4166e20069ed4994b0cd97c9fb570795d1d1`
- Original implementation commit: `40422de2f3e6b38b9acf9e4d7c5059a03a419457` (`ci: move build and release workflows to ImperaOS`)
- Original verification-report commit: `b297ca8` (`docs: record task 6.2 verification`)
- First review-hardening commit: `ddff3e7ce19f83b36cda75afa204419c02063866` (`test: harden CI release identity regression`)
- First post-review report commit: `ba2279420d6c12203c840b59820c8066d3329ddc` (`docs: update task 6.2 verification`), superseded by this final report update
- Second review-hardening commit: `cf09e0deb1927e8c332c0094e0442699f65b8873` (`test: require CI brand gate failures to block`)

The exact implementation diff is five files, 74 insertions, and 6 deletions:

| File | Change | Insertions | Deletions |
| --- | --- | ---: | ---: |
| `.github/workflows/operator-panel-internal-unsigned-build.yml` | modified | 3 | 3 |
| `.github/workflows/operator-panel-windows-clean-smoke.yml` | modified | 1 | 1 |
| `apps/operator-panel/scripts/codesign_notarize_macos.sh` | modified | 1 | 1 |
| `apps/operator-panel/scripts/windows_installer_smoke.ps1` | modified | 1 | 1 |
| `tests/test_ci_release_identity.py` | added | 68 | 0 |

The consumer edits set the unsigned staged binaries to `imperaos_operator_panel` and `imperaos_operator_panel.exe`, the workflow and script product name to `ImperaOS Operator Panel`, and the quarantine metadata producer brand to `ImperaOS`. Post-review findings concerned only the strength of the regression contract and were fixed in the separate test-only hardening commit; no production workflow or release-script change was required.

## RED Evidence

Before the production edits, `tests/test_ci_release_identity.py` produced 5 failed and 1 passed. The five expected identity-contract nodes failed, while the existing early fail-closed brand-gate contract passed. This demonstrated that the new regression contract detected each prescribed stale consumer before implementation.

## Focused GREEN Evidence

The focused six-file verification set passed 22/22:

```text
tests/test_ci_release_identity.py
tests/test_automation_distribution_identity.py
tests/test_operator_panel_internal_unsigned_workflow.py
tests/test_windows_release_workflows_static.py
tests/test_macos_release_workflows_static.py
tests/test_ci_node_action_inventory.py
```

Ruff also completed with `All checks passed!` after applying its single import-order whitespace normalization to the new test file and rerunning the focused tests.

## Workflow, PowerShell, and Bash Syntax

- PyYAML parsed all 11 active workflow files: `workflow-yaml-ok:11`.
- PowerShell AST parsing of `apps/operator-panel/scripts/windows_installer_smoke.ps1` completed with zero parser errors.
- `bash -n` parsing of `apps/operator-panel/scripts/codesign_notarize_macos.sh` exited 0.

## Canonical Binary Build

The canonical Cargo binary build command exited 0 and built `imperaos_operator_panel`. No former-binary fallback was used. The host emitted only non-fatal toolchain messages about canonicalizing the user path and the Windows linker creating its import library.

## Full Python Regression

The decisive short-temp comparison is:

- Implementation `HEAD` (`40422de`) with `--basetemp C:\t\x`: 919 passed, 9 skipped, 1 failed.
- Exact base (`341c416`) with `--basetemp C:\t\b`: 913 passed, 9 skipped, 1 failed.
- Both runs failed only `tests/test_brand_identity.py::test_typescript_identity_is_a_typed_frozen_view_of_canonical_json`, with the identical pre-existing assertion.

The six additional passing tests at `HEAD` are exactly the new Task 6.2 regression contract. With the longer `C:\t\task-6-2-full` base, `HEAD` produced 901 passed, 9 skipped, and 19 failed. The 18 additional failures were path-sensitive cascades: every affected node passed under shorter temp roots without any code change. Therefore Task 6.2 introduced no full-suite regression; the one remaining short-temp failure predates the implementation commit.

## Active CI and Release Identity Scan

The constructed-token scan of all active workflows plus `apps/operator-panel/scripts/windows_installer_smoke.ps1` and `apps/operator-panel/scripts/codesign_notarize_macos.sh` found no former product or distribution identity. The Task 6.2 active workflow/script boundary is clean.

## Early Blocking Brand Gate

The early CI gate remains fail-closed: the parsed `jobs.test.steps` sequence contains exactly one Sync dependencies step, one ImperaOS brand consistency gate step, and one Lint step in that order. The gate step's command is exactly `make brand-consistency-gate`; `continue-on-error` must be absent or the literal boolean `false`, so boolean `true` and expression strings are forbidden; an `if` condition is also forbidden. The Makefile target still runs the gate in `--mode enforce`.

## Post-review Hardening

Review identified two contract-strength issues in `tests/test_ci_release_identity.py`:

1. The original early-gate test used global text positions and a substring command check, so it could accept a fail-open command or step controls.
2. The original canonical-binary test used a global occurrence count plus partial substrings rather than four independent complete source/destination assertions.

Mutation evidence confirmed the first issue. With an uncommitted `run: make brand-consistency-gate || true` mutation, the original test passed 1/1. After strengthening the test while the mutation remained, the test failed on the exact command comparison. The workflow was then restored exactly; no workflow diff was committed.

The hardened test uses `yaml.safe_load` with normalization for GitHub Actions' YAML 1.1 `on` key, selects only the `test` job, enforces unique step names and exact ordering, requires the exact gate command, and rejects fail-open step controls. The binary assertions now require each complete macOS/Windows source and destination exactly once.

Post-review covering gates:

- `tests/test_ci_release_identity.py` plus `tests/test_automation_distribution_identity.py`: 7 passed.
- Ruff on `tests/test_ci_release_identity.py`: `All checks passed!`.
- PyYAML parsing of all active workflows: `workflow-yaml-ok:11`.

The first hardening is committed separately as `ddff3e7ce19f83b36cda75afa204419c02063866`; it changes only the regression test.

### Second re-review hardening

Second re-review identified that `gate_step.get("continue-on-error") is not True` still accepted the exact GitHub Actions expression `continue-on-error: ${{ true }}` because safe YAML parsing preserves the expression as a string. Mutation evidence confirmed the gap: the first hardened test incorrectly passed 1/1 with that expression. Changing only the assertion to `gate_step.get("continue-on-error", False) is False` produced the expected RED (`assert '${{ true }}' is False`). After restoring the workflow exactly, the covering suite passed 7/7, Ruff passed, and all 11 workflows parsed.

The second hardening is committed separately as `cf09e0deb1927e8c332c0094e0442699f65b8873`; it is a one-line test-only change. No production workflow diff was committed in either review cycle.

## Brand Inventory

The exact committed-`HEAD` inventory command completed successfully and wrote ignored JSON/Markdown artifacts under `.superpowers/sdd/task-6.2-brand-inventory`. JSON validation confirmed:

| Field | Actual value |
| --- | ---: |
| `gitCommit` | `cf09e0deb1927e8c332c0094e0442699f65b8873` |
| `status` | `fail` |
| `scannedFileCount` | 1,544 |
| `legacyContentMatchCount` | 907 |
| `legacyPathMatchCount` | 2 |
| `binaryMetadataMatchCount` | 19 |
| `builtArtifactMatchCount` | 0 |
| Total findings | 928 |

The category sum is 928 and exactly matches the JSON `findings` array length. The findings comprise 909 blocking findings and 19 manual-review findings. The inventory was regenerated after the second test-only hardening commit, and `gitCommit` exactly matched committed `HEAD` at generation time. The repository-wide inventory correctly remains `fail` because later phases own the remaining findings; this does not contradict the clean Task 6.2 active workflow/script scope. Inventory JSON/Markdown artifacts remain ignored and are not part of the commits.

## Remote CI Deferral

Full remote-CI green is deferred to Phase 10. The early enforcing brand gate correctly continues to report later-phase repository findings, so Task 6.2 neither claims repository-wide inventory success nor weakens the gate to manufacture a green result.

## Phase 7 Boundary

Qualification soak, temp-path, service-label, and observability identity work remains Phase 7.1. Python evidence descriptions, schemas, historical evidence, and other repository-wide inventory findings remain outside Task 6.2. This task made no edits in those later-phase surfaces.

## Final Status

`DONE_WITH_CONCERNS` — Task 6.2 satisfies its minimal four-consumer identity contract, twice-hardened regression, syntax, canonical-build, active-scope scan, fail-closed gate, inventory, and no-side-effect requirements across the original implementation and separate review-hardening commits. Both review rounds are closed. The remaining concerns are external to this implementation: one pre-existing TypeScript identity test failure remains, and a longer Windows temp root creates 18 path-sensitive failures that disappear without code changes. Full remote-CI green remains intentionally deferred to Phase 10.
