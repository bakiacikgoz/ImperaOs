# UI Lab Theme Parity Design

## Goal

Make the Product Shell visually indistinguishable from the frozen UI Lab source
at `/Users/baki/Documents/ImperaOS-UI-Lab` commit
`165208e90dd37376d5f0a21df22b7a1e7756aab5`, while preserving the current
ImperaOS product data, governance, assistant, artifact, terminal, browser,
preview, approval, and legacy-route behavior.

The UI Lab is the canonical visual template. ImperaOS remains the canonical
behavior and data source.

## Scope

Parity covers the full visual contract:

- dark and light color tokens;
- typography, font stack, font sizes, weights, and line heights;
- application geometry, spacing, borders, radii, elevation, and separators;
- expanded and collapsed sidebar states;
- top bar, home hero, suggestion cards, composer, conversation, task header,
  workspace split, context rail, bottom dock, collections, settings, menus,
  modals, and empty/error states;
- hover, focus, selected, active, disabled, loading, streaming, and archived
  states;
- source responsive breakpoints, narrow split-pane behavior, overlays, and
  collapsed controls;
- icon sizing, stroke weights, placement, truncation, scrolling, and
  transitions;
- native terminal, browser, and preview surfaces adapted to the same visual
  grammar where the UI Lab has no native implementation.

Copy, labels, records, routes, permissions, and runtime behavior may differ
where the real product requires it. Those differences must not alter the
template's hierarchy, density, or visual rhythm.

## Architecture

### Canonical theme layer

The source `tokens.css`, `globals.css`, and `surfaces.css` become the basis of a
Product Shell theme layer in `apps/operator-panel/src/product-shell/styles/`.
Token values, responsive rules, and surface declarations remain source-faithful.
Selectors are scoped beneath `.imperaos-product-shell-v2` or an equivalent
Product Shell host so the legacy `/system/*` application is unaffected.

The Product Shell host owns the `data-theme` contract. Dark and light values
match the source exactly. Global body/root requirements needed for viewport,
font smoothing, and overflow are applied only while Product Shell mode is
active and are removed or neutralized for the legacy application.

### Source-shaped product components

Product components adopt the source DOM hierarchy and class contract rather
than translating the template onto the current simplified `ps-*` shell.
Source-shaped presentation components accept real product records and
callbacks through typed props.

The main mapping is:

| UI Lab template | Product implementation |
| --- | --- |
| `AppShell` | Product router shell and global search |
| `Sidebar` | Durable projects/tasks, real pin/order/archive mutations |
| `TopBar` | Real route/task/workspace/context controls |
| `NewWorkPage` | Real project selection and governed task creation |
| `Composer` | Existing assistant runtime/model/effort/speed/approval controls |
| `ConversationView` | Durable messages and live assistant stream |
| `WorkSurface` | Canonical Artifact Workspace plus runtime tabs |
| `ContextRail` | Real runs, approvals, prompt context, and capability states |
| `BottomDock` | Real activity, agent work, terminal/log/evidence references |
| collection pages | Real artifacts, approvals, agents, and honest automation state |
| `SettingsShell` | Persistent product preferences and legacy advanced routes |

The source mock modules and `demoStore.ts` are never imported into production.

### Native and canonical runtime surfaces

Artifact editors remain owned by the existing Artifact Workspace. Terminal,
browser, and preview remain native/runtime-backed. Their outer chrome, tab
strip, toolbar, empty state, and status treatment adopt UI Lab tokens and
surface classes. Native webview bounds and security policy remain unchanged.

## Data and interaction flow

1. The Product Workspace and existing bridges load real projects, tasks,
   messages, links, artifacts, approvals, and agents.
2. Presentation adapters shape those records into source-compatible view
   props without copying source mock data.
3. Source-shaped components emit existing governed callbacks.
4. Mutations continue through `ProductWorkspaceClient`, assistant adapters,
   Artifact Workspace controllers, terminal commands, and browser commands.
5. Loading, empty, error, unavailable, and disabled capability states use the
   template's layout and styling while preserving explicit product reason
   codes.

No visual component gains authority to bypass governance, browser origin
policy, native surface coordination, persistence, or approval boundaries.

## Responsive design

The source breakpoints and layout transitions are canonical:

- sidebar width, collapse affordance, and compact navigation match the source;
- the home hero, cards, and composer preserve source max widths and vertical
  placement;
- task conversation/workspace splitting follows source widths and divider
  behavior;
- context rail becomes the source-style overlay at narrow widths;
- composer controls wrap or collapse in the same order as the source;
- native webviews follow the measured Product Shell viewport after every
  responsive layout change;
- horizontal overflow is prevented in sidebar, task header, composer, tab
  strip, and collection layouts.

Acceptance viewports are 1440×900, 1280×800, 1024×768, 768×900, and 390×844 in
both dark and light themes.

## Error handling and capability truth

Runtime failures must not fall back to demo records or fake successful states.
Errors, setup requirements, empty results, and unavailable capabilities occupy
the nearest source template state and retain a visible, useful message.

Browser, preview, terminal, assistant, artifact, approval, and data-access
security boundaries are behaviorally unchanged. Styling cannot turn a denied
or disabled action into an enabled one.

## Verification

### Structural parity

- Source theme files are represented in the target with a documented
  source-to-target manifest.
- Production Product Shell has no source mock/demo imports.
- Core Product Shell routes render source class and hierarchy contracts.
- Legacy routes remain isolated from Product Shell styles.

### Visual parity

Automated screenshots are captured from the frozen UI Lab and Product Shell at
the acceptance viewports and themes. Comparison masks are permitted only for
dynamic copy, timestamps, IDs, and native-rendered content; geometry, color,
typography, spacing, borders, and component placement are not masked.

The home shell, task shell, workspace, collections, settings, modal/search,
collapsed sidebar, and narrow responsive states each receive a side-by-side
review. Any visible template divergence is treated as a defect.

### Behavior and regression

- Existing Product Shell tests remain green.
- New tests cover theme propagation, source class contracts, collapsed and
  responsive states, runtime surface tab preservation, and legacy style
  isolation.
- Operator Panel lint, type checking/build, i18n coverage, and bridge parity
  pass.
- Python and Rust suites are rerun when touched behavior crosses their
  boundaries.
- Tauri launch smoke confirms the Product Shell starts with the new theme.

## Completion criteria

The work is complete only when:

1. the target uses the UI Lab template as its actual presentation layer, not a
   visual approximation;
2. all current real product features remain reachable and governed;
3. dark, light, responsive, interaction, empty, error, and disabled states
   match the source grammar;
4. the legacy application remains isolated and usable;
5. screenshot review and automated regression checks show no unresolved
   template divergence.
