# Operator Panel Product Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand all active Operator Panel UI, browser-settings, and preview-identity surfaces to ImperaOS without retaining a former-key compatibility path.

**Architecture:** Reuse `PRODUCT_IDENTITY` for display-name and slug-derived UI values, while keeping serialized preview identifiers explicit. Preserve existing component, settings, and preview data flows; this task changes identity values and adds regression coverage, not application structure.

**Tech Stack:** React 19, TypeScript 5.9, Vitest 4, Playwright 1.60, Vite 7, pnpm 10.29.2.

## Global Constraints

- Final application code reads and writes only `imperaos.operator.settings.v1`.
- Data stored only under `imperaos.operator.settings.v1` is ignored; do not migrate, copy, or delete it.
- English and Turkish UI must both render ImperaOS product and assistant titles.
- Do not add a React context, identity registry, compatibility alias, dependency, or lockfile change.
- Do not modify package, HTML, Tauri, Cargo, bundled-runtime, installer, CI, historical, signed, or immutable surfaces in this task.
- Use RED-GREEN-REFACTOR and record the expected RED failure before production edits.
- The implementation commit subject must be exactly `feat: rebrand Operator Panel surfaces to ImperaOS`.

---

## File Map

**Canonical identity consumers**

- Modify: `apps/operator-panel/src/i18n.ts` — localized display and assistant titles.
- Modify: `apps/operator-panel/src/components/shell/Sidebar.tsx` — sidebar product display name.
- Modify: `apps/operator-panel/src/components/assistant/AssistantWelcome.tsx` — ImperaOS highlight logic.
- Modify: `apps/operator-panel/src/routeRegistry.ts` — visible assistant route heading.

**Browser settings**

- Modify: `apps/operator-panel/src/settings.ts` — slug-derived canonical settings key.
- Modify: `apps/operator-panel/e2e/helpers.ts` — E2E seed key.

**Preview identities**

- Modify: `apps/operator-panel/src/previewFixtures.ts` — preview host, window title, derived surface strings, and computer-use team IDs.
- Modify: `apps/operator-panel/src/assistant/assistantFixtures.ts` — assistant preview target title.

**Regression tests**

- Create: `apps/operator-panel/src/productIdentitySurfaces.test.tsx` — EN/TR, sidebar, route, and highlight contract.
- Modify: `apps/operator-panel/src/settings.test.ts` — exact new key, save/load behavior, and old-key isolation.
- Modify: `apps/operator-panel/src/App.test.tsx` — rendered ImperaOS shell.
- Modify: `apps/operator-panel/src/components/assistant/AssistantView.test.tsx` — assistant title and welcome state.
- Modify: `apps/operator-panel/src/previewFixtures.test.ts` — preview identities.
- Modify: `apps/operator-panel/src/bridge.test.ts` — preview request URL expectation.
- Modify: `apps/operator-panel/src/workspace.test.ts` — preview world-model URL/title expectations.
- Modify: `apps/operator-panel/e2e/assistant.spec.ts` — visible assistant welcome heading.

---

### Task 1: Rebrand active Operator Panel identity surfaces

**Interfaces:**

- Consumes: `PRODUCT_IDENTITY: ProductIdentity` from `apps/operator-panel/src/productIdentity.ts`, including `displayName: string` and `slug: string`.
- Preserves: `loadSettings(): PanelSettings`, `saveSettings(settings: PanelSettings): void`, `dictionaries: Record<UiLocale, Dictionary>`, and all preview-function signatures.
- Produces: `SETTINGS_KEY === "imperaos.operator.settings.v1"` and ImperaOS-only active UI/preview values.

- [ ] **Step 1: Add the failing UI identity contract test**

Create `apps/operator-panel/src/productIdentitySurfaces.test.tsx` with the following test coverage:

```tsx
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { AssistantWelcome } from './components/assistant/AssistantWelcome';
import { Sidebar } from './components/shell/Sidebar';
import { dictionaries } from './i18n';
import { PRODUCT_IDENTITY } from './productIdentity';
import { routes } from './routeRegistry';

describe('Operator Panel product identity surfaces', () => {
  it('keeps English and Turkish product titles on the canonical identity', () => {
    expect(dictionaries.en.appTitle).toBe('ImperaOS Agent Control Plane');
    expect(dictionaries.tr.appTitle).toBe('ImperaOS Agent Control Plane');
    expect(dictionaries.en.assistantTitle).toBe('ImperaOS Assistant');
    expect(dictionaries.tr.assistantTitle).toBe('ImperaOS Assistant');
    expect(dictionaries.en.assistantWelcomeTitle).toBe('Welcome to ImperaOS Assistant');
    expect(dictionaries.tr.assistantWelcomeTitle).toContain('ImperaOS Assistant');
  });

  it('renders the canonical sidebar and assistant brand without the former display name', () => {
    const sidebar = renderToStaticMarkup(
      <Sidebar
        activeView="workspace"
        open
        collapsed={false}
        operatorId="qa-operator"
        pendingApprovalCount={0}
        warningCount={0}
        onClose={() => undefined}
        onToggleCollapse={() => undefined}
        onNavigate={() => undefined}
        onThemeChange={() => undefined}
      />,
    );
    const welcome = renderToStaticMarkup(
      <AssistantWelcome
        title="Welcome to ImperaOS Assistant"
        subtitle="Governed assistant"
        badgeLabel="Governed assistant"
        readOnlyByDefault="Read-only by default"
      />,
    );
    const formerDisplayName = ['ImperaOS', 'OS'].join('');

    expect(PRODUCT_IDENTITY.displayName).toBe('ImperaOS');
    expect(sidebar).toContain('<h1>ImperaOS</h1>');
    expect(sidebar).not.toContain(formerDisplayName);
    expect(welcome).toContain('<span>ImperaOS</span>');
    expect(welcome).toContain('aria-label="Welcome to ImperaOS Assistant"');
  });

  it('uses the ImperaOS assistant route heading', () => {
    expect(routes.find((route) => route.routeId === 'assistant')?.heading).toBe('ImperaOS Assistant');
  });
});
```

