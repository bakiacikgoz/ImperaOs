# UI Lab Theme Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Execution status (2026-07-25):** Tasks 1–8 implemented and freshly
verified. The unchecked boxes below preserve the original pre-implementation
procedure and expected red/green sequence; the evidence record is
`docs/integration/UI_LAB_INTEGRATION_EVIDENCE.md`.

**Goal:** Replace the simplified Product Shell presentation with the frozen UI Lab template while retaining every existing real ImperaOS product behavior.

**Architecture:** Copy the frozen UI Lab CSS contract verbatim into a Product Shell-owned theme bundle and mount it only for product routes. Rebuild Product Shell presentation components with the source DOM/class hierarchy, then bind those components to the existing durable workspace, assistant, artifact, terminal, browser, approval, and settings adapters.

**Tech Stack:** React 19, TypeScript 5.9, React Router 7, Zustand 5, Vite 7, Vitest 4, Testing Library, Playwright 1.60, Tauri 2.

## Global Constraints

- Canonical visual source: `/Users/baki/Documents/ImperaOS-UI-Lab` at `165208e90dd37376d5f0a21df22b7a1e7756aab5`.
- Preserve source dark/light tokens, typography, geometry, spacing, radii, responsive rules, interaction states, and motion.
- Preserve all existing real ImperaOS data, governance, assistant, artifact, terminal, browser, preview, approval, and legacy-route behavior.
- Never import `src/mocks/**` or `src/stores/demoStore.ts` from the source.
- Product styling must not leak into `/system/*`.
- Browser origin, approval, download, popup, native bounds, and session-isolation policies remain unchanged.
- Disabled or unavailable capabilities must remain honest and must not gain fake data or fake success states.
- Acceptance viewports: 1440×900, 1280×800, 1024×768, 768×900, and 390×844 in dark and light themes.
- A1 execution does not commit, push, merge, or publish without separate Git authority.

---

### Task 1: Canonical UI Lab theme mount

**Files:**
- Create: `apps/operator-panel/src/product-shell/styles/ui-lab/tokens.css`
- Create: `apps/operator-panel/src/product-shell/styles/ui-lab/globals.css`
- Create: `apps/operator-panel/src/product-shell/styles/ui-lab/surfaces.css`
- Create: `apps/operator-panel/src/product-shell/styles/ProductTheme.tsx`
- Modify: `apps/operator-panel/src/product-shell/ProductShellApp.tsx`
- Modify: `apps/operator-panel/src/product-shell/shell/AppShell.tsx`
- Replace: `apps/operator-panel/src/product-shell/styles/shell.css`
- Test: `apps/operator-panel/src/product-shell/ProductShellApp.theme.test.tsx`

**Interfaces:**
- Consumes: frozen source CSS files and `useProductShellStore().theme`.
- Produces: `ProductTheme({ theme }: { theme: 'dark' | 'light' }): JSX.Element` and an exact source stylesheet mounted only inside Product Shell routes.

- [ ] **Step 1: Write the failing theme-contract test**

```tsx
it('mounts the frozen UI Lab theme and source shell classes', () => {
  render(<AppShell><div>content</div></AppShell>);
  expect(document.querySelector('style[data-ui-lab-theme]')).not.toBeNull();
  expect(document.querySelector('.imperaos-product-shell-v2.app-shell')).not.toBeNull();
  expect(document.documentElement.dataset.theme).toBe('dark');
});
```

- [ ] **Step 2: Run the focused test and observe the missing theme style**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/ProductShellApp.theme.test.tsx`

Expected: FAIL because no `data-ui-lab-theme` style or source `app-shell` class exists.

- [ ] **Step 3: Copy the frozen CSS files verbatim**

Copy:

```text
/Users/baki/Documents/ImperaOS-UI-Lab/src/styles/tokens.css
  -> apps/operator-panel/src/product-shell/styles/ui-lab/tokens.css
/Users/baki/Documents/ImperaOS-UI-Lab/src/styles/globals.css
  -> apps/operator-panel/src/product-shell/styles/ui-lab/globals.css
