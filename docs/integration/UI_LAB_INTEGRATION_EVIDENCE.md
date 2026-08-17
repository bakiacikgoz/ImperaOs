# UI Lab Integration Evidence

## Source and branch provenance

- UI Lab source: `/Users/baki/Documents/ImperaOS-UI-Lab`
- Frozen UI Lab source commit: `165208e90dd37376d5f0a21df22b7a1e7756aab5`
- Stacked base: `0a9c4ea5a6e26a3b32a9dd327ec1d7154ac39376`
- Integration branch: `codex/imperaos-ui-lab-full-integration-v1`

The Product Shell is authored under `apps/operator-panel/src/product-shell/`.
It does not import the UI Lab checkout, `src/mocks/**`, or `demoStore.ts`.
The UI Lab source remains unchanged.

## Frozen theme contract

- `tokens.css`, `globals.css`, and `surfaces.css` are retained byte-for-byte
  under `product-shell/styles/ui-lab/`. `ProductTheme` removes only the two
  source `@import` statements at runtime to avoid a duplicate load.
- `uiLabThemeManifest.ts` pins the source commit and SHA-256 checksums;
  `npm run ui-lab:theme:verify` reads the checked-in bytes and fails on drift:
  - `tokens.css`: `47bfbda433800a6947f86e1e9a41f8096bacf93ad63f4c1dd9f88f893e65506a`
  - `globals.css`: `9cba3ad4558258b07a2d05670593a9c3489c061a6fba2f3aa0fe013b2db2a904`
  - `surfaces.css`: `25e000276ed2329d71fd5bcbcc2e7db07f91817c77ca3dd4ff441fb243307d2b`
- Product-only adapter CSS resets pre-existing Operator Panel rules where a
  shared class name would otherwise leak into the frozen template. It also
  styles governed/native controls that have no UI Lab equivalent.
- The style host is absent on `/system/*`; the legacy Operator Panel remains
  isolated from the new template.

## Product/runtime evidence

- The product router uses the desktop-safe hash router and preserves the old
  Operator Panel below `#/system/*`.
- Projects, tasks, task messages, links and preferences are SQLite-backed and
  exposed through the existing sidecar/Tauri bridge with idempotency binding.
  Project pin state, manual order, archives and cursor pages persist across
  restarts. Native folder selection exposes only an opaque ticket; the raw
  local path remains in the native bridge while the sidecar records a generated
  `rootRef` and display name.
- New work persists the initial user message, routes to the durable task ID,
  and starts the assistant session with the selected governed composer options.
- Task reasoning effort, speed and approval profile persist in the product
  workspace. Fast selects the CLI fast-chat router path; always-ask requires a
  governance ticket and fails closed if one cannot be issued; policy-automatic
  does not widen the existing policy decision.
- The product composer has a registry of safe slash commands. Each command
  resolves to the same bounded prompt controls as the visible safe-intent UI;
  unsupported commands are disabled rather than interpreted as capabilities.
- Existing Artifact Workspace controllers and all seven artifact editors remain
  canonical. Product-shell tabs host the Artifact Workspace, PTY terminals,
  native browser and registered preview surfaces. Selecting an artifact card
  passes its exact artifact ID into the canonical workspace, which opens and
  focuses the persisted artifact rather than a mock copy.
- Project files and data explorer controls are visibly disabled with explicit
  capability reason codes. This runtime has no governed project-files or data
  query API, so the shell does not fabricate either surface.
- Browser origin policy is documented in
  `docs/security/BROWSER_ORIGIN_POLICY.md` and enforced by the native runtime.
  It has no global bypass: user browsing accepts only explicitly entered HTTPS
  URLs; preview accepts only exact runtime-registered `localhost`/`127.0.0.1`
  origins; and agent browsing accepts only the task/deployment allowlist in a
  fresh isolated profile. Redirects repeat that mode-specific validation.