- [ ] **Step 2: Run the UI identity test and verify RED**

Run from the repository root:

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/productIdentitySurfaces.test.tsx
```

Expected: FAIL because dictionary, sidebar, assistant highlight, and route heading still expose the former identity. Record the failing assertions; do not edit production code before this run.

- [ ] **Step 3: Implement the minimal visible-identity changes**

In `apps/operator-panel/src/i18n.ts`, import the canonical identity and replace only the six localized identity values:

```typescript
import { PRODUCT_IDENTITY } from './productIdentity';

const productDisplayName = PRODUCT_IDENTITY.displayName;

// In `en`:
appTitle: `${productDisplayName} Agent Control Plane`,
assistantTitle: `${productDisplayName} Assistant`,
assistantWelcomeTitle: `Welcome to ${productDisplayName} Assistant`,

// In `tr`:
appTitle: `${productDisplayName} Agent Control Plane`,
assistantTitle: `${productDisplayName} Assistant`,
assistantWelcomeTitle: `${productDisplayName} Assistant’a hoş geldiniz`,
```

In `apps/operator-panel/src/components/shell/Sidebar.tsx`, import `PRODUCT_IDENTITY` and render:

```tsx
<h1>{PRODUCT_IDENTITY.displayName}</h1>
```

In `apps/operator-panel/src/components/assistant/AssistantWelcome.tsx`, import `PRODUCT_IDENTITY` and replace the former-brand indexing block with:

```tsx
const brandName = PRODUCT_IDENTITY.displayName;
const brandIndex = title.indexOf(brandName);
const highlightedTitle =
  brandIndex >= 0 ? (
    <>
      {title.slice(0, brandIndex)}
      <span>{brandName}</span>
      {title.slice(brandIndex + brandName.length)}
    </>
  ) : (
    title
  );
```

In `apps/operator-panel/src/routeRegistry.ts`, import `PRODUCT_IDENTITY` and set the assistant heading to:

```typescript
heading: `${PRODUCT_IDENTITY.displayName} Assistant`,
```

Update `apps/operator-panel/src/App.test.tsx` and `apps/operator-panel/src/components/assistant/AssistantView.test.tsx` so their exact title/copy expectations use `ImperaOS`.

- [ ] **Step 4: Run the focused visible-identity tests and verify GREEN**

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/productIdentitySurfaces.test.tsx src/App.test.tsx src/components/assistant/AssistantView.test.tsx src/routeRegistry.test.ts
```

Expected: all selected tests PASS with no warnings or unhandled errors.

- [ ] **Step 5: Add failing settings-namespace tests**

In `apps/operator-panel/src/settings.test.ts`, import `saveSettings` and add:

```typescript
it('uses only the canonical ImperaOS browser settings namespace', () => {
  const formerKey = ['imperaos', 'os.operator.settings.v1'].join('');
  localStorage.setItem(formerKey, JSON.stringify({ ...DEFAULT_SETTINGS, profile: 'strict' }));

  expect(SETTINGS_KEY).toBe('imperaos.operator.settings.v1');
  expect(loadSettings().profile).toBe(DEFAULT_SETTINGS.profile);

  const nextSettings = { ...DEFAULT_SETTINGS, profile: 'fast' };
  saveSettings(nextSettings);
  expect(JSON.parse(localStorage.getItem('imperaos.operator.settings.v1') ?? '{}')).toEqual(nextSettings);
  expect(localStorage.getItem(formerKey)).not.toBeNull();
});
```

- [ ] **Step 6: Run the settings test and verify RED**

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/settings.test.ts
```

Expected: FAIL because `SETTINGS_KEY` still resolves to the former namespace and data under that key is loaded.

- [ ] **Step 7: Implement the new browser settings namespace**

In `apps/operator-panel/src/settings.ts`, import `PRODUCT_IDENTITY` and define:

```typescript
export const SETTINGS_KEY = `${PRODUCT_IDENTITY.slug}.operator.settings.v1`;
```

Do not add any former-key fallback, migration, deletion, or alias. In `apps/operator-panel/e2e/helpers.ts`, set:

```typescript
const SETTINGS_KEY = 'imperaos.operator.settings.v1';
```

- [ ] **Step 8: Run the settings tests and verify GREEN**

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/settings.test.ts
```