/Users/baki/Documents/ImperaOS-UI-Lab/src/styles/surfaces.css
  -> apps/operator-panel/src/product-shell/styles/ui-lab/surfaces.css
```

Remove only the two `@import` lines from the copied `globals.css`; `ProductTheme`
will concatenate the three raw files in token/global/surface order.

- [ ] **Step 4: Add the route-scoped theme host**

```tsx
import tokens from './ui-lab/tokens.css?inline';
import globals from './ui-lab/globals.css?inline';
import surfaces from './ui-lab/surfaces.css?inline';

export function ProductTheme({ theme }: { theme: 'dark' | 'light' }) {
  useLayoutEffect(() => {
    const previous = document.documentElement.dataset.theme;
    document.documentElement.dataset.theme = theme;
    return () => {
      if (previous) document.documentElement.dataset.theme = previous;
      else delete document.documentElement.dataset.theme;
    };
  }, [theme]);
  return <style data-ui-lab-theme>{`${tokens}\n${globals}\n${surfaces}`}</style>;
}
```

Render `ProductTheme` inside `ProductShellRoutes`, not around the legacy route.
Set the Product Shell root classes to
`imperaos-product-shell-v2 app-shell` plus source state classes.

- [ ] **Step 5: Replace simplified shell CSS with runtime-only additions**

Keep `shell.css` limited to styles absent from the UI Lab source:
native browser viewport, native terminal host, canonical artifact host sizing,
and explicit disabled-reason treatment. Use only source token variables.

- [ ] **Step 6: Run the focused test**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/ProductShellApp.theme.test.tsx`

Expected: PASS.

- [ ] **Step 7: Prepare a local checkpoint**

Checkpoint files: the copied theme files, `ProductTheme.tsx`, shell host changes,
and the focused test. Do not commit under A1 without separate Git authority.

---

### Task 2: Source-shaped application shell, sidebar, top bar, and search

**Files:**
- Create: `apps/operator-panel/src/product-shell/shell/TopBar.tsx`
- Modify: `apps/operator-panel/src/product-shell/shell/AppShell.tsx`
- Modify: `apps/operator-panel/src/product-shell/shell/Sidebar.tsx`
- Modify: `apps/operator-panel/src/product-shell/shell/GlobalSearch.tsx`
- Modify: `apps/operator-panel/src/product-shell/state/productShellStore.ts`
- Test: `apps/operator-panel/src/product-shell/shell/AppShell.theme.test.tsx`
- Test: `apps/operator-panel/src/product-shell/shell/Sidebar.test.tsx`
- Test: `apps/operator-panel/src/product-shell/shell/GlobalSearch.test.tsx`

**Interfaces:**
- Consumes: `ProductProjectRoot[]`, `ProductTask[]`, `ProductWorkspaceClient`, router location, and UI-only shell state.
- Produces: source class contracts `sidebar codex-sidebar`, `app-frame`, `topbar`, `modal-backdrop`, and `search-modal`.

- [ ] **Step 1: Add failing class and behavior assertions**

```tsx
expect(screen.getByRole('complementary', { name: 'Product navigation' }))
  .toHaveClass('sidebar', 'codex-sidebar');
expect(screen.getByRole('button', { name: /kenar çubuğunu/i })).toBeVisible();
expect(document.querySelector('.app-frame')).not.toBeNull();
```

Retain existing assertions for real project loading, pin/order/archive mutations,
and governed search navigation.

- [ ] **Step 2: Run shell tests and observe source-class failures**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/shell`

Expected: FAIL on missing source shell hierarchy/classes.

- [ ] **Step 3: Port the source shell hierarchy**

Use the source `AppShell`, `Sidebar`, `TopBar`, and search modal markup. Replace
mock arrays with store records and retain these real actions:

```ts
productWorkspaceClient.registerProjectFromFolder()
productWorkspaceClient.updateProject(projectId, changes)
productWorkspaceClient.archiveProject(projectId, reason)
productWorkspaceClient.updateTask(taskId, changes)
productWorkspaceClient.archiveTask(taskId, reason)
```

Keep route labels and capabilities product-correct while preserving source icon
positions, row shells, action menus, truncation, resizer, and collapsed state.

- [ ] **Step 4: Make global search a source modal**

Keep the existing backend search request and result routing. Render results
inside `modal-backdrop`, `search-modal`, `search-input`, `search-result`, and
`search-hint`. Close on result selection, backdrop click, and Escape.

- [ ] **Step 5: Run shell tests**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/shell`

