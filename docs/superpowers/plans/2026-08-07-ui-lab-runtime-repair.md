# UI Lab Runtime Repair Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Repair the v2 product shell's governed workspace, terminal, new-conversation, model-selection, and soft-archive flows without weakening desktop security boundaries.

**Architecture:** Keep browser preview fail-closed and repair the existing desktop contracts at their boundaries: idempotent workspace state, shared RPC protocol registration, canonical conversation identity, normalized model provider identity, and safe archive navigation. Use focused TypeScript and Rust tests for each boundary, followed by a launched-desktop lifecycle proof.

**Tech Stack:** React 19, TypeScript, Zustand, React Router, Tauri 2, Rust, Vitest, Playwright, portable-pty.

## Global Constraints

- Approved conversation-removal behavior is soft archive; no task, message, or link is permanently deleted.
- Retain trusted artifact identity, origin policy, project-folder tickets, mutation idempotency, and native-only capability boundaries.
- Browser preview must describe unavailable native capability; it must never fabricate terminal, browser, files, data, project, or task results.
- Do not alter frozen UI Lab theme files.
- Preserve unrelated root-checkout state: `apps/operator-panel/src-tauri/Cargo.toml` line endings and `.codegraph/`, `.codex-remote-attachments/`, `.pnpm-store/` are not owned by this plan.
- Use user-visible Codex task worktrees for implementation. Do not merge, push, or create Git history without explicit user authorization.

---

## File map

- `src/product-shell/workspace/ProductArtifactWorkspace.tsx`: idempotent artifact surface opening.
- `src/product-shell/workspace/workspaceTabState.ts` and its tests: valid active-tab invariant.
- `src-tauri/src/artifact_rpc.rs` and bridge tests: bounded product-workspace RPC allowlist contract.
- `src/product-shell/pages/NewWorkPage.tsx`, `src/assistant/useAssistantRuntimeSession.ts`, and tests: canonical assistant-session creation.
- `src/components/assistant/AssistantModelPicker.tsx`, `src/assistant/useAssistantModels.ts`, and tests: normalized provider/model selection.
- `src/product-shell/shell/Sidebar.tsx`, `src/product-shell/pages/TaskPage.tsx`, `src/product-shell/state/productShellStore.ts`, and tests: soft archive selection and route fallback.
- `src/product-shell/ProductShellApp.tsx` plus a small readiness module/tests: desktop readiness propagation and root error reporting.
- `scripts/tauri-launched-smoke.ts`, Tauri/Playwright tests: end-to-end evidence.

### Task 1: Make workspace opening and selection idempotent

**Files:**
- Modify: `apps/operator-panel/src/product-shell/workspace/ProductArtifactWorkspace.tsx:36-38`
- Modify: `apps/operator-panel/src/product-shell/workspace/workspaceTabState.ts:active-tab selection helpers`
- Modify/Test: `apps/operator-panel/src/product-shell/workspace/WorkspaceTabs.test.tsx`
- Create/Test: `apps/operator-panel/src/product-shell/workspace/ProductArtifactWorkspace.test.tsx`

**Interfaces:**
- Consumes: `openRequest: number`, `workspace.open`, controller `open()` and `toggle()` actions.
- Produces: positive open requests are idempotent; a nonempty tab set always yields a valid active tab ID.

- [ ] **Step 1: Write failing StrictMode and invalid-active-tab tests**

```tsx
it('keeps an artifact workspace open when StrictMode replays its effect', async () => {
  render(<StrictMode><ProductArtifactWorkspace state={state} openRequest={1} /></StrictMode>);
  expect(await screen.findByLabelText('Assistant workbench')).toBeVisible();
  expect(actions.open).toHaveBeenCalled();
  expect(actions.toggle).not.toHaveBeenCalled();
});

it('recovers a missing active tab to a remaining tab', () => {
  expect(resolveActiveWorkspaceTabId([terminalTab], 'missing')).toBe(terminalTab.id);
});
```