Expected: all settings tests PASS; the former-key isolation test proves the old value is ignored and not deleted.

- [ ] **Step 9: Add failing preview-identity assertions**

Extend `apps/operator-panel/src/previewFixtures.test.ts` by importing `previewTailEvents` and adding:

```typescript
it('uses ImperaOS preview hosts, windows, and team identifiers', () => {
  const settings = { ...DEFAULT_SETTINGS, rootDir: '.imperaos/preview/jobs' };
  const serialized = JSON.stringify([
    previewRunDetail(settings),
    previewTailEvents(),
  ]);
  const formerHost = ['preview.', 'imperaos', '.local'].join('');
  const formerWindowTitle = ['ImperaOS', ' Preview Form'].join('');

  expect(serialized).toContain('imperaos-computer-use');
  expect(serialized).toContain('https://preview.imperaos.local/form');
  expect(serialized).toContain('ImperaOS Preview Form');
  expect(serialized).not.toContain(formerHost);
  expect(serialized).not.toContain(formerWindowTitle);
});
```

- [ ] **Step 10: Run the preview test and verify RED**

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/previewFixtures.test.ts
```

Expected: FAIL because active preview URL and window identities still contain the former brand.

- [ ] **Step 11: Implement the preview identity replacements**

In `apps/operator-panel/src/previewFixtures.ts`, change every active preview occurrence as follows:

```text
https://preview.imperaos.local/form -> https://preview.imperaos.local/form
safari:ImperaOS Preview Form -> safari:ImperaOS Preview Form
ImperaOS Preview Form -> ImperaOS Preview Form
imperaos-computer-use -> imperaos-computer-use
```

Apply the same preview title replacement in `apps/operator-panel/src/assistant/assistantFixtures.ts`. Update matching expected values in `apps/operator-panel/src/bridge.test.ts` and `apps/operator-panel/src/workspace.test.ts`. In `apps/operator-panel/e2e/assistant.spec.ts`, use:

```typescript
await openPrimaryView(page, 'AI Assistant', 'Welcome to ImperaOS Assistant');
```

Do not alter fixture timestamps, approval IDs, workflow states, or payload shapes.

- [ ] **Step 12: Run the focused preview tests and verify GREEN**

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/previewFixtures.test.ts src/bridge.test.ts src/workspace.test.ts src/components/assistant/AssistantView.test.tsx
```

Expected: all selected tests PASS; `AssistantView.test.tsx` exercises the assistant fixture consumer.

- [ ] **Step 13: Run full Operator Panel static verification**

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel test
corepack pnpm@10.29.2 --dir apps/operator-panel lint
corepack pnpm@10.29.2 --dir apps/operator-panel build
corepack pnpm@10.29.2 --dir apps/operator-panel i18n:coverage
```

Expected: full Vitest, ESLint, TypeScript/Vite build, and i18n coverage all exit 0.

- [ ] **Step 14: Run the relevant browser verification**

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel exec playwright test e2e/assistant.spec.ts --pass-with-no-tests
```

Expected: assistant Playwright scenario PASS. If the environment lacks the required Playwright browser binary, record the exact tool/environment error without changing product code; the unit, build, and lint gates remain mandatory.

- [ ] **Step 15: Audit task boundaries and former active identities**

Run:

```powershell
rg -n "ImperaOS|imperaos\.operator\.settings|imperaos-computer-use|preview\.imperaos|ImperaOS Preview" apps/operator-panel/src apps/operator-panel/e2e
git diff --name-only 7acc7f6
git diff --check
```

Expected:

- the former-identity scan returns no matches in active source/E2E files;
- diff contains only the files listed in this plan plus the implementation-plan/SDD evidence files;
- no package, HTML, Tauri, Cargo, scripts, dependencies, or lockfiles changed;
- `git diff --check` exits 0.

- [ ] **Step 16: Record brand inventory evidence**

```powershell
& '.venv\Scripts\python.exe' scripts/run_brand_consistency_gate.py --mode inventory --repo-root . --output-root C:\p51-brand --json
```

Expected: command exits 0 and total findings are lower than the Task 4.3 result of 994. The inventory remains nonzero because later phases own Tauri, packaging, installer, documentation, and historical boundaries.

- [ ] **Step 17: Commit the complete Task 5.1 implementation**

Stage only the reviewed Task 5.1 files and its SDD brief. Commit with:

```powershell
git -c user.name=Codex -c user.email=codex@openai.com commit -m "feat: rebrand Operator Panel surfaces to ImperaOS"
```

Expected: commit succeeds with the exact required subject. Write `.superpowers/sdd/task-5.1-report.md` afterward with RED/GREEN evidence, test counts, Playwright status, scan results, inventory delta, diff boundary, and implementation SHA; commit the report separately.