Expected: PASS, including durable mutation and search assertions.

- [ ] **Step 6: Prepare a local checkpoint**

Checkpoint the shell, sidebar, top bar, search, store, and tests without
committing under A1.

---

### Task 3: Home page and governed composer parity

**Files:**
- Modify: `apps/operator-panel/src/product-shell/pages/NewWorkPage.tsx`
- Modify: `apps/operator-panel/src/components/assistant/AssistantComposer.tsx`
- Modify: `apps/operator-panel/src/components/assistant/AssistantModelPicker.tsx`
- Modify: `apps/operator-panel/src/product-shell/composer/Composer.tsx`
- Test: `apps/operator-panel/src/product-shell/pages/NewWorkPage.test.tsx`
- Test: `apps/operator-panel/src/components/assistant/AssistantComposer.test.tsx`
- Test: `apps/operator-panel/src/product-shell/pages/NewWorkPage.theme.test.tsx`

**Interfaces:**
- Consumes: existing `AssistantRuntimeSettings`, model discovery, safe slash commands, context attachments, and tool intents.
- Produces: `AssistantComposer` visual variant `product` with source `composer` hierarchy and unchanged governed callback payload.

- [ ] **Step 1: Add failing parity assertions**

```tsx
expect(document.querySelector('.new-work-page.codex-home')).not.toBeNull();
expect(document.querySelector('.suggestion-grid.codex-suggestions')).not.toBeNull();
expect(screen.getByRole('form', { name: 'Assistant composer' })).toHaveClass('composer');
expect(document.querySelector('.composer-context')).not.toBeNull();
expect(document.querySelector('.composer-footer')).not.toBeNull();
```

Retain the assertion that task creation persists a real task and navigates to
its durable ID with runtime settings and safe controls.

- [ ] **Step 2: Run the home/composer tests**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/pages/NewWorkPage.test.tsx src/product-shell/pages/NewWorkPage.theme.test.tsx src/components/assistant/AssistantComposer.test.tsx`

Expected: FAIL on source class contracts.

- [ ] **Step 3: Port the source home hierarchy**

Render `new-work-page codex-home`, `welcome-stage`, `welcome-hero`,
`welcome-glyph`, `suggestion-grid codex-suggestions`, source card tones, and
`welcome-composer`. Suggestions seed the composer only; they do not fabricate
records.

- [ ] **Step 4: Add the product composer visual variant**

Add:

```ts
variant?: 'operator' | 'product'
```

For `product`, render source `composer`, `composer-context`, `composer-body`,
`composer-footer`, menu, model picker, access-control, microphone, and send
button classes. Preserve the existing validation, safe command resolution,
context/tool selections, model discovery, runtime settings, cancellation, and
`onSend(message, runtimeSettings, controls)` contract.

- [ ] **Step 5: Run the focused tests**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 6: Prepare a local checkpoint**

Checkpoint home/composer changes and tests without committing under A1.

---

### Task 4: Task page, conversation, and message-state parity

**Files:**
- Modify: `apps/operator-panel/src/product-shell/pages/TaskPage.tsx`
- Modify: `apps/operator-panel/src/product-shell/conversation/ProductConversationView.tsx`
- Modify: `apps/operator-panel/src/product-shell/conversation/conversationState.ts`
- Modify: `apps/operator-panel/src/product-shell/pages/TaskPage.test.tsx`
- Modify: `apps/operator-panel/src/product-shell/conversation/ProductConversationView.ui.test.tsx`
- Create: `apps/operator-panel/src/product-shell/pages/TaskPage.theme.test.tsx`

**Interfaces:**
- Consumes: durable task/message/link records and live `AssistantSessionState`.
- Produces: source `task-page`, `task-stage`, `task-layout`,
  `conversation-pane`, `conversation-view`, `conversation-inner`,
  `user-message`, `completion-message`, and `assistant-working` contracts.

- [ ] **Step 1: Add failing task/conversation class assertions**

```tsx
expect(document.querySelector('.task-page')).not.toBeNull();
expect(document.querySelector('.conversation-view')).not.toBeNull();
expect(document.querySelector('.sticky-composer')).not.toBeNull();
expect(document.querySelector('.assistant-working, .completion-message, .user-message'))
  .not.toBeNull();
