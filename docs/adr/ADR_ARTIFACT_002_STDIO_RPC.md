# ADR_ARTIFACT_002: Persistent stdio RPC

- Status: Accepted
- Owner: MAIN / Artifact Workspace
- Authoritative sources: approved artifact workspace plan sections 4.3, 5.6, 8.2 and Task 1.2
- Last verified: 2026-07-16 at Git commit `d1bb6c0097399064fc578976c466d2a8c693d482`
- Open decisions: packaged Python runtime locator on macOS and measured maximum binary ticket size

## Context

Artifact reads, saves, history, and validation need lower latency and stronger lifecycle control than spawning a CLI process per request. A localhost service would add a network listener and authentication surface.

## Decision

Run one supervised Python artifact sidecar per desktop application. Tauri owns the child process, handshake, pending request map, restart budget, shutdown, and export ticket registry. Communication uses versioned, length-prefixed UTF-8 JSON frames over stdin/stdout; stdout contains frames only and redacted diagnostics go to stderr.

The handshake declares protocol version, maximum frame size, capabilities, feature gates, and backend readiness. Requests have a unique ID, workspace/principal context, method allowlist entry, deadline, and idempotency key for mutations. Responses echo the ID and return either typed data or a bounded structured error. Raw binary content uses guarded files or opaque single-use tickets rather than unbounded JSON/base64 payloads.

Malformed, oversized, duplicate, unknown-method, out-of-order, and timed-out frames fail closed. The supervisor permits at most three bounded restart attempts with backoff, then opens a circuit and exposes a stable unavailable reason. On restart, safe reads may retry; mutations retry only with the same idempotency key. Shutdown first stops admission, drains bounded in-flight work, then terminates the child.

## Consequences

- No TCP port, browser fetch, or renderer subprocess authority is introduced.
- Sidecar restart recovery must meet the plan target and prove no duplicate revision.
- Packaging must verify the trusted executable/resource path on Windows and macOS.
- Protocol fixtures, fragmented-frame tests, crash tests, and a one-sidecar process assertion are mandatory.

## Rejected alternatives

- Frontend-only persistence: rejected because it bypasses canonical Python policy and validation.
- Per-operation CLI spawn: retained only as a measured diagnostic fallback, not the primary runtime.
- Local HTTP server: rejected because it broadens the attack and deployment surface.
