# Artifact Workspace Final Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining rollout, fallback-editor, export, and release-truth requirements in the approved Artifact Workspace completion plan.

**Architecture:** Python resolves effective rollout and publishes a redacted per-kind capability snapshot. React uses existing artifact contracts, autosave, revision, conflict, asset, and native export boundaries while completing the bundled spreadsheet/canvas adapters and common export UI.

**Tech Stack:** Python 3.11+, Pydantic v2, React 19, TypeScript, Zod, Vitest, Playwright, Rust/Tauri.

## Global Constraints

- GitHub Actions must not be invoked in this run.
- Commercial Handsontable/tldraw capabilities remain fail-closed without verified production entitlement.
- Python remains artifact, rollout, revision, approval, policy, and export authority.
- Renderer flags may disable but never enable backend authority.
- No direct provider call, code execution, arbitrary path import, remote embed, or canonical browser storage.
- Use focused red-green tests and avoid duplicate or broad verification until final local gates.

---

### Task 1: Runtime rollout profiles and operator capability card

**Files:**
- Create: `imperaos/artifacts/rollout.py`
- Create: `apps/operator-panel/src/artifact-workspace/ui/ArtifactWorkspaceCapabilityCard.tsx`
- Modify: `imperaos/artifacts/runtime.py`
- Modify: `contracts/artifact_workspace/feature_flags.json`
- Modify: `apps/operator-panel/src/artifact-workspace/artifactContracts.ts`
- Modify: `apps/operator-panel/src/App.tsx`
- Test: `tests/test_artifact_feature_flags.py`
- Test: `apps/operator-panel/src/artifact-workspace/ui/ArtifactWorkspaceCapabilityCard.test.tsx`

**Interfaces:**
- Produces: `resolve_artifact_rollout_profile(name: str) -> dict[str, bool]`
- Produces: runtime `kindCapabilities` keyed by seven artifact kinds
- Consumes: existing effective feature flags and license booleans

- [ ] Write failing Python tests for the exact off/core/full profiles and detailed per-kind snapshot.
- [ ] Run `uv run --extra dev python -m pytest tests/test_artifact_feature_flags.py -q` and confirm the new assertions fail because profiles/kind capabilities are absent.
- [ ] Implement profile resolution and detailed snapshot without exposing environment or entitlement evidence.
- [ ] Write a failing component test for the dedicated card's global/runtime/export/kind/reason/adapter fields and secret redaction.
- [ ] Run the focused Vitest file and confirm the card import/render assertion fails.
- [ ] Implement the card and wire it into Settings using the handshake snapshot.
- [ ] Run only the two focused test files and confirm they pass.

### Task 2: Spreadsheet fallback completion

**Files:**
- Create: `apps/operator-panel/src/artifact-workspace/editors/spreadsheet/spreadsheetAdapter.ts`
- Create: `apps/operator-panel/src/artifact-workspace/editors/spreadsheet/spreadsheetAdapter.test.ts`
- Modify: `apps/operator-panel/src/artifact-workspace/editors/spreadsheet/SpreadsheetArtifactEditor.tsx`
- Test: `apps/operator-panel/src/artifact-workspace/editors/spreadsheet/SpreadsheetArtifactEditor.test.tsx`

**Interfaces:**
- Produces: bounded address/range parsing, range clearing, paste application, and visible row-window helpers
- Consumes: `SpreadsheetArtifactContent` and emits unchanged contract shape plus `ArtifactContextSelection`

- [ ] Write failing adapter tests for normalized ranges, clear/paste, sheet growth, and bounded virtual windows.
- [ ] Run the adapter test and observe failures for missing exports.
- [ ] Implement the pure adapter helpers.
- [ ] Write a failing editor test for range selection, copy/paste, clear selection, sheet add/rename, row/column growth, formula-disabled status, and a bounded DOM row count.
- [ ] Run the editor test and observe the missing controls/selection behavior.
- [ ] Implement the toolbar, range state, keyboard/pointer selection, and virtual row window.
- [ ] Run the two focused spreadsheet tests and the existing spreadsheet export tests.

### Task 3: Canvas fallback completion

**Files:**
- Modify: `apps/operator-panel/src/artifact-workspace/editors/canvas/canvasAdapter.ts`
- Modify: `apps/operator-panel/src/artifact-workspace/editors/canvas/canvasAdapter.test.ts`
- Modify: `apps/operator-panel/src/artifact-workspace/editors/canvas/CanvasArtifactEditor.tsx`
- Modify: `apps/operator-panel/src/artifact-workspace/editors/canvas/CanvasArtifactEditor.test.tsx`

