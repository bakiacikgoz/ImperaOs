# Task 7.1 Verification Report

## Scope

Task 7.1 moved the active observability and operational-runtime identity boundary to ImperaOS. The implementation renamed exactly eight Prometheus textfile series and the coupled qualification workspace, launchd label, watcher discovery/help/title, macOS Ollama log, governance demo payload, and computer-use gate temporary identities. It also repaired the resilient soak launcher package copy and updated the active runbook soak example.

The implementation did not change metric values or ordering, the metrics snapshot JSON schema, control flow, historical evidence, or managed-KMS/signing identities. No soak, launchd job, Ollama service, or external monitoring update was started or performed.

## Implementation Commit

- SHA: `eaf2be343d2dce80ec663a4276d1c97c9ab828c5`
- Subject: `refactor: publish observability under ImperaOS metrics`
- Diff: 9 files changed, 145 insertions, 23 deletions

The committed change contains the eight active production/documentation consumers plus `tests/test_observability_identity.py`. The committed-HEAD inventory independently recorded the same full SHA.

## RED Evidence

Before production edits, the new regression contract was run with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_observability_identity.py
```

Result: `9 failed, 1 passed`. The exact Prometheus snapshot and eight active identity-consumer cases failed as expected. The already-canonical enterprise Prometheus path assertion passed.

## Prometheus Snapshot

The final contract requires this exact newline-terminated textfile output:

```text
imperaos_approval_pending 2
imperaos_approval_oldest_age_seconds 17
imperaos_audit_inconsistency_total 3
imperaos_replay_verify_failure_total 5
imperaos_memory_conflict_total 7
imperaos_fallback_mode_total 11
imperaos_control_plane_agents_registered 13
imperaos_control_plane_claims_blocked 19
```

It also requires the enterprise destination to remain `.imperaos/enterprise/metrics/imperaos.prom`. A fresh report-stage run of `tests/test_observability_identity.py` passed all 10 tests; its worktree-local `--basetemp` directory was removed immediately afterward.

## Focused GREEN Evidence

The implementation-stage focused command covered the new identity contract plus runtime paths, the computer-use integration gate, enterprise CLI, and enterprise qualification:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp C:\tmp\imperaos-task-7-1-focus `
  tests/test_observability_identity.py `
  tests/test_runtime_paths.py `
  tests/test_computer_use_integration_gate.py `
  tests/test_enterprise_cli.py `
  tests/test_enterprise_qualification.py
```

Result: `61 passed`.

Ruff was run against the new contract and the modified Python production surfaces:

```powershell
.\.venv\Scripts\python.exe -m ruff check tests/test_observability_identity.py imperaos/enterprise/observability.py scripts/evaluate_computer_use_integration_gate.py
```

Result: `All checks passed!`

## Bash Syntax

Git Bash `bash -n` parsed all five modified shell scripts with exit code 0:

- `scripts/launch_resilient_qualification_soak.sh`
- `scripts/run_qualification_soak_supervised.sh`
- `scripts/watch_qualification_soak.sh`
- `scripts/bootstrap_macos.sh`
- `scripts/demo_governance_v03.sh`

This was syntax-only validation; none of the scripts was launched.

## Broader Python Regression

One implementation-stage full-suite probe completed with `19 failed, 9 skipped`. One failure was the already-recorded TypeScript canonical-identity baseline failure. The other 18 were the established Windows temporary-path-sensitive failures previously reproduced in Phase 6; they disappear under a shorter temporary root without code changes. The new Task 7.1 contract did not fail.

The full suite was not repeated for this report. The focused short-root suite (`61 passed`) and the fresh final identity contract (`10 passed`) are the authoritative Task 7.1 GREEN evidence. This report does not claim a repository-wide green Python suite.

## Active Operational Identity Scan

The contract checks all eight active Task 7.1 production/documentation consumers for their required ImperaOS identity and rejects the corresponding mapped former identity. The checked boundary includes Prometheus output, resilient launcher workspace/package copy, launchd supervision, watcher discovery/help/title, macOS bootstrap log, governance demo payload, computer-use gate temporary names, and the active operations-runbook example.

Independent implementation review found no identity leak in the current active-file scan. It recorded one Minor coverage note: the committed regression rejects the explicitly mapped former variants instead of applying a generic former-brand scan to every active Task 7.1 file. There were no Critical or Important findings, and the reviewer marked the implementation `Ready for report: Yes`.

## Brand Inventory

The committed implementation HEAD was inventoried with:

```powershell
.\.venv\Scripts\python.exe scripts/run_brand_consistency_gate.py `
  --mode inventory `
  --repo-root . `
  --output-root .superpowers\sdd\task-7.1-brand-inventory `
  --json
```

JSON validation produced:

| Field | Actual value |
| --- | ---: |
| `gitCommit` | `eaf2be343d2dce80ec663a4276d1c97c9ab828c5` |
| `status` | `fail` |
| `scannedFileCount` | 1,547 |
| `legacyContentMatchCount` | 897 |
| `legacyPathMatchCount` | 2 |
| `binaryMetadataMatchCount` | 19 |
| `builtArtifactMatchCount` | 0 |
| Total findings | 918 |

The category sum equals the 918-element `findings` array. Classification counts are 899 blocking and 19 manual-review findings. `gitCommit` exactly matched committed HEAD at generation time. The inventory remains `fail` because Task 7.2 and later phases own the remaining repository-wide findings; this does not contradict the clean Task 7.1 active boundary. The JSON and Markdown inventory artifacts are ignored and are not committed.

## Task 7.2 Boundary

Managed-KMS drill identities, signing/evidence identities, historical evidence, and other remaining repository-wide findings are intentionally deferred to Task 7.2 or later phases. Task 7.1 did not modify `scripts/run_managed_kms_adapter_drill.py` and made no signing, key-management, or evidence-schema change.

## Temporary-Artifact Cleanup

The implementation-stage agent-owned roots were boundary-checked, removed, and verified absent:

- `C:\tmp\imperaos-task-7-1-focus`
- `C:\tmp\imperaos-task-7-1-full`
- `artifacts\pytest-task-7-1-focused`

The report-stage worktree-local pytest root was also removed and verified absent. No direct `C:\p*` or `C:\t` directory was created. The ignored `.superpowers/sdd/task-7.1-brand-inventory` directory is retained intentionally as Task 7.1 verification evidence.

## Final Status

`DONE_WITH_CONCERNS` - Task 7.1 satisfies the exact Prometheus snapshot, canonical destination, focused regression, Ruff, Bash syntax, active identity, inventory, boundary, cleanup, and no-external-action requirements. Review found no Critical or Important issue and marked the task ready for its report. The sole Minor note is the generic-scan coverage opportunity described above. The known repository-wide concerns remain the pre-existing TypeScript identity failure, 18 Windows temp-path-sensitive failures under longer roots, and later-phase inventory findings. These do not block proceeding to Task 7.2.
