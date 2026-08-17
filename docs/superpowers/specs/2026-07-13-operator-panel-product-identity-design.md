# Operator Panel Product Identity Design

Date: 2026-07-13
Status: Approved
Plan task: Phase 5, Task 5.1

## Objective

Move every active Operator Panel product-identity surface from the former brand to ImperaOS while preserving English/Turkish UI parity and existing runtime behavior. This task covers visible UI copy, the browser settings namespace, active preview identities, and their tests. Package, HTML, Tauri, Cargo, bundled-runtime, installer, and CI identities remain owned by later tasks.

## Decisions

- Use the existing canonical `PRODUCT_IDENTITY` module where a UI surface needs the product display name or operator product name.
- Keep domain-specific fixture identifiers explicit when they are serialized or operational values, such as `imperaos-computer-use` and the ImperaOS preview hostname.
- Read and write only `imperaos.operator.settings.v1` in final application code.
- Do not read, migrate, copy, or delete `imperaos.operator.settings.v1`. Existing settings under the former key are intentionally ignored and defaults are loaded.
- Do not add a React brand context or another identity registry.
- Do not retain compatibility aliases or former-brand constants in active Operator Panel code.

## Components and Changes

### Localized and visible identity

Update the English and Turkish dictionaries so both locales expose:

- `ImperaOS Agent Control Plane`
- `ImperaOS Assistant`
- locale-appropriate welcome text containing `ImperaOS Assistant`

Update active non-dictionary surfaces that display product identity, including the sidebar header and assistant route heading. Visible titles must not depend on a former-brand literal.

### Assistant brand highlighting

`AssistantWelcome` continues to highlight only the product-name portion of its title. Rename brand-specific local variables to generic names such as `brandIndex`, and locate/highlight `ImperaOS`. Preserve the complete accessible heading through the existing `aria-label`.

### Browser settings namespace

Change the canonical settings key to exactly `imperaos.operator.settings.v1`. `loadSettings` checks only that key; if it is missing or invalid, it returns the existing defaults. `saveSettings` writes only that key. The old key is neither read nor removed.

### Preview identity

Replace active preview-only former-brand identities with ImperaOS equivalents, including:

- computer-use team identifiers;
- preview URL hostname and derived active-surface values;
- preview window title/identity strings;
- request and verified-effect text containing the preview URL.

Keep fixture structure, timestamps, workflow state, approvals, and unrelated payload data unchanged.

## Data Flow

1. Application startup calls `loadSettings`.
2. Only the ImperaOS storage key is queried.
3. Missing or invalid data resolves to existing defaults; valid data is normalized as before.
4. UI locale resolution selects the English or Turkish ImperaOS dictionary.
5. Sidebar, route, assistant, and shell surfaces render the canonical ImperaOS identity.
6. Preview bridge calls return fixtures whose active hosts, titles, and team identifiers use ImperaOS.

## Error and Compatibility Behavior

- Invalid JSON under the new settings key remains fail-safe and returns defaults.
- Data stored only under the old key has no effect.
- No migration warning or destructive cleanup is introduced.
- Runtime bridge errors and preview/live selection behavior remain unchanged.

## Test Design

Follow RED-GREEN-REFACTOR:

1. Add or update focused tests first and confirm they fail because active surfaces still use the former identity.
2. Verify exact English and Turkish product/assistant titles.
3. Verify the assistant heading renders and highlights ImperaOS while preserving its accessible full title.
4. Verify settings load/save uses only `imperaos.operator.settings.v1` and ignores data stored solely under the former key.
5. Verify preview computer-use team IDs, hostnames, window identities, and derived URLs use ImperaOS.
6. Verify sidebar and route-visible assistant identity.
7. Run the focused Vitest set, full Operator Panel test suite, typecheck/build, and relevant Playwright checks where the environment supports them.
8. Scan active Operator Panel source and tests in Task 5.1 scope for former product identity, former storage key, former preview hostname, and former active team ID. Expected residual count is zero, excluding immutable/history evidence outside this task.

## Acceptance Criteria

- All visible active Operator Panel product titles use ImperaOS in both English and Turkish.
- The assistant highlight logic is brand-generic in naming and highlights ImperaOS.
- Only `imperaos.operator.settings.v1` is used by final application and E2E setup code.
- Active preview identities use ImperaOS consistently.
- Focused and full Operator Panel verification passes.
- No package, HTML, Tauri, Cargo, bundled-runtime, installer, CI, dependency, or lockfile changes are included.

## Implementation Boundary

The implementation commit subject must be exactly:

`feat: rebrand Operator Panel surfaces to ImperaOS`
