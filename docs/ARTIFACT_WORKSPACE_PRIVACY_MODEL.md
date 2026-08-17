# Artifact Workspace Privacy Model

Artifact content is workspace-scoped customer data. Each artifact and asset carries a data class: public, internal, confidential, or regulated. Classification is inherited on duplicate/fork and may be raised but not silently lowered. Evidence artifacts and editable workspace artifacts are separate domains; evidence is immutable and can only be copied through an explicit governed operation.

The default assistant context is metadata-only. Content, a selection, or surrounding text is included only for an explicit purpose, within byte/node budgets, after workspace and classification checks. Provider routing receives the exact selected data classes so confidential or regulated content cannot enter an ineligible provider. Redaction occurs before prompt compilation, logs, diagnostics, support bundles, and error messages. Raw form responses are not persisted unless the schema policy explicitly permits a persistence mode.

Local storage contains SQLite metadata, immutable revision payloads, content-addressed assets, journals, quarantine, and backups. Absolute paths are operational secrets and are not placed in renderer state, audit payloads, export records, or support reports. Browser local/session storage must not contain artifact bodies, form answers, license material, approvals, export tickets, or provider credentials.

Retention is status- and policy-driven. Archive is reversible and preserves history. Revision restore creates a new revision; it does not rewrite history. Orphan cleanup is dry-run first, approval-gated, and evidence-producing. No incident procedure performs permanent delete. Backup and restore must preserve workspace boundaries, hashes, classification, audit links, and schema versions.

Privacy verification includes canary-secret tests, Windows and Unix absolute-path tests, prompt and support-bundle inspection, log field allowlists, response persistence policy tests, cross-workspace denial, and provider data-class binding. A privacy regression disables the global artifact gate and the AI SDK transport if needed until a forward-fix or verified restore is complete.
