# Artifact Phase 20 Governed AI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver policy-aware artifact selection/context, exactly five public assistant tools, verified proposal approval/apply, and interactive inline artifact parts without renderer secrets or raw full-artifact prompts.

**Architecture:** Python remains authority for context projection, policy, approvals, tools, idempotency, and provenance. Tauri exposes typed RPC only; React stores coordinate selections and opaque IDs, renders bounded cards, and never owns provider credentials or approval truth.

**Tech Stack:** Python 3.14, Pydantic v2, SQLite, Typer/RPC; React 19, TypeScript, Zod, assistant-ui; Rust/Tauri bridge.

## Global Constraints

- Public tool allowlist is exactly `artifact.create_draft`, `artifact.get_context`, `artifact.propose_mutation`, `artifact.request_form`, `artifact.request_export`.
- Full artifact content is never provider context by default; projections are bounded, redacted, classified, purpose-bound, and hashed.
- Renderer booleans cannot approve mutations. Approval is fresh, workspace/principal/action-hash bound, single-use backend state.
- Provider secrets and raw entitlement/approval material never enter renderer state, localStorage, logs, evidence, or support bundles.
- Unknown tools, mutation types, selection shapes, and unverified approvals fail closed.

---

### Task 1: Renderer secret boundary

**Files:** `apps/operator-panel/src/settings.ts`, `apps/operator-panel/src/bridge.ts`, their focused tests.

- [ ] Add a failing renderer-boundary test proving provider keys are absent from persisted settings and bridge payloads and legacy keys are removed.
- [ ] Run the focused test and observe the expected secret-field failure.
- [ ] Move provider credential resolution behind the trusted native/backend boundary; keep renderer configuration non-secret.
- [ ] Run the focused tests, TypeScript, and ESLint.

### Task 2: Typed selection and backend context pack

**Files:** create `imperaos/artifacts/context.py`, `tests/test_artifact_context.py`, `tests/test_artifact_privacy.py`, `apps/operator-panel/src/artifact-workspace/selectionContext.ts`, `selectionContext.test.ts`, `ui/ArtifactSelectionChip.tsx` and test; modify editor host/controller/workbench.

- [ ] Write failing Python tests for strict seven-kind selection unions, revision binding, redaction, 32 KiB/8k-token budget, no-full-default, data class, purpose, allowed scope, and SHA-256.
- [ ] Write failing TypeScript tests for coordinate-only selection persistence and visible bounded chip rendering.
- [ ] Implement `ArtifactContextBuilder.build(request, context) -> ArtifactContextPack` and strict TS selection schemas.
- [ ] Run only the new Python/TypeScript context tests, TypeScript, and ESLint.

### Task 3: Verified proposal approval and provenance

**Files:** modify artifact commands/results/migrations/store/service/policy/evidence/RPC/contracts; focused service/evidence tests.

- [ ] Write failing tests proving apply rejects renderer booleans, missing/stale/wrong-workspace/wrong-principal/wrong-action approvals, re-use, and full-request idempotency mismatch.
- [ ] Add backend approval tickets bound to proposal ID, action hash, workspace, approver, expiry, and single-use status; remove `approvalGranted` authority.
- [ ] Persist proposal request hash, context/selection hashes, session/turn/trace, approval ID/action hash/approver, and apply principal.
- [ ] Generate schemas; run proposal/service/evidence/RPC/contract tests and Ruff.

### Task 4: Exact public tool registry

**Files:** create `imperaos/artifacts/tools.py`, `tests/test_artifact_tool_registry.py`, update assistant/native RPC integration.

- [ ] Write a failing registry test for the exact five public names and deny unknown/internal model-visible tools.
- [ ] Implement strict input/output models and handlers that route side effects through draft/proposal/form/export request boundaries.
- [ ] Run the focused registry, policy, service, RPC, and contract tests.

### Task 5: Inline artifact/proposal/form parts

**Files:** create `ArtifactProposalCard.tsx`, `ArtifactSelectionChip.tsx`, focused CSS/tests; modify assistant mappers/runtime/workbench/controller.

- [ ] Write failing tests for artifact open, proposal review/approve/reject/failure, form submit state, keyboard/a11y labels, and no raw JSON primary UI.
- [ ] Implement typed parts and bridge calls using opaque proposal/approval IDs only.
- [ ] Run focused Vitest, TypeScript, ESLint, and the one Phase 20 Playwright journey.

### Task 6: Phase gate and review

- [ ] Run the bounded impacted Python, frontend, Rust bridge, contract, and privacy tests.
- [ ] Run `git diff --check` and reviewer reread; close every P0/P1.
- [ ] Commit Phase 20 atomically before Phase 21.
