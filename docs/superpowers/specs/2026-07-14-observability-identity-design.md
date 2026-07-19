# ImperaOS Observability Identity Design

Date: 2026-07-14
Status: Approved by delegated user authority
Plan task: Phase 7, Task 7.1

## Objective

Publish active operational metrics, qualification-soak paths, temporary-file names, log names, service labels, and monitor branding under ImperaOS. Keep runtime behavior unchanged and preserve historical evidence and the managed-KMS/evidence boundary assigned to Task 7.2.

## Current State

Runtime configuration already points Prometheus textfile output at `.imperaos/metrics/imperaos.prom`, but `write_prometheus_textfile()` still emits eight `imperaos_` metric names. Active macOS and qualification scripts also retain former-brand temp roots, a launchd label, a log file, a demo payload, a computer-use integration-gate temp prefix, and a monitor title. The active operations runbook still shows the former soak root.

## Chosen Approach

Treat metrics and their directly operated runtime surfaces as one atomic identity boundary:

- rename the eight emitted metric names from `imperaos_` to `imperaos_`;
- rename active qualification-soak workspace discovery, examples, and launchd labels;
- rename the active macOS Ollama log, governance-demo payload, and computer-use gate temp paths;
- repair the resilient-soak copy list to copy the renamed `imperaos` package;
- update only the active runbook soak example;
- add a file-backed regression contract and an exact Prometheus snapshot test.

Historical reports, archived evidence, and compatibility documentation remain unchanged. The managed-KMS drill temp prefix remains Task 7.2 because it belongs to the signing and evidence surface.

## Identity Contract

| Surface | Canonical identity |
|---|---|
| Prometheus metric prefix | `imperaos_` |
| Prometheus textfile | `.imperaos/metrics/imperaos.prom` |
| Qualification workspace | `/private/tmp/imperaos_soak_<run-id>` |
| Qualification launchd label | `com.imperaos.qualification-soak.<run-id>` |
| Qualification monitor title | `ImperaOS Qualification Soak Monitor` |
| macOS Ollama log | `/tmp/imperaos-ollama.log` |
| Governance demo payload | `/tmp/imperaos_v03_demo.json` |
| Computer-use gate temp identity | `imperaos_gate_`, `imperaos-gate-ascii`, `ImperaOS Gate Space` |
| Resilient-soak package copy | `imperaos` |

The eight exact metric names are:

1. `imperaos_approval_pending`
2. `imperaos_approval_oldest_age_seconds`
3. `imperaos_audit_inconsistency_total`
4. `imperaos_replay_verify_failure_total`
5. `imperaos_memory_conflict_total`
6. `imperaos_fallback_mode_total`
7. `imperaos_control_plane_agents_registered`
8. `imperaos_control_plane_claims_blocked`

## Components and Data Flow

`collect_metrics_snapshot()` continues to produce the existing JSON schema. `write_prometheus_textfile()` maps that schema to the same eight numeric series and writes the same newline-terminated text format; only the series prefix changes. Runtime configuration continues to provide the already-canonical `imperaos.prom` destination.

The resilient qualification launcher creates an ImperaOS-named isolated workspace, copies the canonical Python package, and invokes the supervised runner. The supervisor installs an ImperaOS launchd label. The watcher discovers the same workspace prefix and reports the canonical monitor title. The runbook example must agree with that path.

## Test Design

Follow RED-GREEN-REFACTOR:

1. Add `tests/test_observability_identity.py` before production edits.
2. Write an exact byte-for-byte snapshot assertion for the eight Prometheus lines using a deterministic in-memory metrics payload.
3. Assert the configured `.prom` filename is `imperaos.prom` under the ImperaOS state root.
4. Scan the active Task 7.1 files for constructed former-brand tokens and require every canonical operational identity.
5. Observe RED on the current metric and script consumers.
6. Apply only the mapped identity edits.
7. Run focused observability, runtime-path, integration-gate, and enterprise tests; lint the new test; syntax-check the modified Bash scripts.
8. Run the broader Python suite with temporary output kept inside the worktree and removed after verification. Use a short `C:\tmp\imperaos-*` root only if Windows path limits make that impossible, and remove it immediately afterward.
9. Run inventory at the committed implementation SHA and record remaining later-phase findings without weakening enforcement.

## Phase Boundaries

Task 7.1 does not change:

- managed-KMS, signing, evidence-pack, evidence-schema, or attestation identities; Task 7.2 owns them;
- historical release reports or evidence snapshots;
- legacy command examples elsewhere in broad documentation; later documentation cleanup owns them;
- metric JSON field names, runtime configuration schema, or compatibility behavior;
- external dashboards that are not present in this repository.

## Error and Safety Behavior

- Textfile writes retain their existing parent-directory creation and write-failure behavior.
- No fallback metric with the former prefix is emitted.
- Soak discovery and launcher prefixes change together, preventing split-brain workspace lookup.
- Shell control flow, cleanup traps, process supervision, and qualification evidence logic remain unchanged.
- No external monitoring system, launchd service, or long-running soak is started by this task.
- Verification must not leave test artifacts directly under `C:\`.

## Acceptance Criteria

- The emitted Prometheus snapshot contains exactly the eight canonical series and no former prefix.
- Runtime configuration still resolves to `.imperaos/metrics/imperaos.prom`.
- Active Task 7.1 scripts contain no former product identity.
- Launcher, watcher, supervisor, log, demo, and integration-gate paths agree on ImperaOS.
- The resilient launcher copies the existing `imperaos` package.
- The active runbook soak example uses `/private/tmp/imperaos_soak_...`.
- Focused tests, Ruff, Bash syntax validation, and the applicable Python regression suite pass.
- Inventory and remaining Task 7.2/later-phase findings are recorded without changing the brand gate.

## Commit Boundary

The implementation commit subject must be exactly:

`refactor: publish observability under ImperaOS metrics`