```

Retain direct durable reload, first-turn start, persisted assistant messages,
durable action links, artifact open, approval open, copy, regenerate, and
cancel assertions.

- [ ] **Step 2: Run task/conversation tests**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/pages/TaskPage.test.tsx src/product-shell/pages/TaskPage.theme.test.tsx src/product-shell/conversation`

Expected: FAIL on source hierarchy/classes.

- [ ] **Step 3: Port the task layout**

Use source task header, stage, layout, conversation/workspace split, sticky
composer, open-surface prompt, and focus/rail state classes. Keep real workspace
tab state, durable reload, assistant send/cancel, and archived read-only
behavior.

- [ ] **Step 4: Port conversation presentation**

Map stored and live records to source message surfaces:

```ts
type ProductConversationItem =
  | { kind: 'user'; id: string; body: string }
  | { kind: 'working'; id: string; body: string; toolEvents: string[] }
  | { kind: 'completion'; id: string; body: string; links: ProductTaskLink[] }
  | { kind: 'error'; id: string; body: string };
```

Use source working orb, divider, tool event, reference document, change summary,
message action, and feedback-disabled layout. Do not expose chain-of-thought or
raw provider responses.

- [ ] **Step 5: Run task/conversation tests**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 6: Prepare a local checkpoint**

Checkpoint task/conversation changes and tests without committing under A1.

---

### Task 5: Workspace, context rail, bottom dock, and native surface parity

**Files:**
- Modify: `apps/operator-panel/src/product-shell/workspace/WorkSurface.tsx`
- Modify: `apps/operator-panel/src/product-shell/workspace/WorkspaceTabs.tsx`
- Modify: `apps/operator-panel/src/product-shell/context-rail/ContextRail.tsx`
- Modify: `apps/operator-panel/src/product-shell/bottom-dock/BottomDock.tsx`
- Modify: `apps/operator-panel/src/product-shell/terminal/TerminalSurface.tsx`
- Modify: `apps/operator-panel/src/product-shell/browser/BrowserSurface.tsx`
- Modify: `apps/operator-panel/src/product-shell/browser/PreviewSurface.tsx`
- Modify: `apps/operator-panel/src/product-shell/browser/BrowserApprovalInbox.tsx`
- Modify: `apps/operator-panel/src/product-shell/workspace/WorkSurface.test.tsx`
- Modify: `apps/operator-panel/src/product-shell/workspace/WorkspaceTabs.test.tsx`
- Modify: `apps/operator-panel/src/product-shell/context-rail/ContextRail.test.tsx`
- Modify: `apps/operator-panel/src/product-shell/browser/BrowserSurface.test.tsx`

**Interfaces:**
- Consumes: existing `WorkspaceTab`, assistant state, project root refs, native terminal/browser commands, and browser approval events.
- Produces: source workspace split, tab strip, rail, dock, toolbar, overlay, and modal visual contracts with unchanged runtime lifecycles.

- [ ] **Step 1: Add failing source-surface assertions**

```tsx
expect(document.querySelector('.work-surface')).not.toBeNull();
expect(document.querySelector('.workspace-tabs')).not.toBeNull();
expect(document.querySelector('.context-rail')).not.toBeNull();
expect(document.querySelector('.bottom-dock')).not.toBeNull();
```

Retain tests that inactive terminal/browser surfaces stay mounted or hidden,
native bounds synchronize, and tabs close their sessions only when removed.