- [ ] **Step 2: Run the focused tests and observe failure**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/workspace/WorkspaceTabs.test.tsx src/product-shell/workspace/ProductArtifactWorkspace.test.tsx`

Expected: FAIL because the current effect calls `toggle()` and a missing active ID resolves to `null`.

- [ ] **Step 3: Implement the smallest invariant-preserving change**

Replace the positive-request `toggle()` call with the controller's idempotent `open()` action. Add a pure active-ID resolver used by tab creation, hydration, close, and render selection so a nonempty list chooses the first valid tab when persisted state is invalid.

- [ ] **Step 4: Run the focused tests and verify pass**

Run the command from Step 2. Expected: PASS with StrictMode replay and invalid active IDs covered.

- [ ] **Step 5: Record the verified patch for MAIN review**

Do not commit automatically. Return the changed-file list, test exit, and exact worktree revision to MAIN.

### Task 2: Align product-workspace RPC registration with the allowlist

**Files:**
- Modify: `apps/operator-panel/src-tauri/src/artifact_rpc.rs:19-...`
- Modify/Test: `apps/operator-panel/src-tauri/src/artifact_rpc.rs` tests or its focused sibling test module
- Review: `apps/operator-panel/src-tauri/src/bridge.rs:product workspace handlers`

**Interfaces:**
- Consumes: renderer method names emitted by `ProductWorkspaceClient`.
- Produces: an exact allowlist for `project.register`, `project.update`, `project.archive`, `task.get`, `task.update`, `task.archive`, `task.link.list`, and any remaining frontend-reachable product method; nonlisted methods remain rejected.

- [ ] **Step 1: Write a failing method-contract test**

```rust
#[test]
fn product_workspace_methods_are_allowlisted_but_unknown_methods_are_rejected() {
    for method in ["project.register", "project.update", "project.archive", "task.get", "task.update", "task.archive", "task.link.list"] {
        assert!(build_trusted_request(method, json!({}), &identity(), Some("key-1".into()), 15_000).is_ok());
    }
    assert!(build_trusted_request("task.delete", json!({}), &identity(), None, 15_000).is_err());
}
```

- [ ] **Step 2: Run the focused Rust test and observe failure**

Run: `cargo test -p imperaos_operator_panel product_workspace_methods_are_allowlisted_but_unknown_methods_are_rejected`

Expected: FAIL for currently unlisted frontend methods and PASS for `task.delete` rejection.

- [ ] **Step 3: Add only contract-backed methods to the allowlist**

Add the frontend-reachable product method names, retaining the existing envelope-bound idempotency requirement for mutations and trusted identity filtering. Do not add destructive permanent-delete methods.

- [ ] **Step 4: Run the focused Rust test and bridge tests**

Run: `cargo test -p imperaos_operator_panel product_workspace_methods_are_allowlisted_but_unknown_methods_are_rejected`

Expected: PASS; unknown methods remain protocol mismatches.

- [ ] **Step 5: Record the verified patch for MAIN review**

Do not commit automatically. Return changed Rust files, command exit, and exact worktree revision.

### Task 3: Preserve one canonical assistant session during New Work

**Files:**
- Modify: `apps/operator-panel/src/product-shell/pages/NewWorkPage.tsx:submit handler`
- Modify: `apps/operator-panel/src/assistant/useAssistantRuntimeSession.ts:runtime selection`
- Modify/Test: `apps/operator-panel/src/product-shell/pages/NewWorkPage.test.tsx`
- Modify/Test: `apps/operator-panel/src/assistant/useAssistantSession.test.tsx`

**Interfaces:**
- Consumes: generated `assistantSessionId`, `createTask`, `addMessage`, navigation state.
- Produces: the persisted task ID and active assistant runtime use the identical session ID; failed initial-message writes never navigate or select an incomplete task.

- [ ] **Step 1: Write failing canonical-session and message-failure tests**

```tsx
it('initializes the active assistant runtime with the persisted task session', async () => {
  renderNewWork();
  await user.click(screen.getByRole('button', { name: 'Başlat' }));
  expect(navigate).toHaveBeenCalledWith(expect.stringMatching(/task-/), expect.objectContaining({ state: expect.objectContaining({ initialSessionId: 'product-session-1' }) }));
});

it('does not navigate or select a task when the initial message fails', async () => {
  addMessage.mockRejectedValueOnce(new Error('message failed'));
  renderNewWork();
  await user.click(screen.getByRole('button', { name: 'Başlat' }));
  expect(navigate).not.toHaveBeenCalled();
  expect(screen.getByRole('alert')).toHaveTextContent('message failed');
});
```

- [ ] **Step 2: Run New Work/session tests and observe failure**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/pages/NewWorkPage.test.tsx src/assistant/useAssistantSession.test.tsx`

Expected: FAIL for the legacy runtime's second session identity and early navigation path.

- [ ] **Step 3: Implement canonical propagation and failure containment**

Pass the durable `assistantSessionId` through both runtime implementations. Keep the draft page selected until `createTask` and `addMessage` complete; display a typed error on failure and avoid store/route updates for incomplete work.

- [ ] **Step 4: Run the focused tests and verify pass**

