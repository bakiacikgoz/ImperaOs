# Web Workspace Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the private JavaScript workspace, Operator Panel package, and browser document title with ImperaOS.

**Architecture:** Keep workspace paths and dependency resolution unchanged; update only package display identities and initial HTML metadata. Protect the values with a focused file-backed Vitest contract and verify pnpm lockfile idempotence.

**Tech Stack:** JSON package manifests, HTML5, pnpm 10.29.2, React/Vite, Vitest 4, Playwright 1.60.

## Global Constraints

- Root package name must be exactly `imperaos-workspace`.
- App package name must be exactly `imperaos-operator-panel`.
- HTML and E2E document title must be exactly `ImperaOS Operator Panel`.
- Keep `apps/operator-panel/public/vite.svg` and its `/vite.svg` link unchanged.
- Do not change package versions, scripts, dependencies, package-manager declarations, workspace importer paths, or unrelated lockfile entries.
- Do not modify Tauri, Cargo, bundled-runtime, installer, release, CI, source behavior, historical, signed, or immutable files.
- The implementation commit subject must be exactly `build: align web workspace metadata with ImperaOS`.

---

### Task 1: Align web workspace metadata

**Files:**

- Modify: `package.json`
- Modify: `apps/operator-panel/package.json`
- Modify: `apps/operator-panel/index.html`
- Modify: `apps/operator-panel/e2e/helpers.ts`
- Create: `apps/operator-panel/src/webMetadata.test.ts`
- Verify unchanged: `apps/operator-panel/public/vite.svg`
- Regenerate only if content changes: `pnpm-lock.yaml`

**Interfaces:**

- Consumes: root/app JSON `name` fields and the browser `<title>`/favicon link in `index.html`.
- Produces: exact ImperaOS names/title without changing importer paths or dependency graph.

- [ ] **Step 1: Write the failing metadata contract test**

Create `apps/operator-panel/src/webMetadata.test.ts`:

```typescript
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

type PackageManifest = { name?: string };

function readJson(relativeUrl: string): PackageManifest {
  return JSON.parse(readFileSync(new URL(relativeUrl, import.meta.url), 'utf8')) as PackageManifest;
}

describe('web workspace metadata', () => {
  it('uses the canonical ImperaOS package and document identities', () => {
    const rootPackage = readJson('../../../package.json');
    const appPackage = readJson('../package.json');
    const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');

    expect(rootPackage.name).toBe('imperaos-workspace');
    expect(appPackage.name).toBe('imperaos-operator-panel');
    expect(html).toContain('<title>ImperaOS Operator Panel</title>');
  });

  it('keeps the approved brand-neutral favicon reference', () => {
    const html = readFileSync(new URL('../index.html', import.meta.url), 'utf8');

    expect(html).toContain('href="/vite.svg"');
  });
});
```

- [ ] **Step 2: Run the focused test and verify RED**

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/webMetadata.test.ts
```

Expected: first test FAILS on the root package name, app package name, and HTML title; favicon test PASSES. Record the failure before editing metadata.

- [ ] **Step 3: Apply the minimal metadata changes**

Change only these values:

`package.json`:

```json
{
  "name": "imperaos-workspace",
  "private": true
}
```

In `apps/operator-panel/package.json`:

```json
"name": "imperaos-operator-panel"
```

In `apps/operator-panel/index.html`:

```html
<title>ImperaOS Operator Panel</title>
```

In `apps/operator-panel/e2e/helpers.ts`:

```typescript
await expect(page).toHaveTitle('ImperaOS Operator Panel');
```

Do not modify the favicon link, scripts, versions, dependency blocks, or package-manager field.

- [ ] **Step 4: Run the focused test and verify GREEN**

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel exec vitest run src/webMetadata.test.ts
```

Expected: 1 file and 2 tests PASS.

- [ ] **Step 5: Prove lockfile idempotence**

Capture the original hash, run the pinned package manager, and compare:

```powershell
$before = (Get-FileHash pnpm-lock.yaml -Algorithm SHA256).Hash
corepack pnpm@10.29.2 install --lockfile-only
$after = (Get-FileHash pnpm-lock.yaml -Algorithm SHA256).Hash
"before=$before"
"after=$after"
git diff -- pnpm-lock.yaml
```

Expected: hashes are identical and `git diff -- pnpm-lock.yaml` is empty. If pnpm produces dependency churn, do not include it; investigate the command/environment before proceeding.

- [ ] **Step 6: Run full static verification**

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel test
corepack pnpm@10.29.2 --dir apps/operator-panel lint
corepack pnpm@10.29.2 --dir apps/operator-panel build
```

Expected: all Vitest files pass, lint exits 0, and TypeScript/Vite build exits 0.

- [ ] **Step 7: Run the title browser check**

```powershell
corepack pnpm@10.29.2 --dir apps/operator-panel exec playwright test e2e/assistant.spec.ts --pass-with-no-tests
```

Expected: scenario passes. If the already identified Chromium binary is still absent, record the exact environment error and do not alter product code or install dependencies as a workaround.

- [ ] **Step 8: Audit boundaries and former metadata**

```powershell
rg -n 'imperaos-workspace|"name"\s*:\s*"operator-panel"|<title>operator-panel</title>' package.json apps/operator-panel/package.json apps/operator-panel/index.html apps/operator-panel/e2e
git diff --name-only 2b0e5bf
git diff --check
```

Expected:

- former metadata scan has no matches;
- diff contains only the five Task 5.2 files;
- favicon asset/link is unchanged;
- `pnpm-lock.yaml`, Tauri, Cargo, runtime, installer, CI, versions, scripts, dependencies, and package-manager declarations are unchanged;
- `git diff --check` exits 0.

- [ ] **Step 9: Record inventory evidence and commit**

Run the inventory after all Task 5.2 files are tracked or explicitly report pre-commit versus committed-HEAD semantics. Add the implementation files and commit:

```powershell
git -c user.name=Codex -c user.email=codex@openai.com commit -m "build: align web workspace metadata with ImperaOS"
```

Then run the inventory against that committed implementation HEAD with MinGit available on `PATH`, write `.superpowers/sdd/task-5.2-report.md`, and commit the report separately. The report must include RED/GREEN evidence, full test counts, build/lint results, Playwright status, lockfile hash equality, inventory commit/counts, exact diff boundary, and implementation SHA.
