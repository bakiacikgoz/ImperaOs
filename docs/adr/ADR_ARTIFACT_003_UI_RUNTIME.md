# ADR_ARTIFACT_003: Assistant UI Runtime

- Status: Accepted
- Owner: MAIN / Artifact Workspace
- Authoritative sources: approved artifact workspace plan sections 4.1, 5.7, 9 and Task 1.2; Task 0.2 golden parity evidence
- Last verified: 2026-07-16 at Git commit `d1bb6c0097399064fc578976c466d2a8c693d482`
- Open decisions: reconnect/replay protocol after the first persistent sidecar release

## Context

The existing ImperaOS assistant reducer owns turn identity, event sequencing, governance cards, cancel behavior, and preview parity. Adding assistant-ui and AI SDK must not create a second state machine or route provider calls from the renderer.

## Decision

The ImperaOS assistant session remains the canonical state owner. `@assistant-ui/react` consumes it through `ExternalStoreRuntime`; assistant-ui is a presentation/runtime adapter, not an authority. AI SDK uses a custom Tauri `ChatTransport` only where its streaming primitives are useful.

The transport calls typed Tauri commands, filters `assistant://event` by session and turn ID, preserves monotonic sequence, closes listeners exactly once, and maps `AbortSignal` to the existing cancel command. It must never select the default `/api/chat` HTTP transport, instantiate a provider adapter, read provider secrets, or perform remote fetch from the renderer. First-release `reconnectToStream()` returns `null` until replay is implemented by the trusted runtime.

Approval and tool cards are projections of backend-governed events. Decisions execute through existing Tauri/governance commands and synchronize the canonical session. Preview fixtures are development/test-only and production without a working bridge fails closed. The legacy workbench remains available behind a separate fallback flag.

## Consequences

- Task 0.2 golden fixtures are the parity contract for text, policy, approval, artifact reference, cancel, error, and preview behavior.
- A single reducer prevents double tool dispatch and cancel/final races.
- assistant-ui or AI SDK failure can fall back without changing persisted artifact state.
- Network monitoring must prove no accidental default HTTP transport.

## Rejected alternatives

- AI SDK `useChat` as a second canonical store: rejected due to duplicated lifecycle authority.
- Provider SDKs in React: rejected because secrets and policy belong behind the backend boundary.
- Replacing the legacy runtime in one cutover: rejected because rollback and parity evidence are required.