Run the command from Step 2. Expected: PASS with one session ID and no premature navigation.

- [ ] **Step 5: Record the verified patch for MAIN review**

Do not commit automatically. Return changed files, test exit, and exact worktree revision.

### Task 4: Normalize discovered provider identity and availability

**Files:**
- Modify: `apps/operator-panel/src/components/assistant/AssistantModelPicker.tsx:17-155`
- Modify: `apps/operator-panel/src/assistant/useAssistantModels.ts:flattening/normalization seam`
- Modify/Test: `apps/operator-panel/src/components/assistant/AssistantModelPicker.test.tsx`
- Modify/Test: `apps/operator-panel/src/assistant/useAssistantModels.test.tsx`

**Interfaces:**
- Consumes: legacy setting values (`ollama`, `transformers`) and discovered providers (`local-ollama`, `local-transformers`).
- Produces: canonical discovered provider IDs, only available/installed model options, and unchanged canonical runtime settings for the Tauri bridge.

- [ ] **Step 1: Write failing alias and disabled-model tests**

```tsx
it('maps legacy ollama settings to the discovered local-ollama provider', () => {
  renderPicker({ assistantProvider: 'ollama' }, discoveryWithLocalOllama);
  expect(screen.getByRole('combobox', { name: 'Assistant model' })).toHaveDisplayValue('qwen3.5:4b');
});

it('does not make unavailable or uninstalled models selectable', () => {
  renderPicker({ assistantProvider: 'local-ollama' }, discoveryWithUnavailableModel);
  expect(screen.getByRole('option', { name: /offline model/i })).toBeDisabled();
});
```

- [ ] **Step 2: Run picker/discovery tests and observe failure**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/components/assistant/AssistantModelPicker.test.tsx src/assistant/useAssistantModels.test.tsx`

Expected: FAIL because equality filtering separates `ollama` from `local-ollama` and model availability is not enforced.

- [ ] **Step 3: Implement canonical provider normalization**

Derive a canonical selected provider from discovery aliases before filtering models. Render discovered provider records rather than synthetic available legacy substitutes, preserve unavailable reasons, and disable model options where `available === false` or `installed === false`.

- [ ] **Step 4: Run focused tests and verify pass**

Run the command from Step 2. Expected: PASS with aliases, disabled reasons, and canonical runtime values covered.

- [ ] **Step 5: Record the verified patch for MAIN review**

Do not commit automatically. Return changed files, test exit, and exact worktree revision.

### Task 5: Complete the approved soft-archive lifecycle

**Files:**
- Modify: `apps/operator-panel/src/product-shell/shell/Sidebar.tsx:archive callback`
- Modify: `apps/operator-panel/src/product-shell/state/productShellStore.ts:selected task actions`
- Modify: `apps/operator-panel/src/product-shell/pages/TaskPage.tsx:archived task fallback`
- Modify/Test: `apps/operator-panel/src/product-shell/shell/Sidebar.test.tsx`
- Modify/Test: `apps/operator-panel/src/product-shell/pages/TaskPage.test.tsx`

**Interfaces:**
- Consumes: `archiveTask(taskId, reason)` returning the archived task and current selected task/route.
- Produces: archived task omitted from active sidebar, selected archived task cleared, and navigation to `/` or the owning project's safe active task. Archived data remains retrievable only through its explicit archived context.

- [ ] **Step 1: Write failing archive-success, archive-failure, and selected-route tests**

```tsx
it('clears the selected archived task and routes to New Work', async () => {
  renderSidebarWithSelectedTask('task-1');
  await user.click(screen.getByRole('button', { name: 'Archive Task 1' }));
  expect(selectTask).toHaveBeenCalledWith(null);
  expect(navigate).toHaveBeenCalledWith('/');
  expect(screen.queryByText('Task 1')).not.toBeInTheDocument();
});

it('keeps selection and row on archive failure', async () => {
  archiveTask.mockRejectedValueOnce(new WorkspaceError('ARCHIVE_FAILED', 'Denied', false));
  renderSidebarWithSelectedTask('task-1');
  await user.click(screen.getByRole('button', { name: 'Archive Task 1' }));
  expect(selectTask).not.toHaveBeenCalledWith(null);
  expect(screen.getByText('Task 1')).toBeVisible();
});
```

- [ ] **Step 2: Run sidebar/task tests and observe failure**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/shell/Sidebar.test.tsx src/product-shell/pages/TaskPage.test.tsx`

Expected: FAIL because the current archive path keeps `selectedTaskId` and the task route.

- [ ] **Step 3: Implement post-success archive cleanup only**

