# ADR_ARTIFACT_001: Artifact Storage

- Status: Accepted
- Owner: MAIN / Artifact Workspace
- Authoritative sources: approved artifact workspace plan sections 5.2, 7, 10.4 and Task 1.2
- Last verified: 2026-07-16 at Git commit `d1bb6c0097399064fc578976c466d2a8c693d482`
- Open decisions: optional at-rest encryption provider and platform-specific directory fsync support

## Context

Artifacts require queryable metadata, immutable history, bounded binary assets, optimistic concurrency, and crash recovery. A database-only blob model makes large editor payloads and export recovery expensive; a filesystem-only model cannot enforce workspace, principal, classification, and revision invariants.

## Decision

Use SQLite in WAL mode for metadata, authorization references, idempotency records, and a durable write journal. Store immutable content revisions and content-addressed assets below a backend-resolved workspace root. Renderer-supplied absolute paths are never accepted.

Every mutation requires `expectedRevision`, a content hash, workspace/principal context, and an idempotency key. The commit protocol is:

1. Validate policy, quota, expected revision, and target root; reserve a pending journal entry.
2. Write a same-volume temporary file, flush and `fsync` it, then atomically rename it to its immutable final revision path.
3. In one SQLite transaction insert the revision, advance the artifact current revision, write the audit reference, and mark the journal committed.
4. `fsync` the containing directory where the platform exposes a reliable primitive.

The database is updated only after the immutable content exists and its hash matches. Therefore SQLite must never point to a missing or hash-mismatched file. Startup orphan reconciliation replays committed journals, quarantines unreferenced final files, removes stale temporary files only inside the guarded storage root, and never invents a revision. Restore and duplicate always create a new revision or artifact; history is not rewritten.

## Consequences

- Optimistic conflicts are explicit and no-op saves create no revision.
- Cross-store atomicity is implemented as a recoverable protocol, not claimed as a single transaction.
- Backup must capture SQLite plus the revision/asset trees at a documented checkpoint.
- Storage health, hash verification, orphan counts, disk pressure, and reconciliation outcome become release evidence.

## Rejected alternatives

- SQLite blobs: rejected for large content, export, and recovery ergonomics.
- Mutable working files as source of truth: rejected because history and crash invariants become ambiguous.
- Renderer-owned paths: rejected as a traversal and workspace-isolation risk.
