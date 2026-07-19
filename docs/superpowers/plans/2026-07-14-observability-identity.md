# ImperaOS Observability Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move active Prometheus series and operational runtime identities to ImperaOS without changing metric semantics, supervision behavior, or historical evidence.

**Architecture:** Lock the public textfile and active script identity in one Python regression contract. Rename all coupled launcher/watcher/supervisor consumers together, validate shell syntax, and keep managed-KMS/evidence work in Task 7.2.

**Tech Stack:** Python, pytest, Ruff, Bash, Prometheus textfile format

## Global Constraints

- Emit exactly eight metrics with the `imperaos_` prefix and no compatibility aliases.
- Preserve the metrics snapshot JSON schema and numeric values.
- Preserve `.imperaos/metrics/imperaos.prom` as the configured destination.
- Change launcher, watcher, and launchd identities atomically.
- Copy the canonical `imperaos` Python package in the isolated soak workspace.
- Do not edit historical evidence or managed-KMS/signing identities.
- Do not start a soak, launchd job, Ollama, or an external monitoring system.
- Keep test artifacts out of the `C:\` root and remove temporary verification data.
- The implementation commit subject must be exactly `refactor: publish observability under ImperaOS metrics`.

## File Structure

- `tests/test_observability_identity.py`: exact Prometheus snapshot and active operational identity contract.
- `imperaos/enterprise/observability.py`: canonical metric series names.
- `scripts/launch_resilient_qualification_soak.sh`: canonical workspace and package copy.
- `scripts/run_qualification_soak_supervised.sh`: canonical launchd label.
- `scripts/watch_qualification_soak.sh`: canonical discovery, help, example, and monitor title.
- `scripts/bootstrap_macos.sh`: canonical Ollama log path.
- `scripts/demo_governance_v03.sh`: canonical demo payload path.
- `scripts/evaluate_computer_use_integration_gate.py`: canonical temporary gate identities.
- `docs/OPERATIONS_RUNBOOK.md`: canonical active soak example.
- `.superpowers/sdd/task-7.1-report.md`: durable verification evidence.

---

### Task 1: Observability and Operational Identity Contract

**Files:**
- Create: `tests/test_observability_identity.py`
- Modify: `imperaos/enterprise/observability.py`
- Modify: `scripts/launch_resilient_qualification_soak.sh`
- Modify: `scripts/run_qualification_soak_supervised.sh`
- Modify: `scripts/watch_qualification_soak.sh`
- Modify: `scripts/bootstrap_macos.sh`
- Modify: `scripts/demo_governance_v03.sh`
- Modify: `scripts/evaluate_computer_use_integration_gate.py`
- Modify: `docs/OPERATIONS_RUNBOOK.md`

**Interfaces:**
- Consumes: `write_prometheus_textfile()`, the runtime observability path, qualification launcher/supervisor/watcher scripts, and active operator documentation.
- Produces: canonical Prometheus output and consistent ImperaOS operational identities.

- [ ] **Step 1: Write the failing regression contract**

Create a deterministic snapshot dictionary containing all fields used by `write_prometheus_textfile()`. Call it with pytest's `tmp_path` and assert the exact newline-terminated output:

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

Also require:

- the resolved enterprise Prometheus path ends in `.imperaos/enterprise/metrics/imperaos.prom`;
- every active Task 7.1 file is free of constructed former-brand tokens;
- each mapped canonical path, title, label, and package copy occurs in its expected file;
- the managed-KMS drill is not included in this contract.

- [ ] **Step 2: Run RED and record exact failures**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_observability_identity.py
```

Expected: the Prometheus snapshot and active operational identity checks fail before production edits; the already-canonical runtime path assertion passes.

- [ ] **Step 3: Rename metric series without changing values**

In `write_prometheus_textfile()`, replace only the eight `imperaos_` prefixes with `imperaos_`. Preserve ordering, keys, whitespace, newline termination, directory creation, and return value.

- [ ] **Step 4: Rename all coupled active operational identities**

Apply these exact mappings:

```text
/private/tmp/imperaos_soak_ -> /private/tmp/imperaos_soak_
imperaos_soak_* -> imperaos_soak_*
com.imperaos.qualification-soak. -> com.imperaos.qualification-soak.
ImperaOS Qualification Soak Monitor -> ImperaOS Qualification Soak Monitor
copy_item "imperaos" -> copy_item "imperaos"
/tmp/imperaos-ollama.log -> /tmp/imperaos-ollama.log
/tmp/imperaos_v03_demo.json -> /tmp/imperaos_v03_demo.json
imperaos_gate_ -> imperaos_gate_
imperaos-gate-ascii -> imperaos-gate-ascii
ImperaOS Gate Space -> ImperaOS Gate Space
```

Update the matching active runbook soak example. Do not change control flow or evidence contents.

- [ ] **Step 5: Run focused GREEN tests and lint**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_observability_identity.py `
  tests/test_runtime_paths.py `
  tests/test_computer_use_integration_gate.py `
  tests/test_enterprise_cli.py `
  tests/test_enterprise_qualification.py
.\.venv\Scripts\python.exe -m ruff check tests/test_observability_identity.py imperaos/enterprise/observability.py scripts/evaluate_computer_use_integration_gate.py
```

Expected: all selected tests and Ruff pass.

- [ ] **Step 6: Validate every modified Bash script**

Run Git Bash `bash -n` for the five modified shell scripts:

```text
scripts/launch_resilient_qualification_soak.sh
scripts/run_qualification_soak_supervised.sh
scripts/watch_qualification_soak.sh
scripts/bootstrap_macos.sh
scripts/demo_governance_v03.sh
```

Expected: every file exits zero.

- [ ] **Step 7: Run the applicable broader regression suite**

Run pytest with `--basetemp` under an ignored worktree-local directory. If Windows path length prevents the full run, use a verified `C:\tmp\imperaos-task-7-1` child, remove that child after the run, and record the exception. Do not create direct `C:\p*` or `C:\t` directories.

- [ ] **Step 8: Verify exact scope and commit**

Construct former tokens at runtime and scan only the Task 7.1 active files. Confirm the managed-KMS file is unchanged, run `git diff --check`, stage exactly Task 1 files, and commit:

```powershell
git commit -m "refactor: publish observability under ImperaOS metrics"
```

---

### Task 2: Task 7.1 Verification Evidence

**Files:**
- Create: `.superpowers/sdd/task-7.1-report.md`

- [ ] **Step 1: Run committed-HEAD inventory**

Run the brand consistency gate in inventory mode against the implementation SHA. Record scanned-file and finding counts, including remaining Task 7.2/later-phase findings.

- [ ] **Step 2: Create the durable report**

Use these sections:

```markdown
# Task 7.1 Verification Report

## Scope
## Implementation Commit
## RED Evidence
## Prometheus Snapshot
## Focused GREEN Evidence
## Bash Syntax
## Broader Python Regression
## Active Operational Identity Scan
## Brand Inventory
## Task 7.2 Boundary
## Temporary-Artifact Cleanup
## Final Status
```

State actual counts and commands. Explicitly say no soak, launchd job, external monitoring update, or Ollama service was started.

- [ ] **Step 3: Verify and commit the report**

Cross-check the report SHA and counts against inventory JSON, run `git diff --check`, commit only the durable report with subject `docs: record task 7.1 verification`, and leave generated inventory ignored.

- [ ] **Step 4: Complete two-stage review**

Require independent spec and quality review of the implementation and report. Fix every Critical or Important issue with a focused regression, re-run verification, and request final readiness review for Task 7.2. Record any Minor findings in the SDD progress ledger.