After a successful archive response, upsert the returned archived task, clear matching selection, and navigate. Do not mutate the store or route when the bridge fails. Keep soft-archive terminology and never call a permanent delete API.

- [ ] **Step 4: Run focused tests and verify pass**

Run the command from Step 2. Expected: PASS for success, failure, and direct archived-route fallback.

- [ ] **Step 5: Record the verified patch for MAIN review**

Do not commit automatically. Return changed files, test exit, and exact worktree revision.

### Task 6: Introduce shared desktop readiness and typed bridge errors

**Files:**
- Create: `apps/operator-panel/src/product-shell/nativeReadiness.ts`
- Modify: `apps/operator-panel/src/product-shell/adapters/productWorkspaceClient.ts:31-61`
- Modify: `apps/operator-panel/src/product-shell/pages/NewWorkPage.tsx`
- Modify: `apps/operator-panel/src/product-shell/shell/Sidebar.tsx`
- Modify: `apps/operator-panel/src/product-shell/terminal/TerminalSurface.tsx`
- Modify/Test: `apps/operator-panel/src/product-shell/adapters/productWorkspaceClient.test.ts`
- Create/Test: `apps/operator-panel/src/product-shell/nativeReadiness.test.ts`

**Interfaces:**
- Consumes: desktop bridge presence and typed Tauri error envelope `{ code, message, retryable }`.
- Produces: `NativeReadiness { ready: boolean; reason?: string }` and `WorkspaceError` retaining code/retryability for UI alerts and disabled controls.

- [ ] **Step 1: Write failing readiness and typed-error tests**

```ts
it('marks the browser preview as desktop-runtime unavailable', () => {
  expect(resolveNativeReadiness(undefined)).toEqual({ ready: false, reason: 'Workspace data requires the ImperaOS desktop runtime.' });
});

it('retains native envelope code and retryability', async () => {
  invoke.mockResolvedValueOnce({ ok: false, data: null, error: { code: 'ARTIFACT_RPC_UNAVAILABLE', message: 'Offline', retryable: true } });
  await expect(productWorkspaceClient.listProjects()).rejects.toMatchObject({ code: 'ARTIFACT_RPC_UNAVAILABLE', retryable: true });
});
```

- [ ] **Step 2: Run readiness/client tests and observe failure**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/adapters/productWorkspaceClient.test.ts src/product-shell/nativeReadiness.test.ts`

Expected: FAIL because errors are converted to generic `Error` values and New Work/launch controls lack one readiness source.

- [ ] **Step 3: Implement one truthful readiness and error boundary**

Create a pure readiness resolver, consume it from creation and native launch controls, and introduce a typed `WorkspaceError`. Preserve existing role=alert feedback, add a root v2 error boundary, and leave browser preview fail-closed.

- [ ] **Step 4: Run focused tests and verify pass**

Run the command from Step 2. Expected: PASS with disabled controls and typed codes/retryability.

- [ ] **Step 5: Record the verified patch for MAIN review**

Do not commit automatically. Return changed files, test exit, and exact worktree revision.

### Task 7: Prove the repaired desktop lifecycle

**Files:**
- Modify: `apps/operator-panel/scripts/tauri-launched-smoke.ts`
- Create/Test: `apps/operator-panel/e2e/product-workspace-lifecycle.spec.ts`
- Modify/Test: `apps/operator-panel/src-tauri/src/terminal.rs` test module if the PTY reader must be released before `child.wait()`

**Interfaces:**
- Consumes: repaired workspace, bridge, task, model, archive, and terminal contracts.
- Produces: a real launched-desktop proof of terminal IPC, project/task create/archive, workspace tab opening, and persisted archive behavior.

- [ ] **Step 1: Write failing launched-smoke assertions**

```ts
expect(await bridge.productTaskCreate(payload)).toMatchObject({ taskId: expect.any(String) });
await terminal.start({ rootRef, cols: 80, rows: 24 });
await terminal.write(sessionId, 'echo imperaos\n');
await expect(terminal.output(sessionId)).resolves.toContain('imperaos');
await bridge.productTaskArchive(taskId, 'user_archive');
```

- [ ] **Step 2: Run the launch test and observe failure**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel tauri:smoke:launch`

Expected: FAIL until the smoke harness invokes the real bridge/terminal contract rather than treating a live process as sufficient evidence.

- [ ] **Step 3: Implement explicit lifecycle probes and PTY teardown discipline**

Make launched smoke require bridge calls and terminal output/status. If the Rust test hangs, release the PTY reader before waiting for the child, matching portable-pty lifecycle discipline. Use a fixed Vite port with `strictPort` or derive the exact port before Tauri launch so `devUrl` cannot silently diverge.

