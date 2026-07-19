# Artifact Workspace Data Model

`artifacts` stores the stable identity and current pointer: artifact ID, workspace ID, kind, title, status, schema version, data class, current revision ID/number, source session/turn, creator and updater identities, timestamps, etag, and bounded metadata. Titles need not be unique; the service applies deterministic suffixes. Workspace plus update time and workspace plus kind/status are indexed.

`artifact_revisions` is append-only. A revision records its parent/base, monotonically increasing number, mutation type, content-relative path, SHA-256, byte size, encoding, bounded change summary, author, idempotency key, and timestamp. `(artifact_id, revision_number)` and `(artifact_id, idempotency_key)` are unique. Restore and fork create new revisions with provenance instead of editing old rows.

`artifact_assets` is workspace-scoped and content-addressed by SHA-256. It records media type, size, safe relative path, optional dimensions/original name, data class, creator, and timestamp. Deduplication never crosses workspace or classification boundaries. `artifact_links` connects artifacts to sessions, turns, runs, evidence, approvals, sources, and exports without embedding content.

`form_submissions` records the schema revision, principal, persistence policy, redacted summary, idempotency, disposition, and continuation result. `artifact_operation_dedup` binds an idempotency key to the request hash and result. `artifact_exports` records format, lifecycle status, safe basename, hash, size, actor, workspace, and timestamps; it never stores an absolute destination path.

The filesystem root contains `metadata/artifacts.sqlite3`, immutable revision payloads under `content/<workspace>/<artifact>/revisions`, assets under `assets/<workspace>/sha256`, plus bounded `tmp`, `quarantine`, and `backups`. Writes use journal/reconcile semantics and atomic replacement. Schema changes are additive and versioned. Rollback disables features and restores a verified backup or applies a forward-fix; it does not downgrade schema in place.
