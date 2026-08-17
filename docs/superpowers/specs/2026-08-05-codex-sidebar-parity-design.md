# Codex Sidebar Parity Design

## Objective

Bring the ImperaOS product sidebar to the proportions, visual hierarchy, and restrained surface treatment of the supplied Codex desktop reference while preserving ImperaOS routes, governed project/task data, workspace mutations, profile/settings access, search, collapse, and resize behavior.

The reference is a visual contract, not a source of fabricated product data or inactive controls.

## Scope and ownership

- Keep the frozen UI Lab theme files under `styles/ui-lab/` byte-for-byte unchanged.
- Put product-specific sidebar parity rules in `styles/shell.css`, scoped under `.imperaos-product-shell-v2`.
- Keep project/task loading and mutation behavior in `Sidebar.tsx` unchanged except for semantic classes and a compact web-preview status treatment.
- Keep persisted UI preferences in `productShellStore.ts`; introduce a versioned migration for the new width contract.
- Do not add a notification control unless a real ImperaOS notification destination or state exists. The supplied bell is therefore not copied as a non-functional decoration.

## Geometry

- Expanded default width: `260px`.
- User resize range: `220px` through `340px`.
- Collapsed width: retain the existing frozen-theme `48px` behavior.
- Existing persisted widths outside the new range are migrated to `260px`, not silently left oversized.
- Existing persisted widths within the new range are preserved.
- The resize handle remains keyboard-focusable and visually appears only on hover, focus, or active resize.
- At narrow breakpoints the existing UI Lab responsive/collapse behavior remains authoritative.

## Surface and hierarchy

- Use a warm graphite/slate sidebar surface distinct from the near-black work canvas, expressed as product semantic OKLCH tokens.
- Use a subtle right divider rather than a heavy boundary.
- Keep the utility row compact, followed by the ImperaOS identity/search row and the primary navigation.
- The root `Yeni görev` destination stays recognizable as the current route through text/icon emphasis, but does not render a large filled active pill.
- Project/task rows use quiet transparent defaults, compact radii, and a restrained selected surface only for durable task selection.
- Section labels and secondary metadata stay muted; project/task names retain adequate contrast.
- The footer remains pinned to the bottom, with a subtle separator, compact avatar, account copy, and settings action.

## Runtime status

The browser preview cannot load desktop-owned workspace data. The state must remain truthful and fail closed, but the sidebar will present that status as a compact, subdued inline notice under the Projects heading instead of a dominant paragraph. The main composer may continue to show its existing runtime alert. Tauri desktop behavior and real workspace loading are unchanged.

## Interaction and accessibility

- Preserve real navigation, project registration, pin, reorder, archive, search, settings, profile, history, collapse, and resize actions.
- Preserve visible hover, active, disabled, and `:focus-visible` states.
- Keep the separator accessible with its existing role and label.
- New transitions must respect `prefers-reduced-motion`.
- No hidden horizontal overflow may be introduced at supported viewport sizes.

## Verification contract

- Store unit tests cover the `260px` default, live clamping to `220–340px`, and migration of both valid and oversized persisted widths.
- Sidebar component tests cover the semantic root-link class and truthful compact runtime notice without weakening governed-data tests.
- Browser/E2E verification covers computed expanded width, sidebar/background separation, root-link treatment, responsive overflow, navigation, and resize behavior.
- Existing full Vitest, Playwright, build, lint, UI Lab theme-hash verification, bridge parity, Rust tests, and Tauri launch smoke gates must remain green before publication.

## Self-review

- No placeholders, fake records, or no-op reference controls are introduced.
- The chosen measurements are explicit and testable.
- The migration behavior distinguishes persisted restoration from live dragging.
- Canonical theme ownership and product adapter ownership are unambiguous.
- Desktop-only runtime truth remains visible rather than being suppressed.