- [ ] **Step 4: Run targeted lifecycle and regression gates**

Run:

```text
corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/workspace src/product-shell/pages/NewWorkPage.test.tsx src/product-shell/shell/Sidebar.test.tsx src/components/assistant/AssistantModelPicker.test.tsx src/assistant/useAssistantModels.test.tsx src/product-shell/adapters/productWorkspaceClient.test.ts
corepack pnpm@10.29.2 --dir apps/operator-panel tauri:smoke
corepack pnpm@10.29.2 --dir apps/operator-panel tauri:smoke:launch
```

Expected: all focused unit tests and both smoke gates pass; a launched desktop run proves the previously broken flows rather than HTML delivery alone.

- [ ] **Step 5: Record integrated verification for MAIN**

Return exact command exits, artifact locations, worktree status, and any environment-only limitation. Do not report browser-only coverage as Tauri proof.

### Task 8: Remove the Windows ConPTY cursor-inheritance deadlock

**Files:**
- Create: `apps/operator-panel/src-tauri/vendor/portable-pty/` (faithful local source copy of `portable-pty 0.9.0`)
- Modify: `apps/operator-panel/src-tauri/vendor/portable-pty/src/win/psuedocon.rs:CreatePseudoConsole flags`
- Modify: `apps/operator-panel/src-tauri/Cargo.toml:[patch.crates-io]`
- Modify/Test: `apps/operator-panel/src-tauri/src/terminal.rs:native_pty_executes_an_interactive_shell_command_end_to_end`

**Interfaces:**
- Consumes: the existing `portable_pty::{native_pty_system, CommandBuilder, PtySize}` API and the terminal's UTF-8/VT byte streams.
- Produces: the identical `portable-pty 0.9.0` public API, with a Windows ConPTY that uses the supported standard GUI-host mode and does not wait for inherited cursor-state negotiation.

- [ ] **Step 1: Use the current native PTY regression test as the failing proof**

Run: `cargo test native_pty_executes_an_interactive_shell_command_end_to_end --manifest-path apps/operator-panel/src-tauri/Cargo.toml -- --nocapture`

Expected: the test exceeds the bounded runner timeout while an interactive PowerShell session waits on ConPTY cursor inheritance.

- [ ] **Step 2: Add a source-identical local override before its one-line Windows flag change**

Copy the registry source for `portable-pty 0.9.0` to `src-tauri/vendor/portable-pty`, retaining the manifest, license, source, and package metadata. Add this exact override to `src-tauri/Cargo.toml`:

```toml
[patch.crates-io]
portable-pty = { path = "vendor/portable-pty" }
```

- [ ] **Step 3: Remove only cursor inheritance from the ConPTY flag expression**

In the local override, replace:

```rust
PSUEDOCONSOLE_INHERIT_CURSOR
    | PSEUDOCONSOLE_RESIZE_QUIRK
    | PSEUDOCONSOLE_WIN32_INPUT_MODE
```

with:

```rust
PSEUDOCONSOLE_RESIZE_QUIRK | PSEUDOCONSOLE_WIN32_INPUT_MODE
```

Do not alter the public crate API, process creation, input/output pipes, terminal policy, or source files outside this bounded override.

- [ ] **Step 4: Run the native regression test and focused terminal checks**

Run:

```text
cargo test native_pty_executes_an_interactive_shell_command_end_to_end --manifest-path apps/operator-panel/src-tauri/Cargo.toml -- --nocapture
cargo test terminal_exit_status_preserves_the_native_exit_code --manifest-path apps/operator-panel/src-tauri/Cargo.toml
```

Expected: both tests pass without a stranded test process; the first contains `__IMPERAOS_PTY_OK__` and exits successfully.

- [ ] **Step 5: Verify dependency resolution and source scope**

Run:

```text
cargo tree --manifest-path apps/operator-panel/src-tauri/Cargo.toml -i portable-pty
cargo fmt --check --manifest-path apps/operator-panel/src-tauri/Cargo.toml
```

Expected: Cargo resolves `portable-pty v0.9.0` from the local override; formatting is clean. Record the exact diff and preserve unrelated checkout changes.

## Plan self-review

- Workspace, terminal, new conversation, model selection, soft archive, runtime readiness, and integration verification each map to an explicit task.
- The plan preserves non-destructive archive semantics, native identity/origin boundaries, and existing user changes.
- Every implementation task starts with a failing test and specifies a passing verification command.
- No placeholder language or implicit permanent deletion is present.
