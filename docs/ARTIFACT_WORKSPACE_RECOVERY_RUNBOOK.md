# Artifact Workspace Recovery Runbook

Trigger recovery for integrity failure, unauthorized mutation, cross-workspace access, crash loop, data loss, export corruption/replay, CSP or external-network violation, license bypass, or a mainline regression. Record time, workspace, candidate commit, bounded reason codes, affected operation IDs, and audit references. Do not copy content or secrets into the incident record.

First disable `artifact_workspace.enabled`; disable `ai_sdk_tauri_transport.enabled` as well if assistant context or provider routing is implicated. Stop the artifact sidecar when writes must cease. Preserve SQLite, content, assets, journal, tmp, quarantine, backups, native export samples, audit, and evidence. Never perform permanent delete, history rewrite, schema downgrade, or manual hash repair.

Run read-only doctor and integrity checks. Inspect SQLite integrity, revision and asset hashes, missing/orphan files, evidence-chain continuity, pending journal entries, tmp/quarantine state, and disk/count bounds. Classify the incident before any repair. For a recoverable interrupted write, use reconciliation and verify that the final revision pointer and content hash agree. Restore an artifact revision by creating a new governed revision. Clean orphans only after a dry-run report and explicit approval.

For database corruption, verify the chosen backup independently, restore into a separate root, run migrations forward, then execute the full integrity and security gates before switching roots. Evidence data is never migrated in place. Prefer a forward-fix; use verified restore when integrity cannot be proven. Keep features off during repair.

Exit recovery only when integrity, reconciliation, policy, cross-workspace, CSP/no-network, export, and targeted regression tests pass on one immutable commit; the no-ship entry is closed with evidence; and operators approve a staged re-enable. Enable global, then document, then one kind at a time. Keep the original incident bundle and hashes according to retention policy.
