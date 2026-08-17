# ADR_ARTIFACT_004: Editor Licenses

- Status: Accepted
- Owner: MAIN / Artifact Workspace
- Authoritative sources: approved artifact workspace plan sections 2.7, 12.11, 13 and Task 1.2; `docs/ARTIFACT_WORKSPACE_DEPENDENCY_MATRIX.md`
- Last verified: 2026-07-16 at Git commit `d1bb6c0097399064fc578976c466d2a8c693d482`
- Open decisions: optional purchase/entitlement records for commercial adapters

## Context

Handsontable production use and tldraw production/offline use require entitlements that are not currently recorded. Evaluation modes are not acceptable production authority, and trial network contact conflicts with offline requirements.

## Decision

Licensed adapters are fail-closed. `handsontable`, `@handsontable/react-wrapper`, and `tldraw` are deferred and their production capabilities remain off until a backend license doctor verifies an approved entitlement, permitted product/version scope, offline behavior, and build target. The accepted production fallback is the repository-owned spreadsheet grid and `CanvasContentV2` editor. These adapters preserve the same backend artifact, revision, policy, selection, asset, and export contracts and require no commercial package.

License material is loaded only by the trusted backend/Tauri boundary from configured secret references. Literal keys, entitlement payloads, hashes that enable reuse, and vendor responses are never written to repository files, renderer state, logs, telemetry, audit bodies, or support bundles. The handshake exposes only enabled/disabled state and a stable reason code.

No evaluation key, environment-name heuristic, or client-side boolean can enable a licensed adapter. Missing, invalid, expired, network-dependent, or unverifiable entitlement selects the explicit `bundled_fallback` adapter. The runtime snapshot reports this choice; fallback is never silent and renderer configuration cannot promote it to commercial.

## Consequences

- Spreadsheet and canvas remain fully editable through reviewed bundled adapters without commercial dependencies.
- Optional commercial chunks stay absent until entitlement is verified.
- Local gates check package presence, capability resolution, redaction, adapter selection, and fallback behavior without secrets.
- License acquisition is an optional adapter upgrade, not a workspace release dependency.

## Rejected alternatives

- `non-commercial-and-evaluation` in production: rejected by license terms.
- tldraw trial mode: rejected because it is not offline-compatible production proof.
- Renderer-entered license keys: rejected as a secret and authority boundary violation.
