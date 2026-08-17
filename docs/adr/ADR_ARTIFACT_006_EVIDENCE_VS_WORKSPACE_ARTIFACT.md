# ADR_ARTIFACT_006: Evidence versus Workspace Artifact

- Status: Accepted
- Owner: MAIN / Artifact Workspace
- Authoritative sources: approved artifact workspace plan sections 2.8, 3.2, 5.3, 9.12 and Task 1.2
- Last verified: 2026-07-16 at Git commit `d1bb6c0097399064fc578976c466d2a8c693d482`
- Open decisions: retention coupling when source evidence expires before a derived workspace artifact

## Context

Existing run and audit artifacts are immutable evidence. Workspace artifacts are editable, revisioned collaboration objects. Treating both as the same object would allow audit history to be changed or would make normal editing impossible.

## Decision

Evidence remains immutable and read-only. “Open as workspace artifact” performs a governed copy into a new artifact with a new ID and revision 1. It records `sourceEvidenceRef`, source content hash, source run/workspace, import timestamp, actor, policy decision, and classification provenance. The source file and evidence metadata are never moved, rewritten, or reclassified by the import.

The import requires source read permission, target artifact create permission, workspace binding, quota checks, content-type validation, and any required approval. Target classification is at least as restrictive as the source; it cannot be lowered by copy. The copied bytes are hash-verified before the new artifact becomes current. Later edits, restores, duplicates, exports, and archives affect only the workspace artifact.

UI labels must distinguish “Evidence (read-only)” from “Workspace artifact (editable copy)”. Links allow an authorized operator to trace from the copy back to the immutable source without exposing a raw filesystem path. Deleting or archiving the workspace copy never deletes source evidence.

## Consequences

- Audit integrity and normal editing have separate lifecycles.
- Imported content may consume independent retention/quota and requires provenance in export/audit records.
- A missing or expired source leaves a non-secret provenance tombstone; it does not invalidate already verified workspace revisions.
- Tests must prove copy semantics, hash parity, workspace isolation, classification monotonicity, and source immutability.

## Rejected alternatives

- In-place evidence editing: rejected because it destroys immutable audit meaning.
- Symlinking evidence into the workspace store: rejected due to path, lifecycle, and cross-workspace risks.
- Copy without provenance: rejected because the derived artifact would lose its evidence chain.
