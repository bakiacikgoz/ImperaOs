# ImperaOS Security and Evidence Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move active security defaults and evidence-producing gates to ImperaOS identity without changing cryptographic algorithms, schemas, or fail-closed controls.

**Architecture:** Define one generic file-backed identity boundary for six consumers and add behavioral proofs for the default audit HMAC and generated operator text. Apply literal-only production changes, then run each consumer's existing behavioral suite.

**Tech Stack:** Python, pytest, Ruff, HMAC-SHA256, Ed25519, Pydantic evidence models

## Global Constraints

- Preserve `IMPERAOS_AUDIT_SECRET` and explicit environment override priority.
- Preserve HMAC-SHA256, Ed25519 derivation shape, KMS rotation/revocation, and integrity behavior.
- Preserve all serialized schema versions, purpose strings, field names, and evidence filenames.
- Do not modify historical evidence or broad documentation/fixtures.
- Do not contact or rename the GitHub repository; only prepare canonical text locally.
- Do not start external KMS, signing, monitoring, release, or remote Git operations.
- Do not create temporary data directly under `C:\`; clean every agent-owned temp root.
- The implementation commit subject must be exactly `refactor: secure evidence under ImperaOS identity`.

## File Structure

- `tests/test_security_evidence_identity.py`: generic former-brand scan and behavioral security/evidence identity contract.
- `imperaos/governance/redaction.py`: canonical audit development fallback.
- `scripts/prepare_enterprise_fixture.py`: canonical deterministic fixture seed namespace.
- `scripts/run_managed_kms_adapter_drill.py`: canonical temporary prefix.
- `scripts/run_memory_governance_gate.py`: canonical organization owner.
- `scripts/run_enterprise_workspace_pr_readiness_gate.py`: canonical prepared manual PR URL.
- `scripts/run_product_complete_closure_gate.py`: canonical product-complete PR summary.
- `.superpowers/sdd/task-7.2-report.md`: durable verification evidence.

---

### Task 1: Security and Evidence Identity Contract

**Files:**
- Create: `tests/test_security_evidence_identity.py`
- Modify: `imperaos/governance/redaction.py`
- Modify: `scripts/prepare_enterprise_fixture.py`
- Modify: `scripts/run_managed_kms_adapter_drill.py`
- Modify: `scripts/run_memory_governance_gate.py`
- Modify: `scripts/run_enterprise_workspace_pr_readiness_gate.py`
- Modify: `scripts/run_product_complete_closure_gate.py`

- [ ] **Step 1: Write the failing identity and behavior contract**

Create a test module that constructs former-brand tokens from fragments so the test itself does not add inventory findings. Require:

1. A parameterized generic casefolded scan over all six production/script files rejects both former product families anywhere in each file.
2. Exact canonical strings are present in their mapped consumers.
3. With `IMPERAOS_AUDIT_SECRET` deleted, `redact_audit_payload({"api_key": "secret-value"})` produces the HMAC-SHA256 digest calculated with `imperaos-dev-secret`.
4. With the environment variable set to a test key, the same function produces the digest calculated with the explicit key and differs from the fallback digest.
5. `build_remote_commands()` emits `https://github.com/bakiacikgoz/ImperaOS/pull/new/<branch>` and retains the existing forbidden-command safety assertions.
6. `render_pr_body()` emits `Product-complete closure gate for ImperaOS.` and no former brand.

Use pytest `tmp_path` for generated command text. Do not execute a remote command.

- [ ] **Step 2: Run RED and record exact failures**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_security_evidence_identity.py
```

Expected: the generic scans and canonical/behavior assertions fail on all six current consumers before production edits.

- [ ] **Step 3: Apply the six minimal identity replacements**

Make only these replacements:

```text
imperaos-dev-secret -> imperaos-dev-secret
imperaos-enterprise-fixture: -> imperaos-enterprise-fixture:
imperaos-managed-kms- -> imperaos-managed-kms-
owner="imperaos" -> owner="imperaos"
https://github.com/bakiacikgoz/ImperaOS -> https://github.com/bakiacikgoz/ImperaOS
Product-complete closure gate for ImperaOS / ImperaOS. -> Product-complete closure gate for ImperaOS.
```

Do not rename environment variables, schemas, purpose identifiers, JSON fields, evidence files, commands, or control flow.

- [ ] **Step 4: Run focused GREEN tests**

Run the new contract plus consumer suites:

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests/test_security_evidence_identity.py `
  tests/test_managed_kms_adapter_drill.py `
  tests/test_agent_enrollment_cli.py `
  tests/test_agent_enrollment_evidence.py `
  tests/test_control_plane_install_rehearsal.py `
  tests/test_control_plane_pilot_pack.py `
  tests/test_enterprise_workspace_cli.py `
  tests/test_enterprise_workspace_pr_readiness_gate.py `
  tests/test_product_complete_closure_gate.py `
  tests/test_memory_cli_v3.py
```

Use a short, verified `C:\tmp\imperaos-task-7-2-focus` basetemp only if Windows path length requires it and remove it afterward.

- [ ] **Step 5: Run static verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check `
  tests/test_security_evidence_identity.py `
  imperaos/governance/redaction.py `
  scripts/prepare_enterprise_fixture.py `
  scripts/run_managed_kms_adapter_drill.py `
  scripts/run_memory_governance_gate.py `
  scripts/run_enterprise_workspace_pr_readiness_gate.py `
  scripts/run_product_complete_closure_gate.py
.\.venv\Scripts\python.exe -m compileall -q imperaos/governance/redaction.py scripts
```

Expected: Ruff and compilation pass.

- [ ] **Step 6: Prove exact scope and commit**

Run the generic constructed-token scan over the six active files, `git diff --check`, and inspect the diff. Stage exactly the seven Task 1 files and commit:

```powershell
git commit -m "refactor: secure evidence under ImperaOS identity"
```

Expected: one regression test and six minimal production/script edits only.

---

### Task 2: Task 7.2 Verification Evidence

**Files:**
- Create: `.superpowers/sdd/task-7.2-report.md`

- [ ] **Step 1: Run committed-HEAD inventory**

Run the brand consistency gate in inventory mode into ignored `.superpowers/sdd/task-7.2-brand-inventory`. Verify `gitCommit` equals the Task 1 SHA and record all category/classification counts.

- [ ] **Step 2: Create the durable report**

Use these sections:

```markdown
# Task 7.2 Verification Report

## Scope
## Implementation Commit
## RED Evidence
## Audit HMAC and Environment Override
## Focused GREEN Evidence
## Static Verification
## Active Security and Evidence Scan
## Cryptographic and Schema Invariants
## Brand Inventory
## External-Action Boundary
## Temporary-Artifact Cleanup
## Final Status
```

Record exact commands/counts and explicitly state that no remote repository, KMS, signature service, PR, release, or monitoring system was changed or contacted.

- [ ] **Step 3: Verify and commit the report**

Cross-check SHA/counts with raw JSON, run `git diff --check`, commit only `.superpowers/sdd/task-7.2-report.md` using `docs: record task 7.2 verification`, and leave inventory ignored.

- [ ] **Step 4: Complete independent reviews**

Require spec and code-quality review of the implementation, followed by combined review of the implementation and report. Fix every Critical or Important finding with a regression. Record Minor findings in the SDD ledger. Final acceptance requires an explicit Ready decision for Phase 8.