- [ ] **Step 2: Run focused surface tests**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/workspace src/product-shell/context-rail src/product-shell/browser`

Expected: FAIL on source class contracts.

- [ ] **Step 3: Port workspace, rail, and dock markup**

Use source `work-surface`, `workspace-header`, `workspace-tabs`,
`workspace-panel`, `context-rail`, and `bottom-dock` structures. Populate them
only from real assistant/task/runtime data and explicit capability states.

- [ ] **Step 4: Theme native terminal/browser/preview surfaces**

Keep command/event behavior unchanged. Replace outer `ps-*` chrome with source
tab/toolbar/panel classes plus narrowly scoped runtime classes:

```text
product-native-terminal
product-native-browser
product-native-preview
product-native-viewport
```

Browser approval remains a modal/alert dialog and hides the originating native
child webview before the overlay appears.

- [ ] **Step 5: Run focused surface tests**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 6: Run Rust browser/terminal policy tests**

Run: `cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml`

Expected: all tests pass with unchanged mode-specific security policy.

- [ ] **Step 7: Prepare a local checkpoint**

Checkpoint surface changes and tests without committing under A1.

---

### Task 6: Collections, settings, empty/error states, and legacy isolation

**Files:**
- Modify: `apps/operator-panel/src/product-shell/pages/CollectionPage.tsx`
- Modify: `apps/operator-panel/src/product-shell/pages/GovernedCollections.tsx`
- Modify: `apps/operator-panel/src/product-shell/settings/SettingsShell.tsx`
- Modify: `apps/operator-panel/src/product-shell/pages/GovernedCollections.test.tsx`
- Modify: `apps/operator-panel/src/product-shell/settings/SettingsShell.test.tsx`
- Create: `apps/operator-panel/src/product-shell/legacy/LegacyStyleIsolation.test.tsx`

**Interfaces:**
- Consumes: real artifact, approval, agent, settings, and capability clients.
- Produces: source collection/settings shells and a verified removal of Product Theme styles on `/system/*`.

- [ ] **Step 1: Add failing collection/settings/isolation assertions**

```tsx
expect(document.querySelector('.collection-page')).not.toBeNull();
expect(document.querySelector('.settings-shell')).not.toBeNull();
expect(document.querySelector('.settings-sidebar')).not.toBeNull();
```

For legacy:

```tsx
render(<ProductShellApp />, { initialHash: '#/system/settings' });
expect(document.querySelector('style[data-ui-lab-theme]')).toBeNull();
```

- [ ] **Step 2: Run focused tests**

Run: `corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/product-shell/pages/GovernedCollections.test.tsx src/product-shell/settings/SettingsShell.test.tsx src/product-shell/legacy/LegacyStyleIsolation.test.tsx`

Expected: FAIL on source classes and style isolation.

- [ ] **Step 3: Port collection and settings presentation**

Use the source collection header/list rows and SettingsShell sidebar/content,
blocks, rows, segmented controls, toggles, account block, and responsive rules.
Keep real record selection, approval decisions, agent registry, settings
persistence, and advanced legacy links.

- [ ] **Step 4: Map honest non-success states**

Render loading, no-results, error, and capability-unavailable messages in source
empty/card states. Keep automation, files, data explorer, feedback, and
unqualified agent-browser capabilities visibly disabled where their governed
backend is absent.

- [ ] **Step 5: Run focused tests**

Run the command from Step 2.

Expected: PASS.

- [ ] **Step 6: Prepare a local checkpoint**

Checkpoint collection/settings/isolation changes and tests without committing.

---

### Task 7: Responsive and visual parity harness

**Files:**
- Create: `apps/operator-panel/e2e/ui-lab-theme-parity.spec.ts`
- Create: `apps/operator-panel/scripts/capture-ui-lab-parity.ts`
- Create: `apps/operator-panel/src/product-shell/styles/uiLabThemeManifest.ts`
- Modify: `apps/operator-panel/package.json`
- Modify: `docs/integration/UI_LAB_COMPONENT_MAP.md`
- Modify: `docs/integration/UI_LAB_INTEGRATION_EVIDENCE.md`

**Interfaces:**
- Consumes: frozen source URL, Product Shell URL, acceptance viewports, and theme values.
- Produces: deterministic source/target screenshots and a source SHA/theme-file manifest.

- [ ] **Step 1: Add the manifest test**

```ts
expect(UI_LAB_THEME_MANIFEST.sourceSha)
  .toBe('165208e90dd37376d5f0a21df22b7a1e7756aab5');
expect(UI_LAB_THEME_MANIFEST.files).toEqual([
  'src/styles/tokens.css',
  'src/styles/globals.css',
  'src/styles/surfaces.css',
]);
```

- [ ] **Step 2: Add deterministic screenshot cases**

For each viewport and `dark | light`, capture:

```text
home-expanded
home-collapsed
task-conversation
task-workspace
library
approvals
agents
settings
search-modal
```

Wait for fonts and stable layout; disable animations only during capture. Mask
only dynamic copy, IDs, timestamps, and native content.

- [ ] **Step 3: Add package scripts**

```json
"ui-lab:parity:capture": "tsx scripts/capture-ui-lab-parity.ts",
"test:e2e:ui-lab": "playwright test e2e/ui-lab-theme-parity.spec.ts"
```

- [ ] **Step 4: Run the parity harness**

Run:

```bash
corepack pnpm@10.29.2 --dir apps/operator-panel ui-lab:parity:capture
corepack pnpm@10.29.2 --dir apps/operator-panel test:e2e:ui-lab
```

Expected: all structural screenshot cases render; no unreviewed visual
divergence remains in the generated side-by-side evidence.

- [ ] **Step 5: Update integration evidence**

Record source SHA, canonical files, verified routes, viewports, themes, and any
permitted dynamic masks. Do not claim native assistant success from a browser
fixture.

- [ ] **Step 6: Prepare a local checkpoint**

Checkpoint visual harness and documentation without committing under A1.

---

### Task 8: Full regression and desktop verification

**Files:**
- Modify only if verification exposes a defect in a file owned by Tasks 1-7.

**Interfaces:**
- Consumes: integrated theme parity implementation.
- Produces: `integrated-verified` evidence for the Product Shell worktree.

- [ ] **Step 1: Run Product Shell and full frontend tests**

Run:

```bash
corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run --reporter=dot
```

Expected: all test files and tests pass.

- [ ] **Step 2: Run static and production checks**

Run separately:

```bash
corepack pnpm@10.29.2 --dir apps/operator-panel lint
corepack pnpm@10.29.2 --dir apps/operator-panel build
corepack pnpm@10.29.2 --dir apps/operator-panel i18n:coverage
corepack pnpm@10.29.2 --dir apps/operator-panel bridge:parity
git diff --check
```

Expected: exit 0 for every command. A bundle-size warning is informational.

- [ ] **Step 3: Run backend/native checks when touched**

Run separately:

```bash
uv run pytest -q --disable-warnings
uv run ruff check .
cargo test -q --manifest-path apps/operator-panel/src-tauri/Cargo.toml
cargo check --manifest-path apps/operator-panel/src-tauri/Cargo.toml
cargo fmt --check --manifest-path apps/operator-panel/src-tauri/Cargo.toml
```

Expected: exit 0 for every command.

- [ ] **Step 4: Run the Tauri launch probe**

Run:

```bash
env OPERATOR_PANEL_TAURI_LAUNCH_TIMEOUT_MS=10000 \
  corepack pnpm@10.29.2 --dir apps/operator-panel tauri:smoke:launch
```

Expected: the desktop process remains alive for 10 seconds. Bridge/assistant
instrumentation may remain explicitly conditional when no qualified local
assistant runtime is available.

- [ ] **Step 5: Inspect the final diff and repository guards**

Confirm:

```text
no source mocks/demo store imported
no website/** integration
no browser or terminal security weakening
legacy route has no Product Theme style element
working tree changes are entirely within the approved theme-parity scope
```

- [ ] **Step 6: Report without unauthorized Git mutation**

Report changed files, visual evidence, exact command results, open conditional
runtime gates, and the current branch. Do not commit, push, merge, or publish
until the user supplies that separate authority.