- Browser and preview tabs retain their native session label while inactive;
  a validated reserved viewport synchronizes the native child webview bounds,
  and tab deactivation hides it before any product overlay can appear. Popup,
  download and external-application attempts enter an explicit approval flow;
  unimplemented executors fail closed after the request is denied or
  acknowledged.
- A user PTY receives only a durable, opaque project `rootRef`; native code
  resolves its local path from protected native storage and fails closed when
  the project root is no longer available.
- The task context rail and activity dock render real assistant session run,
  approval, artifact, safe-prompt-control and timeline references; unavailable
  Git branch context stays visibly disabled rather than being synthesized.
- Library, approvals and agents select canonical backend detail from their
  own lists or Global Search routes; approval decisions retain the existing
  identity/approval bridge. Product-wide keyboard commands are registered
  centrally, and `Cmd/Ctrl+K` only focuses Global Search.
- Conversation actions open governed artifacts and approvals, copy, cancel or
  regenerate through their existing boundaries. Feedback remains visibly
  disabled with `ASSISTANT_FEEDBACK_CAPABILITY_UNAVAILABLE` because this
  runtime provides no governed feedback sink.

## Visual parity evidence

- `npm run ui-lab:parity:capture` launches the frozen UI Lab and the Product
  Shell independently, then captures source/target pairs for:
  home collapsed, home expanded, task conversation, task workspace, library,
  approvals, agents, settings and global search.
- Coverage is five viewports (`1440×900`, `1280×800`, `1024×768`, `768×900`,
  `390×844`) in dark and light themes: 90 cases and 180 PNGs.
- The generated report is
  `artifacts/operator-panel-ui/ui-lab-parity/report.html`; its JSON companion
  records the frozen source commit and home geometry for both applications.
- Source and target home geometry matches exactly for all captured viewports,
  including the narrow expanded-sidebar layout.
- `npm run test:e2e:ui-lab` independently checks the mounted theme, responsive
  hierarchy, overflow boundary, collections, settings, search and a real
  Chromium route transition proving product adapter styles leave `/system/*`.
- The target capture uses an isolated page-init bridge fixture so the same
  stable records can be compared visually. That fixture is test-only evidence;
  it neither represents a Tauri/native success claim nor supplies a production
  data fallback.

## Mock/static guards

- `git diff --name-only origin/codex/imperaos-assistant-artifact-workspace-v1...HEAD`
  contains Product Shell and native runtime source.
- The same diff contains no `website/` path.
- A product-shell grep for `mockTasks`, `mockProjects`, `mockAgents`,
  `mockApprovals`, `mockArtifacts`, `demoScenarios` and `mockTerminal` returns
  no production match.

## Fresh verification — 2026-07-25

- Operator Panel: 136 test files / 498 tests passed.
- Operator Panel lint and production TypeScript/Vite build passed.
- i18n coverage passed with 270 dictionary keys, 33 reason-code keys and both
  `en`/`tr` locales.
- Bridge parity passed with 12 checked actions and 87 registered commands.
- UI Lab parity E2E passed (3/3), covering the five required viewports and
  computed-style legacy isolation.
- Visual capture produced 90 source/target cases and 180 PNGs. The measured
  home geometry maximum delta was `0px`.
- Frozen UI Lab source: 39 Node tests passed; lint and production build passed.
- Native tests passed: 63 library tests plus artifact-crash-recovery and
  desktop-identity integration tests. `cargo check` and `cargo fmt --check`
  also passed.
- The complete repository Python test suite and Ruff passed.
- `git diff --check`, production mock-name guards and website-scope guards
  passed.
- The Tauri development process stayed alive for the 10-second launch probe.
  Launched bridge instrumentation and a live assistant response remain
  explicitly conditional; the smoke report does not convert them into a fake
  success.

## Capability boundaries retained by design

- Project files, data explorer, agent-browser qualification and assistant
  feedback are not supplied by this desktop runtime. Their controls are either
  not exposed or are disabled with an explicit reason code; no mock fallback
  is presented as a working product surface.
