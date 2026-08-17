# UI Lab Runtime Repair Design

## Objective

Make the v2 product shell's workspace, terminal, new conversation, model selection, and conversation removal flows behave truthfully and reliably in the ImperaOS desktop runtime. Browser preview remains explicitly non-native; it must not pretend to provide governed desktop capabilities.

## Decisions

- Conversation removal is **soft archive**, never permanent deletion. Archive preserves the task, messages, and links, hides the task from active navigation, and moves a selected archived task to a safe route.
- Native-only controls stay unavailable until the desktop bridge and required runtime context are ready. They display an actionable capability reason instead of a later invoke failure.
- The Rust product-workspace handler map and artifact-RPC allowlist form one bounded protocol contract. New allowlist entries must be concrete product methods, retain trusted identity enforcement, and preserve mutation idempotency checks.
- No renderer fallback may fabricate PTY, browser, files, data, project, or task results.

## Architecture

### Workspace lifecycle

`ProductArtifactWorkspace` must turn an artifact tab's positive `openRequest` into an idempotent open operation, not a toggle. React StrictMode may mount effects twice, so repeating the request must leave the workspace open. Workspace tab selection must recover a missing active ID by selecting a remaining tab; a visible tab strip must never render without a corresponding active panel.

### Native contract and readiness

The governed methods used by `ProductWorkspaceClient` must be enumerated in the Rust allowlist with a focused contract test. Missing runtime prerequisites (desktop bridge, workspace identity, project root, deployment origin, or native browser profile) are represented by a shared readiness value consumed by New Work and workspace launchers. Terminal behavior is unchanged when a trusted root is available; otherwise it is disabled with a reason. Browser preview continues to show the desktop-runtime requirement.

### Windows terminal lifecycle

The desktop terminal must use a ConPTY implementation that does not request inherited cursor state. `PSEUDOCONSOLE_INHERIT_CURSOR` is intended for a console host nested inside another console host; this GUI host has no such parent cursor to inherit. Microsoft documents that the request must be answered asynchronously over the PTY streams and that omitting that reply can deadlock the session. The pinned `portable-pty 0.9.0` implementation enables that flag unconditionally, so the project will patch only that crate's Windows ConPTY creation flags through a local Cargo source override. The public `portable_pty` API, terminal permissions, shell selection, root-ticket policy, and renderer protocol remain unchanged.

### Conversation lifecycle

New Work creates one canonical `assistantSessionId`, persists it with the task, and initializes the assistant runtime with that same ID. It must not navigate to the new task until both task creation and the initial-message transaction succeed; a failure reports an error and leaves no selected incomplete conversation. Archiving updates the store, clears the selected task if it matches, and routes to the project's safe destination. Archived content is never treated as deleted.

### Model selection

Provider identity is normalized at the picker boundary. Legacy aliases such as `ollama` map to the discovered `local-ollama` record without replacing authoritative availability metadata. Only discovered, available, installed models are selectable; disabled providers and unavailable models remain visible with their truthful reason. The normalized selected provider/model is passed unchanged to task runtime settings and the native invocation.

### Error handling and observability

The v2 shell receives a root error boundary and unhandled-error reporting surface. Product-workspace failures preserve the backend error code and retryability in a typed UI error so disabled states, alerts, and retry affordances remain specific. Background persistence failures that affect the user's selected task are surfaced rather than silently discarded.

## Test strategy

- Unit tests reproduce StrictMode artifact opening, invalid active-tab recovery, model alias normalization, disabled model selection, canonical session propagation, and archive route/store fallback.
- Rust tests assert every frontend-used product RPC method is allowlisted and that unlisted methods remain rejected.
- Tauri integration tests exercise task create/archive, terminal start/write/output/status/kill, and bridge error envelopes from a launched desktop runtime.
- A desktop lifecycle test opens workspace surfaces, archives the selected conversation, and verifies post-reload persisted state.
- A Windows-native PTY regression test runs a real interactive PowerShell command and asserts both output and a clean exit without a host-side cursor-inheritance reply.

## Constraints

- Preserve the existing governed identity checks, origin policy, project folder tickets, mutation idempotency, and archive data retention.
- Do not alter frozen UI Lab theme files or turn browser preview into a native-capability simulator.
- Preserve unrelated worktree changes: the pre-existing `Cargo.toml` line-ending status and generated/untracked local directories are outside this work.
- The local PTY override must preserve `portable-pty 0.9.0`'s package name and version, retain license files, and differ only in the ConPTY creation flag set.

## Self-review

- Soft archive, navigation fallback, and data retention are explicit.
- Every reported broken user flow has a named boundary and verifiable test class.
- Native failures fail closed rather than returning fabricated data.
- The design changes no authorization, trusted identity, or origin-policy boundary.