**Interfaces:**
- Produces: bounded line-segment free draw and object deletion helpers using `CanvasContentV2`
- Consumes: existing strict canvas shape/asset model

- [ ] Write failing adapter tests for bounded free-draw segments and deletion of selected objects/assets references.
- [ ] Run the adapter test and confirm missing helper failures.
- [ ] Implement the helpers while retaining the shape and remote-content allowlists.
- [ ] Write a failing editor test for draw mode, delete selection, outline selection, undo/redo, zoom/pan, and local image import.
- [ ] Run the editor test and observe missing draw/delete behavior.
- [ ] Implement the focused UI behavior without changing the artifact schema.
- [ ] Run the focused canvas adapter/editor/export tests.

### Task 4: Common export dialog and complete format matrix

**Files:**
- Create: `apps/operator-panel/src/artifact-workspace/artifactFormExport.ts`
- Create: `apps/operator-panel/src/artifact-workspace/artifactFormExport.test.ts`
- Create: `apps/operator-panel/src/artifact-workspace/artifactExportFormats.ts`
- Create: `apps/operator-panel/src/artifact-workspace/artifactExportFormats.test.ts`
- Modify: `imperaos/artifacts/exports.py`
- Modify: `tests/test_artifact_export_boundary.py`
- Modify: `apps/operator-panel/src/artifact-workspace/artifactDocumentExport.ts`
- Modify: `apps/operator-panel/src/artifact-workspace/artifactCodeExport.ts`
- Modify: `apps/operator-panel/src/artifact-workspace/artifactSlidesExport.ts`
- Modify: `apps/operator-panel/src/artifact-workspace/useAssistantArtifactWorkspaceController.ts`
- Modify: `apps/operator-panel/src/artifact-workspace/ui/ArtifactExportDialog.tsx`
- Modify: `apps/operator-panel/src/components/assistant/AssistantWorkbench.tsx`
- Modify: `apps/operator-panel/src/App.tsx`
- Test: focused exporter/dialog/workbench/controller tests

**Interfaces:**
- Produces: one seven-kind `artifactExportFormats` matrix
- Produces: dialog request carrying format and optional spreadsheet sheet ID
- Consumes: saved active tab and memory-only form session snapshot

- [ ] Write failing backend tests for the exact format matrix and canonical basenames.
- [ ] Run the focused backend export-boundary test and observe missing formats.
- [ ] Extend allowed formats without weakening ticket/path authority.
- [ ] Write failing TypeScript serializer tests for document JSON, form schema/submission/CSV, code TXT, and slides JSON.
- [ ] Run the focused exporter tests and observe missing APIs.
- [ ] Implement serializers and controller actions through begin/cancel/commit.
- [ ] Write failing dialog/workbench tests for the complete matrix and required metadata fields.
- [ ] Run the focused UI tests and observe the missing dialog/fields.
- [ ] Wire the common dialog to the active saved revision and remove duplicated direct export button groups.
- [ ] Run the focused export, dialog, controller, and workbench tests.

### Task 5: Release and documentation truth

**Files:**
- Modify: `scripts/run_artifact_workspace_release_gate.py`
- Modify: `tests/test_artifact_workspace_release_gate.py`
- Modify: `docs/ARTIFACT_WORKSPACE_OPERATOR_GUIDE.md`
- Modify: `docs/ARTIFACT_WORKSPACE_RELEASE_GATE.md`
- Modify: `docs/ARTIFACT_WORKSPACE_ARCHITECTURE.md`
- Modify: `contracts/artifact_workspace/feature_flags.json`

**Interfaces:**
- Produces: license report with separate `commercialCapabilities` and `fallbackCapabilities`
- Consumes: fallback capability contract and rollout profiles from Task 1

- [ ] Write a failing release-gate test proving commercial editors remain off while bundled fallback capabilities are available.
- [ ] Run the focused release-gate test and observe the old forced-off-only assertion.
- [ ] Update the license gate report and no-ship logic.
- [ ] Update operator/release/architecture documentation to match the effective fallback and rollback behavior.
- [ ] Run focused release-gate tests and `git diff --check`.

### Task 6: Local completion verification

**Files:** No production files expected.

**Interfaces:** Consumes the integrated branch result.

- [ ] Run the plan's minimum local Ruff, Python, frontend test/lint/build, Rust, and diff checks once.
- [ ] Run `uv run --extra dev python scripts/run_artifact_workspace_release_gate.py --gate workspace-release --profile enterprise --json` once on the final candidate.
- [ ] Inspect `artifacts/artifact-workspace-release/NO_SHIP_REGISTER.md` and require `- none`.
- [ ] Confirm clean worktree, current `origin/main` ancestry, backup branch, and PR metadata without invoking or rerunning GitHub Actions.
