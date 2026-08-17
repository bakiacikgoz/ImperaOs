# Codex Sidebar Parity Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Match the supplied Codex desktop sidebar proportions and hierarchy while preserving all real ImperaOS product behavior and publishing the complete current integration branch.

**Architecture:** The frozen UI Lab stylesheet remains immutable. Product-only visual overrides live in `styles/shell.css`; semantic component hooks live in `Sidebar.tsx`; width defaults, clamping, and persisted migration live in the Zustand preference store. Tests assert consumer-visible state and computed browser behavior rather than source text.

**Tech Stack:** React 19, TypeScript, Zustand persist middleware, Vitest/Testing Library, Playwright, CSS, Tauri/Rust.

---

### Task 1: Lock the sidebar width contract with failing tests

**Files:**
- Create: `apps/operator-panel/src/product-shell/state/productShellStore.test.ts`
- Modify: `apps/operator-panel/src/product-shell/state/productShellStore.ts`

- [ ] Add tests proving a fresh store uses `260px`, live resize clamps to `220–340px`, and persisted migration preserves in-range widths but resets oversized legacy widths to `260px`.
- [ ] Run the targeted test and confirm it fails for the expected old `300px`/`240–420px` behavior.
- [ ] Add exported pure width helpers plus Zustand persist version/migration wiring.
- [ ] Re-run the targeted test and confirm it passes.

### Task 2: Add semantic sidebar states with failing component tests

**Files:**
- Modify: `apps/operator-panel/src/product-shell/shell/Sidebar.test.tsx`
- Modify: `apps/operator-panel/src/product-shell/shell/Sidebar.tsx`

- [ ] Add a test proving the root action has a dedicated semantic class and a desktop-runtime failure renders as a compact truthful preview notice.
- [ ] Run the component test and confirm it fails for the missing semantic hooks.
- [ ] Add the minimal component classes/status wrapper without changing routes or governed mutation behavior.
- [ ] Re-run the component test and confirm it passes.

### Task 3: Implement product-scoped Codex parity styling

**Files:**
- Modify: `apps/operator-panel/src/product-shell/styles/shell.css`
- Modify: `apps/operator-panel/e2e/ui-lab-theme-parity.spec.ts`

- [ ] Add a browser test for computed `260px` width, bounded resize, distinct warm graphite surface, unflooded root-route state, and no horizontal overflow.
- [ ] Run the targeted E2E and confirm it fails against the old sidebar.
- [ ] Add a Hallmark-stamped, product-scoped semantic token block and sidebar geometry/hierarchy/state overrides.
- [ ] Add reduced-motion handling and retain focus-visible affordances.
- [ ] Re-run the targeted E2E and confirm it passes.

### Task 4: Perform live visual and interaction verification

**Files:**
- Verify: `apps/operator-panel/src/product-shell/shell/Sidebar.tsx`
- Verify: `apps/operator-panel/src/product-shell/styles/shell.css`

- [ ] Start or confirm the local Vite/Tauri project runtime.
- [ ] Inspect the in-app browser at desktop and narrow viewports.
- [ ] Compare proportions, surface separation, hierarchy, selected states, footer, and runtime notice to the supplied reference.
- [ ] Exercise collapse, search, navigation, and resize; correct any regression using another red-green cycle.

### Task 5: Run complete project verification

**Files:**
- Verify: entire worktree

- [ ] Run full Vitest and Playwright suites.
- [ ] Run build, lint, bridge parity, UI Lab frozen-theme verification, and diff whitespace checks.
- [ ] Run Rust formatting/tests and the Tauri launch smoke test.
- [ ] Review the full diff for accidental Artifact Workspace branch contamination or unrelated files.

### Task 6: Publish the complete integration branch

**Files:**
- Publish: all authorized changes in the current worktree

- [ ] Confirm GitHub CLI availability/authentication and the exact branch/remotes.
- [ ] Stage the entire authorized worktree and create one intentional integration commit.
- [ ] Push `codex/imperaos-ui-lab-full-integration-v1` to origin.
- [ ] Create or update the branch pull request and capture its URL, final SHA, changed top-level areas, and push result.
